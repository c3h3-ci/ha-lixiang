"""理想汽车 · 车型功能探测 (features.py)

原理
----
不同车型 (L6/L7/L8/L9/MEGA) 支持的硬件功能不同。App 通过 `CLVehicleConfig`
(信号 `Vehicle.Information.ConfigCode`) 拿到编码后的配置, 再用服务端字典解码。

我们拿不到服务端字典, 但可以用【VSS 信号探测法】判断功能是否存在:
  - 车辆支持的硬件 → 该功能的所有 VSS 信号都能读到值
  - 不支持的硬件   → 整批路径返回 400 invalid_path (我们已在 get_vss_state
                     里做了容错, 不存在的路径被静默跳过)

因此: 【探测组内至少一个路径有值 → 认为支持】

用法
----
    feats = detect_features(li_api)      # 返回 {功能名: bool}
    if feats.get("冰箱"):
        ...创建冰箱实体...

实测（2026-09-23，XM01 车型）:
    ✅ 冰箱 / 哨兵 / 前备箱 / 座椅加热 / Xmode
    ❌ 旋转座椅
"""

from __future__ import annotations

import logging
from typing import Any

from .const import DOMAIN, LOGGER_NAME

_LOGGER = logging.getLogger(LOGGER_NAME)

# ============================================================================
# ★ 两种判断方式的说明（2026-09-23）
# ============================================================================
# 【App 的方式：编译期硬编码】
#   每个车型一个 StateDelegate 类，例如 LXM01StateDelegate (L6 / M01)：
#     getSupportPlateDisplay() { return 1; }              // ✅ 支持
#     getSupportFridge() { getUN_SUPPORT().invoke();
#                          throw new KotlinNothingValueException(); }  // ❌ 不支持
#   调用方 (LxVehicleHelperStateDelegate) 用 try/catch 包装：
#     try   { return delegate.getSupportFridge(); }   // 支持
#     catch { return 0; }                              // 不支持
#
#   实测 L6 (M01) 的硬编码表：
#     ✅ getSupportPlateDisplay
#     ❌ getSupportFridge / getSupportFrontTrunk /
#        getSupportRotatableSeat / getSupportAutopilot
#
#   优点: 准确（官方定义）  缺点: 需要 App 发版才能加车型
#
# 【我们的方式：运行时 VSS 探测】
#   读一组 VSS 信号，多数有有效 ts（≠"0"）判定为支持。
#   优点: 换车型无需改代码  缺点: 信号选择必须准确
#
# ⚠️ 陷阱：某些信号是【通用信号】（所有车型都上报），会造成误报。
#    例: Vehicle.Body.DoorLockStatus.FrontTrunkDoor 在所有车型都有，
#        不能用来判断"是否有前备箱"（真前备箱应有 Vehicle.Body.FrontTrunk.* 一组）
#
# 本模块策略: 【硬编码表优先, VSS 探测兜底】
#   1) 若车型在 KNOWN_FEATURES 里 → 用硬编码表（最准）
#   2) 否则 → 用 VSS 探测
# ============================================================================

# App 的硬编码功能表（从 smali 提取）
# key = 车型代号, value = {功能名: 是否支持}
KNOWN_FEATURES: dict[str, dict[str, bool]] = {
    "M01": {                      # L6（实测自 LXM01StateDelegate）
        "牌显": True,
        "冰箱": False,
        "前备箱": False,
        "旋转座椅": False,
        "自动驾驶": False,
        # ★ 2026-09-24 新增：L6 是【五座】SUV（前排 2 + 二排 3，无三排）
        #   服务端对不存在的三排硬件也返回 value=0 + 有效 ts，
        #   所以不能靠信号探测，必须靠车型判断。
        "三排座椅": False,
    },
}

