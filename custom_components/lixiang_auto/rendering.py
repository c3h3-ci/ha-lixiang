"""传感器值的渲染逻辑（纯函数，可单测）

★ 2026-09-23 从 sensor.py 抽出（架构优化方案 阶段 1.3）

目的：把 29 处 `if key ==` 的分支逻辑变成【可单测的纯函数】。
这是**纯搬家** —— 行为与原实现完全一致（由 tests/ 兜底）。

为什么抽出来？
  · 原实现依赖 self.coordinator.data / self.entity_description，
    无法在单测里构造 → 改了不知道对不对
  · 抽成纯函数后，可参数化喂各种输入做等价性验证
  · 历史教训：`n != 0` → `n == 1` 的语义 bug（391cd8a），
    若有这套测试，5 分钟就能发现

函数契约
--------
输入：
  key   信号 key（如 "battery_level" / "charge_status"）
  val   该信号的原始值（可能为 None）
  sig   信号完整 dict（{"value":..,"ts":..}）或 None
  data  coordinator.data（含 vehicle_status 等非 VSS 字段）

输出：
  渲染值（str / int / float / dict / None / STATE_UNKNOWN）

用法
----
  # sensor.py
  from .rendering import render_value
  ...
  return render_value(self.entity_description.key, val, sig, self.coordinator.data)

  # tests/test_rendering.py
  assert render_value("charge_status", 3, {"value": 3}, {}) == "充电中"
"""

from __future__ import annotations

import json
from typing import Any

# 与 sensor.py 保持一致
STATE_UNKNOWN = "unknown"


