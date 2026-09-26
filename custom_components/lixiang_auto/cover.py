"""理想汽车 cover 实体 — 尾门 / 全车窗.

★ 为什么用 cover 而不是 button？
  · cover 是 HA 对"可开合设备"的标准域
    → 状态与操作合一（open/closed + open_cover/close_cover）
    → 语音助手（HA Assist）/ 第三方桥接都能识别
  · button 只有"按一下"，无状态、无开合语义

命令（与 button.py 实测一致）:
  尾门  remoteVehPlgControl  {"plgPosi":"100"} / {"plgPosi":"0"}
  车窗  remoteVehWdwControl  四窗位置 99 / 0

状态:
  尾门  VSS door_trunk（DoorSwitchStatus.TrunkDoor，1=开，0/2/3=关）
  车窗  VSS window_main / copilot / back_left / back_right（0-100%）

⚠️ 车控会真实作用于车辆。
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import (
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_VIN, DOMAIN, LOGGER_NAME
from .entity_helper import route_id_of_vin
from .gate import require_control

_LOGGER = logging.getLogger(LOGGER_NAME)

_WIN_KEYS = ("flWindPosi", "frWindPosi", "rlWindPosi", "rrWindPosi")
_WIN_STATE_KEYS = ("window_main", "window_copilot", "window_back_left", "window_back_right")
_TRUNK_STATE_KEY = "door_trunk"

# ★ 2026-09-24 乐观更新有效期（秒）
#   依据：HA 轮询间隔 DEFAULT_SCAN_INTERVAL_SECONDS = 60 秒
#   取 2.5 倍轮询周期 = 150 秒 → 保证至少 2 次轮询机会让 VSS 追上
#   （过短：VSS 还没更新乐观值就失效 → 显示回退；
#     过长：服务端真实变化被掩盖过久）
OPTIMISTIC_TTL = 150.0
CMD_PLG = "remoteVehPlgControl"
CMD_WDW = "remoteVehWdwControl"


def _windows(pos: str | int) -> dict:
    return {k: str(pos) for k in _WIN_KEYS}


def _sig_num(vss: dict, key: str) -> float | None:
    sig = vss.get(key) or {}
    raw = sig.get("value")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][config_entry.entry_id]
    coordinator, li_api = data["coordinator"], data.get("li_api")
    vin = config_entry.data.get(CONF_VIN) or ""
    identifiers = {(DOMAIN, vin)} if vin else {(DOMAIN, config_entry.entry_id)}
    device_info = DeviceInfo(
        identifiers=identifiers, manufacturer="理想汽车",
        model="理想 L6", name="Li Auto L6" if vin else "Li Auto",
    )
    if li_api is None:
        _LOGGER.warning("无密码登录凭据，跳过 cover 实体")
        return
    async_add_entities([
        LiCarTrunkCover(coordinator, li_api, device_info, vin),
        LiCarWindowCover(coordinator, li_api, device_info, vin),
    ])


class LiCarTrunkCover(CoordinatorEntity, CoverEntity):
    """尾门（开/关 → cover，标准开合设备语义）."""

    _attr_has_entity_name = True
    _attr_name = "尾门"
    _attr_icon = "mdi:car-door"
    _attr_device_class = None  # 不标 garage：通用开合语义
    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE
    )

    def __init__(self, coordinator, li_api, device_info, vin: str) -> None:
        super().__init__(coordinator)
        self._api = li_api
        self._rid = route_id_of_vin(vin)
        self._attr_unique_id = f"{DOMAIN}_{self._rid}_cover_trunk"
        self._attr_device_info = device_info
        self._last_result: dict | None = None
        self._optimistic_closed: bool | None = None
        self._optimistic_until: float = 0.0

    @property
    def is_closed(self) -> bool | None:
        """★ 2026-09-24：乐观更新带 TTL（同 fan/switch/number 修复）"""
        import time as _t

        vss = (self.coordinator.data or {}).get("vss") or {}
        v = _sig_num(vss, _TRUNK_STATE_KEY)
        # DoorSwitchStatus.TrunkDoor: 1=开, 0/2/3=关
        vss_closed: bool | None = None if v is None else (v != 1)

        if self._optimistic_closed is not None:
            if _t.monotonic() < self._optimistic_until:
                if vss_closed is None or vss_closed != self._optimistic_closed:
                    return self._optimistic_closed
            self._optimistic_closed = None
            self._optimistic_until = 0.0

        return vss_closed

    @property
    def extra_state_attributes(self) -> dict:
        attrs: dict = {"cmd_key": CMD_PLG}
        if self._last_result is not None:
            attrs["last_command_result"] = self._last_result
        return attrs

    @require_control
    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._send({"plgPosi": "100"}, closed=False)

    @require_control
    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._send({"plgPosi": "0"}, closed=True)

    async def _send(self, cmd_data: dict, *, closed: bool) -> None:
        try:
            res = await self.hass.async_add_executor_job(
                self._api.send_command, CMD_PLG, cmd_data)
            self._last_result = res
            self._optimistic_closed = closed
            import time as _t
            self._optimistic_until = _t.monotonic() + OPTIMISTIC_TTL
            _LOGGER.info("车控 %s %s 已执行: %s", CMD_PLG, cmd_data, res)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("车控 %s %s 失败: %s", CMD_PLG, cmd_data, err)
            self._optimistic_closed = None
            raise
        await self.coordinator.async_request_refresh()


class LiCarWindowCover(CoordinatorEntity, CoverEntity):
    """全车窗 cover — 支持全开/全关 + 位置（开部分窗）.

    ★ 2026-09-24 位置语义改为标准 cover（便于滑条开部分窗）：
      HA position 0 = 物理全关
      HA position N = 物理开约 N%（车端 0…99）
      HA position 100 = 物理全开
      open_cover → 开窗; close_cover → 关窗; set_position → 按开度

    外部调用可走 async_physical_*（与 UI 方向无关）。
    """

    _attr_has_entity_name = True
    _attr_name = "车窗"
    _attr_icon = "mdi:car-window"
    _attr_device_class = None
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(self, coordinator, li_api, device_info, vin: str) -> None:
        super().__init__(coordinator)
        self._api = li_api
        self._rid = route_id_of_vin(vin)
        self._attr_unique_id = f"{DOMAIN}_{self._rid}_cover_window"
        self._attr_device_info = device_info
        self._last_result: dict | None = None
        # optimistic 存 HA position（0关…100开，与物理一致）
        self._optimistic_pos: int | None = None
        self._optimistic_until: float = 0.0

    def _physical_open_pct(self) -> float | None:
        """物理开度 0=全关 … ~99=全开；无信号返回 None。"""
        vss = (self.coordinator.data or {}).get("vss") or {}
        out: list[float] = []
        for key in _WIN_STATE_KEYS:
            v = _sig_num(vss, key)
            if v is not None:
                out.append(max(0.0, min(100.0, v)))
        if not out:
            return None
        return max(out)

    @property
    def physical_open_percent(self) -> int | None:
        """物理开度（0关…100开），供诊断用。

        ★ 2026-09-24：改为复用 current_cover_position（含 TTL 乐观逻辑），
          避免两处逻辑不一致。
        """
        return self.current_cover_position

    @property
    def current_cover_position(self) -> int | None:
        """★ 2026-09-24：乐观更新带 TTL（同 fan/switch/number 修复）"""
        import time as _t

        p = self._physical_open_pct()
        vss_pos = None if p is None else int(round(p))

        if self._optimistic_pos is not None:
            if _t.monotonic() < self._optimistic_until:
                # 车窗开合较慢，允许 3% 误差
                if vss_pos is None or abs(vss_pos - self._optimistic_pos) > 3:
                    return self._optimistic_pos
            self._optimistic_pos = None
            self._optimistic_until = 0.0

        return vss_pos

    @property
    def is_closed(self) -> bool | None:
        p = self.current_cover_position
        if p is None:
            return None
        return p <= 1

    @property
    def extra_state_attributes(self) -> dict:
        attrs: dict = {
            "cmd_key": CMD_WDW,
            "physical_open_percent": self.physical_open_percent,
            "window_positions": {
                k: _sig_num((self.coordinator.data or {}).get("vss") or {}, k)
                for k in _WIN_STATE_KEYS
            },
        }
        if self._last_result is not None:
            attrs["last_command_result"] = self._last_result
        return attrs

    # ---- 物理动作（真正发给车的）----
    async def _open_windows(self, pct: int = 99) -> None:
        await self._send(pct)

    async def _close_windows(self) -> None:
        await self._send(0)

    async def async_physical_open(self, pct: int = 99) -> None:
        """物理开窗（pct 0-100）。供外部服务调用。"""
        await self._open_windows(99 if pct >= 100 else max(1, pct))

    async def async_physical_close(self) -> None:
        """物理关窗。"""
        await self._close_windows()

    @require_control
    async def async_open_cover(self, **kwargs: Any) -> None:
        """开窗（全开）。"""
        await self._open_windows(99)

    @require_control
    async def async_close_cover(self, **kwargs: Any) -> None:
        """关窗（全关）。"""
        await self._close_windows()

    @require_control
    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """按开度设置：position=物理开度百分比（0关…100开）。"""
        pos = int(kwargs.get("position") or 0)
        pos = max(0, min(100, pos))
        if pos <= 0:
            await self._close_windows()
        else:
            # 车端全开为 99
            await self._open_windows(99 if pos >= 100 else pos)

    async def _send(self, physical_posi: int) -> None:
        """physical_posi: 0=关, 99≈全开。"""
        cmd_data = _windows(physical_posi)
        try:
            res = await self.hass.async_add_executor_job(
                self._api.send_command, CMD_WDW, cmd_data)
            self._last_result = res
            self._optimistic_pos = max(0, min(100, physical_posi))
            import time as _t2
            self._optimistic_until = _t2.monotonic() + OPTIMISTIC_TTL
            _LOGGER.info("车控 %s %s 已执行: %s", CMD_WDW, cmd_data, res)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("车控 %s %s 失败: %s", CMD_WDW, cmd_data, err)
            self._optimistic_pos = None
            raise
        await self.coordinator.async_request_refresh()