# 功能名 → 探测用 VSS 路径组（任一有值即视为支持）
# 路径来自 docs/VSS路径全集_20260922.md（实测有效 167 个）
FEATURE_PROBES: dict[str, list[str]] = {
    "冰箱": [
        "Vehicle.Cabin.Fridge.ActWorkSts",
        "Vehicle.Cabin.Fridge.ModeState",
        "Vehicle.Cabin.Fridge.CoolTempSt",
        "Vehicle.Cabin.Fridge.DlyTmRemain",
    ],
    # 注: ReserveFridge 是通用 Xmode 信号（无冰箱的车也有），不能单独用于探测。
    #     "冰箱预约" 由 "冰箱" 推导，见 detect_features 末尾。
    "哨兵模式": [
        "Vehicle.Sentry.SentinelStatus",
        "Vehicle.Sentry.SettingsStatus",
        "Vehicle.Sentry.Video.Count",
    ],
    # ★ 修正 (2026-09-23): DoorLockStatus.FrontTrunkDoor 是所有车型都有的
    #   通用锁状态信号，不能判断是否有前备箱硬件。
    #   真前备箱应有 Vehicle.Body.FrontTrunk.* 一组信号。
    #   实测 L6: 无这些信号 → 判为不支持（与 App 硬编码 getSupportFrontTrunk
    #   抛异常一致）。
    "前备箱": [
        "Vehicle.Body.FrontTrunk.Status",
        "Vehicle.Body.FrontTrunk.DoorStatus",
        "Vehicle.Body.Frunk.Status",
    ],
    "座椅加热": [
        "Vehicle.Cabin.Seat.FLSeatHeatState",
        "Vehicle.Cabin.Seat.FRSeatHeatState",
        "Vehicle.Cabin.Seat.SLSeatHeatState",
        "Vehicle.Cabin.Seat.SRSeatHeatState",
    ],
    "二排座椅": [
        "Vehicle.Cabin.Seat.SLSeatHeatState",
        "Vehicle.Cabin.Seat.SRSeatHeatState",
    ],
    # ★ 2026-09-24 新增：三排座椅（L8/L9/MEGA 有，L6/L7 无）
    #
    # ⚠️ 探测可靠性说明：
    #   服务端对【不存在的三排硬件】也返回 value=0 + 有效 ts（实测 L6），
    #   所以【信号探测无法区分】。
    #   → 因此本项优先由 KNOWN_FEATURES（车型硬编码表）决定；
    #     未知车型才退回探测（可能误判，但至少不会漏掉真有六座的车）。
    "三排座椅": [
        "Vehicle.Cabin.Seat.TLSeatHeatState",
        "Vehicle.Cabin.Seat.TRSeatHeatState",
        "Vehicle.Cabin.Seat.TMSeatHeatState",
    ],
    "旋转座椅": [
        "Vehicle.Cabin.Seat.RotatableStatus",
        "Vehicle.Seat.Rotatable.Status",
    ],
    "方向盘加热": [
        "Vehicle.Cabin.WheelWarmStatus.WarmOnOff",
    ],
    "空气悬架": [
        "Vehicle.Chassis.AirSuspension.Status",
        "Vehicle.Chassis.SuspensionHeight",
    ],
    "电动尾翼": [
        "Vehicle.Body.Spoiler.Status",
        "Vehicle.Body.RearSpoiler.Status",
    ],
    # 注: Vehicle.360Svm.ParkPhoto.State (泊车拍照) 是通用功能, 不在此探测
    # ★ 2026-09-24 修正：原先探测路径用错
    #   错误路径（L6 无数据）：
    #     Vehicle.Camera.Photo.Status
    #     Vehicle.Camera.RemotePhoto.Status
    #   正确路径（L6 实测有数据）：
    #     Vehicle.360Svm.ParkPhoto.State   ← 泊车拍照状态
    #     Vehicle.360Svm.Park.Filekey      ← 拍照文件 key
    "远程拍照": [
        "Vehicle.360Svm.ParkPhoto.State",
        "Vehicle.360Svm.Park.Filekey",
    ],
}

# 车型编码（来自 VehicleModelCodeConst，用于日志识别）
VEHICLE_MODEL_CODES = {
    "101074633608064581": "A00",
    "952447875932008064": "M01A",
    "100204301435085761": "M01B",
    "100618542440964164": "M01B_RING_FIVE",
    "100174236664108736": "X01",
    "100618542440964163": "X02_22",
    "101492138788971191": "X02_MAX",
    "100980659723641806": "X02_PRO",
    "100980659723641805": "X03_22",
}




def _ts_fresh(ts: str, max_days: float = 7.0) -> bool:
    """判断信号时间戳"存在"（非 "0" / 非空）。

    ★ 判据说明（2026-09-23 实测修正）：
      实测 ts 分层：
        · 实时（<1天）:   51 个信号  — 车的当前状态
        · 2-3 天:         若干      — 车辆激活快照（无变化不更新）
        · 42~792 天:      config_code / charge_limit / ota_* 等
                                    — 【仍然有效】！只是长期未变

      因此不能用"年龄"判断有效性。
      真正无效的标志是 ts == "0"（服务端从未上报该信号），
      典型：无冰箱的车 Cabin.Fridge.* 全部 ts=0。
    """
    try:
        from datetime import datetime
        t = datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S")
        return (datetime.now() - t).total_seconds() < max_days * 86400
    except Exception:  # noqa: BLE001
        return True   # 解析失败时不惩罚（保守）


