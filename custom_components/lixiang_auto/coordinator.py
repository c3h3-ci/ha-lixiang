"""Li Auto 数据协调器（周期轮询车辆状态）."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import scan_interval_seconds, DOMAIN, LOGGER_NAME, SCAN_INTERVAL_SECONDS, VSS_PATHS

_LOGGER = logging.getLogger(LOGGER_NAME)


def _jitter(seconds: int, ratio: float = 0.1) -> int:
    """给轮询间隔加 ±ratio 随机抖动。

    ★ 目的（借自风控规避实践）：
      固定节奏的请求容易被服务端识别为脚本 →
      抖动后请求分布更接近真实客户端。
    """
    import random
    delta = max(1, int(seconds * ratio))
    return max(1, seconds + random.randint(-delta, delta))


class LiCarCoordinator(DataUpdateCoordinator[dict]):
    """理想汽车数据协调器.

    数据来源:
    - 异步 LiCarClient: 车辆列表 + basics (静态信息/在线标记)
    - 同步 LiApiClient (经 executor): vss/get-batch 实时信号 (电量/续航/门锁/胎压...)
    """

    def __init__(self, hass: HomeAssistant, client, li_api=None,
                 entry=None) -> None:
        _opts = getattr(entry, "options", None)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=_jitter(scan_interval_seconds(_opts))),
            always_update=False,
        )
        self._entry = entry
        self.client = client
        self.li_api = li_api
        self.vehicles: list[dict] = []
        # ★ 按 route 分桶（多车支持）—— 单车场景等价于单值
        self._online: dict[str, bool | None] = {}       # route_id → 在线
        self._mid_freq_ts: dict[str, float] = {}        # route_id → 时间戳
        self._mid_freq_cache: dict[str, dict] = {}      # route_id → 缓存
        self._low_freq_ts: dict[str, float] = {}
        self._low_freq_cache: dict[str, dict] = {}
        # 主 route（当前唯一支持的车；多车时扩展为遍历）
        self._route_id: str = ""

        # ★ 2026-09-24 错误处理（ROADMAP P1）:
        #   连续失败计数 → 分级处理（不打扰 → 告警 → 停止重试）
        self._fail_count: int = 0
        self._fail_notified: bool = False
        self._last_error: str = ""
        self._unsub_notify = None

    # ★ 信号分级（借自 huawei-auto-cloud 的节流策略 + 实测 ts 分析）
    #
    # 实测变化频率（2026-09-23，按信号 ts 新鲜度分层）:
    #   ① <1h   25 个  → 电量/续航/温度/胎压/车窗  【每轮必拉】
    #   ② 1-6h  30 个  → 门锁/充电状态/保养        【每轮必拉】
    #   ③ 6-24h 18 个  → 座椅加热/空调/哨兵        【每轮必拉】
    #   ④ 1-3天 22 个  → 二排座椅/胎压告警/油量    【每轮必拉，但可降频】
    #   ⑥ 7-30天 4 个  → OTA 信息                  【24 小时】
    #   ⑦ >30天 11 个  → 车辆配置/充电桩预约        【24 小时】
    #
    # 分频策略: 三档轮询间隔
    #   HIGH   → 每轮（SCAN_INTERVAL_SECONDS = 300s）
    #   MID    → 1 小时（充电配置类，变化慢但需及时）
    #   LOW    → 24 小时（车辆配置/OTA/保养类）
    #
    MID_FREQ_PREFIXES = (
        "charge_limit", "scheduled_charge_",   # 充电桩配置（很少改）
        # ★ 胎压告警/TPMS 保持【高频】（安全相关）
        "seat_s", "seat_t",                     # 二排/三排座椅（很少用）
        "fridge_",                              # 冰箱（无此硬件）
        "tank_lock",                            # 油箱锁
        "sunshade",                             # 遮阳帘
        "low_battery_mode",                     # 低电模式
        "low_vol_mode", "low_vol_flag",         # 低压模式
        "charge_fault", "charge_gun_dc",        # 充电故障/直流枪
        "park_fsd",                             # 泊车进度
        "fuel_low_warning",                     # 油量告警
        "charge_gun_ac",                        # 交流充电枪（慢变）
        "charge_remain_time",                   # 剩余充电时间（慢变）
    )
    MID_FREQ_INTERVAL = 3600            # 1 小时

    LOW_FREQ_PREFIXES = (
        "ota_",                             # OTA 信息
        "maint_",                           # 保养信息
        "config_code",                      # 车辆配置（出厂固定）
        "provision_auth",                   # 激活授权
        "battery_keep_warm",                # 电池保温设置
        "park_status",                      # 泊车状态
    )
    LOW_FREQ_INTERVAL = 24 * 3600       # 24 小时

    def _rid(self) -> str:
        """当前 route_id（延迟初始化）。"""
        if not self._route_id:
            try:
                from .entity_helper import route_id_of
                self._route_id = route_id_of(config_entry=self._entry)
            except Exception:  # noqa: BLE001
                self._route_id = "default"
        return self._route_id

    # ★ 在线探测信号（借自 huawei-auto-cloud 的在线驱动轮询策略）
    #   先只查 2 个连接状态字段，离线时跳过大轮询 → 省流量、降低风控风险
    PRESENCE_PATHS = [
        "Vehicle.ConnectManager.ConnectStatus.5G",
        "Vehicle.ConnectManager.ConnectStatus.xcu",
    ]

    async def _async_online(self) -> bool | None:
        """探测车辆是否在线。True=在线 / False=离线 / None=未知。

        ★ 判定规则（实测 5G=True / xcu=False 同时出现）:
            任一通道为 True  → 在线（多通道冗余）
            全部为 False     → 离线
            无有效值         → 未知

        注：5G 与 xcu 是两条独立链路，只要一条通就算在线。
        """
        if self.li_api is None:
            return None
        try:
            r = await self.hass.async_add_executor_job(
                self.li_api.get_vss_state, self.PRESENCE_PATHS)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("在线探测失败: %s", err)
            return None

        seen = False
        for sig in (r or {}).values():
            v = sig.get("value")
            if v is None:
                continue
            seen = True
            s = str(v).lower()
            if s in ("true", "1"):
                return True          # ★ 任一通道在线即在线
        if seen:
            return False             # 全部为 False → 离线
        return None                  # 无有效值 → 未知

    async def _async_update_data(self) -> dict:
        """轮询车辆数据（在线驱动）。

        策略（借自 huawei-auto-cloud）:
          ① 先探测在线状态（只读 2 个字段）
          ② 离线 → 跳过完整轮询，保留上一帧数据
          ③ 在线 → 完整轮询
          ④ 离线→在线切换 → 立即补取（本函数天然满足）
        """
        try:
            data = await self.client.update()
        except Exception as err:  # noqa: BLE001
            # ★ 2026-09-24 分级错误处理：
            #   ①②次失败 → 静默重试（网络抖动很常见）
            #   ③次起    → 记录 warning
            #   ⑤次起    → 发 HA 持久通知（用户可见）
            #   成功后    → 清除通知
            self._fail_count += 1
            self._last_error = str(err)[:200]
            n = self._fail_count

            if n < 3:
                _LOGGER.debug("轮询失败（第 %d 次，静默重试）: %s", n, self._last_error)
            elif n < 5:
                _LOGGER.warning("轮询连续失败 %d 次: %s", n, self._last_error)
            else:
                _LOGGER.error("轮询连续失败 %d 次: %s", n, self._last_error)
                await self._notify_failure(n)

            raise UpdateFailed(f"更新失败（第 {n} 次）: {err}") from err

        # 成功 → 清除失败状态
        if self._fail_count:
            _LOGGER.info("轮询恢复正常（此前连续失败 %d 次）", self._fail_count)
            await self._clear_failure()
        self._fail_count = 0
        self._last_error = ""

        if self.li_api is not None:
            # ① 在线探测
            online = await self._async_online()
            self._online[self._rid()] = online
            if online is False:
                # ② 离线 → 保留上一帧，不发起完整轮询
                prev = (self.data or {}).get("vss") if self.data else None
                data["vss"] = prev or {}
                data["vss_polled_at"] = (self.data or {}).get("vss_polled_at")
                data["vss_skipped"] = "车辆离线，跳过完整轮询"
                _LOGGER.debug("车辆离线，跳过完整轮询（保留 %d 个信号）",
                              len(data["vss"]))
                return data

            # ③ 在线（或未知）→ 完整轮询（三档分频）
            import time as _t
            now = _t.monotonic()
            need_mid = (now - self._mid_freq_ts.get(self._rid(), 0.0)) > self.MID_FREQ_INTERVAL
            need_low = (now - self._low_freq_ts.get(self._rid(), 0.0)) > self.LOW_FREQ_INTERVAL

            # ★ 2026-09-24 接入 signals.py（架构方案 2.3）
            #   从「前缀匹配」改为「读 spec.freq」——
            #   新增信号只需在 signals.py 里声明 freq，无需改这里。
            #
            #   等价性：gen_signals.py 已用同样的前缀规则生成 freq，
            #          所以分组结果应与旧逻辑一致（见 tests/test_signals.py）。
            from .signals import Freq, by_freq
            hi_paths = [sp.path for sp in by_freq(Freq.HIGH)]
            mid_paths = [sp.path for sp in by_freq(Freq.MID)]
            lo_paths = [sp.path for sp in by_freq(Freq.LOW)]

            # 兜底：signals.py 里没有、但 VSS_PATHS 里有的路径
            #   （避免新增路径时被漏掉）
            _covered = set(hi_paths) | set(mid_paths) | set(lo_paths)
            for _k, _p in VSS_PATHS.items():
                if _p not in _covered:
                    hi_paths.append(_p)

            try:
                # 高频：每轮都拉
                vss = await self.hass.async_add_executor_job(
                    self.li_api.poll, hi_paths
                )
                # 中频：1 小时一次
                if need_mid and mid_paths:
                    mid_vss = await self.hass.async_add_executor_job(
                        self.li_api.poll, mid_paths)
                    self._mid_freq_cache[self._rid()] = mid_vss.get("vss") or {}
                    self._mid_freq_ts[self._rid()] = now
                    _LOGGER.debug("拉取中频信号 %d 个（充电/胎压/座椅）",
                                  len(self._mid_freq_cache))
                _mid = self._mid_freq_cache.get(self._rid())
                if _mid:
                    vss["vss"].update(_mid)

                # 低频：24 小时一次
                if need_low and lo_paths:
                    lo_vss = await self.hass.async_add_executor_job(
                        self.li_api.poll, lo_paths)
                    self._low_freq_cache[self._rid()] = lo_vss.get("vss") or {}
                    self._low_freq_ts[self._rid()] = now
                    _LOGGER.debug("拉取低频信号 %d 个（OTA/保养/配置）",
                                  len(self._low_freq_cache))
                _low = self._low_freq_cache.get(self._rid())
                if _low:
                    vss["vss"].update(_low)
                # 反转: {实体key: {"value":..,"ts":..}} 方便实体取值
                data["vss"] = {
                    key: vss["vss"][path]
                    for key, path in VSS_PATHS.items()
                    if path in vss["vss"]
                }
                data["vss_polled_at"] = vss.get("polled_at")
                # basics 缺失时用 VSS 在线信号兜底
                if "vehicle_status" not in data and "online_5g" in data["vss"]:
                    data["vehicle_status"] = (
                        1 if str(data["vss"]["online_5g"]["value"]).lower() == "true" else 0
                    )
            except Exception as err:  # noqa: BLE001
                # 实时信号失败不拖垮静态数据 (也避免反复触发登录)
                _LOGGER.warning("VSS 实时信号轮询失败: %s", err)

        return data