def render_value(
    key: str,
    val: Any,
    sig: dict | None = None,
    data: dict | None = None,
) -> Any:
    """把信号的原始值渲染成实体值（纯函数）。

    对应原 LiCarSensor._compute_value()，逻辑逐行照搬。
    """
    data = data or {}
    if key == "online_status":
        st = data.get("vehicle_status")
        if st is None:
            return STATE_UNKNOWN
        return "在线" if int(st) == 1 else "离线"
    if sig is None:
        return None
    if val is None:
        return None

    # ---- 特殊信号: 返回可读值 ----
    if key == "location" and isinstance(val, str):
        try:
            loc = json.loads(val)
            return f"{loc.get('lat', 0):.5f},{loc.get('lon', 0):.5f}"
        except (ValueError, TypeError):
            return STATE_UNKNOWN
    if key == "sentry" and isinstance(val, str):
        try:
            return "已开启" if int(json.loads(val).get("sentinelStatus", 0)) else "已关闭"
        except (ValueError, TypeError):
            return STATE_UNKNOWN
    if key == "sentry_switch" and isinstance(val, str):
        try:
            return "已开启" if int(json.loads(val).get("sentinelSwitch", 0)) else "已关闭"
        except (ValueError, TypeError):
            return STATE_UNKNOWN
    if key == "ota_progress":
        try:
            o = json.loads(val) if isinstance(val, str) else val
            p = o.get("progress")
            return round(float(p) * 100, 1) if isinstance(p, (int, float)) and p <= 1 else p
        except (ValueError, TypeError, AttributeError):
            return STATE_UNKNOWN
    if key == "ota_state" and isinstance(val, str):
        try:
            o = json.loads(val)
            return o.get("currentVersion") or o.get("displayTargetVersion") or STATE_UNKNOWN
        except (ValueError, TypeError):
            return STATE_UNKNOWN
    if key == "charge_status":
        # ★ 2026-09-23 复刻 App 的 XChargeDataHandle.getChargeState()
        #   （smali:80-241）—— 不再自造枚举。
        #
        #   App 逻辑（输入 6 个信号 → 输出归一化状态码）：
        #     if 预约开关==1 && AC枪==2 && 预约state==1      → 90  预约充电
        #     if chargeStatus==3                             → 50  充电中
        #     if chargeStatus==5 && chrgComplete==1          → 60  已完成
        #     if chargeStatus==5 && !complete && eveFlt==1   → 111 告警
        #     if chargeStatus==5 && !complete                → 70  已停止
        #     if chargeStatus==7                             → 111 告警
        #     if chargeStatus==2                             → 40  电池加热
        #     if chargeStatus==4                             → 80  电池保温
        #     else                                            → 0
        #
        #   枚举（XChargeDataHandle$Status.smali:18-32）：
        #     BATTERY_HEAT=40 CHARGING=50 COMPETE=60 STOP=70
        #     BATTERY_INSULATION=80 APPOINT_CHARGE=90 CHARGE_ALARM=111
        _vss = (data or {}).get("vss", {})

        def _v(k: str):
            _s = _vss.get(k) or {}
            v = _s.get("value")
            try:
                return int(v) if v is not None else None
            except (TypeError, ValueError):
                return None

        cs = _v("charge_status")
        # 预约充电判定（三条件同时满足）
        if _v("scheduled_charge_switch") == 1 \
                and _v("charge_gun_ac") == 2 \
                and _v("scheduled_charge_state") == 1:
            return "预约充电"
        if cs == 3:
            return "充电中"
        if cs == 5:
            if _v("charge_complete") == 1:
                return "充电完成"
            if _v("charge_fault") == 1:
                return "充电告警"
            return "已停止"
        if cs == 7:
            return "充电告警"
        if cs == 2:
            return "电池加热"
        if cs == 4:
            return "电池保温"
        # 未在 App 分支内的原始值（0/1/10/15 等）→ App 归 DEFAULT
        if cs is None:
            return None
        return "—"
    if key.startswith("seat_") and key.endswith("_heat"):
        return {0: "关", 1: "低", 2: "中", 3: "高"}.get(int(val) if str(val).isdigit() else -1, val)
    if key.startswith("seat_") and key.endswith("_vent"):
        return {0: "关", 1: "低", 2: "中", 3: "高"}.get(int(val) if str(val).isdigit() else -1, val)
    if key == "scheduled_charge_switch":
        return "已开启" if int(val) else "已关闭"
    if key == "scheduled_charge_state":
        return {0: "未预约", 1: "已预约", 2: "充电中"}.get(int(val) if str(val).isdigit() else -1, val)
    if key.startswith("tire_") and key.endswith("_warning"):
        return "正常" if not int(val) else "告警"
    if key == "tpms_status":
        return "正常" if not int(val) else "异常"
    if key == "charge_fault":
        return "正常" if not int(val) else "故障"
    if key == "fuel_low_warning":
        return "正常" if not int(val) else "油量低"
    if key in ("online_5g", "online_xcu"):
        return "在线" if val else "离线"
    if key == "provision_auth":
        return "已授权" if val else "未授权"
    if key.startswith("window_"):
        try:
            return int(val)          # 单位已是 %, 只返回值
        except (ValueError, TypeError):
            return val
    if key == "sunshade":
        return {0: "关闭", 1: "打开"}.get(int(val) if str(val).isdigit() else -1, val)
    if key in ("battery_keep_warm",):
        return "已开启" if val else "已关闭"
    if key == "svm_filekey" and isinstance(val, str):
        try:
            o = json.loads(val)
            return o.get("picTime") or STATE_UNKNOWN
        except (ValueError, TypeError):
            return STATE_UNKNOWN
    if key == "ac_set_temp":
        try:
            return float(val)
        except (ValueError, TypeError):
            return val

    # ---- 保养类: 提取关键字段 ----
    if key.startswith("maint_"):
        try:
            o = json.loads(val) if isinstance(val, str) else val
            left = o.get("maintainLeftMileage")
            due = o.get("maintainDueDate")
            if left is not None:
                return f"剩余 {left:.0f} km"
            if due and due != "--":
                return f"到期 {due}"
            return "正常"
        except (ValueError, TypeError, AttributeError):
            return "未知"
    if key == "trip_total":
        try:
            o = json.loads(val) if isinstance(val, str) else val
            mi = o.get("totalMileage") or o.get("adMileage")
            if isinstance(mi, (int, float)) and mi > 1000:
                return round(mi / 1000, 1)      # 转为 km
            return mi if mi is not None else STATE_UNKNOWN
        except (ValueError, TypeError, AttributeError):
            return STATE_UNKNOWN
    # ★ 统一翻译：0/1 等裸数字 → 中文（translations.py）
    #   App 里没有数字→文案映射表，我们用实测表翻译（见 translations.py 说明）
    _path = (VSS_PATHS or {}).get(key, "") if "VSS_PATHS" in globals() else ""
    if _path:
        _tr = translate(_path, val)
        if _tr != val:
            return _tr

    if key == "config_code":
        try:
            o = json.loads(val) if isinstance(val, str) else val
            return o.get("configLevel") or o.get("autopilot") or STATE_UNKNOWN
        except (ValueError, TypeError, AttributeError):
            return STATE_UNKNOWN
    if key == "hu_diag":
        try:
            o = json.loads(val) if isinstance(val, str) else val
            return f"EEA{o.get('eea', '?')}"
        except (ValueError, TypeError, AttributeError):
            return STATE_UNKNOWN
    if key == "battery_keep_warm":
        try:
            o = json.loads(val) if isinstance(val, str) else val
            return "已开启" if o.get("startTime") else "已关闭"
        except (ValueError, TypeError, AttributeError):
            return STATE_UNKNOWN
    if key == "scheduled_charge_start":
        return str(val)[:5] if val else STATE_UNKNOWN
    if key == "scheduled_charge_end":
        return str(val)[:5] if val else STATE_UNKNOWN

    # ---- 通用: 长 JSON 截断, 其余直返 ----
    if isinstance(val, (dict, list)):
        s = json.dumps(val, ensure_ascii=False)
        return s if len(s) <= 250 else s[:247] + "..."
    if isinstance(val, str) and len(val) > 250:
        return val[:247] + "..."
    return val