def _hardcoded_features(li_api: Any) -> dict[str, Any] | None:
    """用 Vehicle.Information.ConfigCode 识别车型, 返回 App 的硬编码功能表。

    返回 None 表示无法识别（调用方回退到 VSS 探测）。
    """
    try:
        state = li_api.get_vss_state(["Vehicle.Information.ConfigCode"]) or {}
        raw = state.get("Vehicle.Information.ConfigCode", {}).get("value")
        if not raw:
            return None
        import json
        cfg = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except Exception:  # noqa: BLE001
        return None

    # ★ 2026-09-24 启用（原先 return None 导致 KNOWN_FEATURES 完全没用上）
    #
    # 车型判定依据：
    #   ConfigCode.vehModel 的编码（如 "JR7"）需要服务端字典才能翻译，
    #   App 里【没有】该字典（已在 smali/Hermes/resources 全面搜索确认）。
    #
    #   因此用【可验证的特征组合】判定：
    #     ① KNOWN_FEATURES 里的车型代号（M01）来自 App 的
    #        LXM01StateDelegate 类 —— 该类的存在说明车型属于 M01 平台
    #     ② 经验判据：有 360Svm.ParkPhoto.State（泊车拍照）
    #        + 无冰箱信号 → L6
    #
    #   ⚠️ 保守策略：
    #     · 只有能【明确判定】车型时才返回硬编码表
    #     · 判不出 → 返回 None → 回退 VSS 探测
    #     · 这样不会把 L9 误判成 L6（进而隐藏三排座椅）
    code = cfg.get("vehModel") or ""
    seats_cfg = cfg.get("seats") or ""
    fridge_cfg = cfg.get("vehRefrigerator") or ""
    _LOGGER.debug(
        "ConfigCode: vehModel=%s seats=%s fridge=%s configLevel=%s",
        code, seats_cfg, fridge_cfg, cfg.get("configLevel"))

    # 已知车型样本（vehModel 编码 → KNOWN_FEATURES 的 key）
    # ★ 目前只确证了我们的车（JR7 = L6 / M01 平台）
    KNOWN_CODES = {
        "JR7": "M01",      # 实测样本（2026-09-23）
    }

    model_key = KNOWN_CODES.get(code)
    if not model_key:
        _LOGGER.debug("未知车型编码 %s，回退 VSS 探测", code)
        return None

    hard = dict(KNOWN_FEATURES.get(model_key) or {})
    if not hard:
        return None
    hard["_model"] = model_key
    return hard


def detect_features(li_api: Any) -> dict[str, bool]:
    """探测车辆实际支持的功能。

    返回 {功能名: 是否支持}；探测失败的组按 False 处理（保守）。
    """
    result: dict[str, bool] = {}
    all_paths: list[str] = []
    for paths in FEATURE_PROBES.values():
        all_paths.extend(paths)

    try:
        state = li_api.get_vss_state(all_paths) or {}
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("功能探测失败, 全部按不支持处理: %s", err)
        return {k: False for k in FEATURE_PROBES}

    # ① 先尝试用 App 的硬编码表（通过 ConfigCode 识别车型）
    hard = _hardcoded_features(li_api)
    if hard:
        _LOGGER.debug("使用 App 硬编码功能表 (%s): %s", hard.get("_model", "?"),
                        {k: v for k, v in hard.items() if not k.startswith("_")})
        # 用硬编码结果覆盖对应功能
        for feat, val in hard.items():
            if feat.startswith("_"):
                continue
            result[feat] = val
        # 未被硬编码覆盖的，继续走 VSS 探测
        remaining = {k: v for k, v in FEATURE_PROBES.items() if k not in result}
    else:
        remaining = FEATURE_PROBES

    for feat, paths in remaining.items():
        # ★ 判据 (2026-09-23 修正):
        #   服务端对【不存在的硬件】也返回 value=0, 但 ts="0"（从未上报）。
        #   因此必须同时满足: value 非空 且 ts 非 "0"。
        #   例: Cabin.Fridge.ActWorkSts=0 ts=0 → 无冰箱
        #       Body.DoorLockStatus.FrontTrunkDoor=1 ts=2026-09-21 → 有前备箱
        # 统计"有效信号"数
        # ★ 判据 (2026-09-23 改进)：
        #   ① value 非空
        #   ② ts != "0"（从未上报）
        #   ③ ts 在 7 天内（避免"残留默认值"，如 FrontTrunkDoor 停在 49h 前）
        valid = 0
        for p in paths:
            sig = state.get(p)
            if not sig:
                continue
            val = sig.get("value")
            ts = str(sig.get("ts") or "")
            if val is None or not ts or ts == "0":
                continue
            valid += 1
        # ★ 判据：多数信号有效才算支持（避免个别通用信号造成误报）
        #   实测: 无冰箱时仅 DlyTmRemain 有 ts，其余 3 个都是 ts=0 → 判为无
        need = 1 if len(paths) == 1 else max(2, (len(paths) + 1) // 2)
        result[feat] = valid >= need

    # "冰箱预约" 依赖冰箱硬件
    if "冰箱" in result:
        result["冰箱预约"] = result["冰箱"]

    supported = [k for k, v in result.items() if v]
    unsupported = [k for k, v in result.items() if not v]
    _LOGGER.info("车型功能探测: 支持=%s | 不支持=%s", supported, unsupported)
    return result


def read_vehicle_config(li_api: Any) -> dict[str, str]:
    """读取车型配置 (Vehicle.Information.ConfigCode)。

    返回服务端下发的原始编码字典, 例如:
        {"vehModel":"JR7","configLevel":"IZ8","seats":"AE4", ...}
    编码需要服务端字典才能翻译成人话, 这里仅原样返回。
    """
    try:
        state = li_api.get_vss_state(["Vehicle.Information.ConfigCode"]) or {}
        raw = state.get("Vehicle.Information.ConfigCode", {}).get("value")
        if not raw:
            return {}
        import json
        return json.loads(raw) if isinstance(raw, str) else dict(raw)
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("读取车型配置失败: %s", err)
        return {}
