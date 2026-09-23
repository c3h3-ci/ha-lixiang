"""实体共用工具（route_id 解析，多车兼容）

各平台统一调用，避免散落的 `vin or 'default'` 逻辑。
"""

from __future__ import annotations

from typing import Any

from .const import CONF_VIN, DOMAIN


def route_id_of(entry: Any = None, config_entry: Any = None) -> str:
    """从 ConfigEntry 取 route_id（多车时取该 entry 对应车辆的）。

    兼容三种情况：
      ① data['routes'] 是列表（多车，新格式）→ 取第一辆（各平台按需传入）
      ② data['vin'] 存在（单车）→ 用 VIN 派生
      ③ 都没有 → 用 entry_id 派生

    ★ 目的：unique_id 从 `{DOMAIN}_{vin or 'default'}_` 改为
      `{DOMAIN}_{route_id}_`，避免多车时 VIN 为空导致的碰撞。
    """
    e = config_entry or entry
    if e is None:
        return "default"
    data = getattr(e, "data", None) or {}
    raw = data.get("routes")
    if isinstance(raw, list) and raw and isinstance(raw[0], dict):
        rid = raw[0].get("route_id")
        if rid:
            return str(rid)
    vin = str(data.get(CONF_VIN) or "")
    if vin:
        import hashlib
        return "v" + hashlib.sha256(vin.encode()).hexdigest()[:12]
    eid = getattr(e, "entry_id", "") or ""
    if eid:
        import hashlib
        return "e" + hashlib.sha256(eid.encode()).hexdigest()[:12]
    return "default"


def control_enabled(entry: Any) -> bool:
    """是否允许车控（enable_control 选项）。"""
    opts = getattr(entry, "options", None) or {}
    return bool(opts.get("enable_control", True))


def route_id_of_vin(vin: str | None) -> str:
    """从 VIN 派生 route_id（各平台统一入口）。

    用法（实体 __init__ 里）：
        self._rid = route_id_of_vin(vin)
        self._attr_unique_id = f"{DOMAIN}_{self._rid}_{description.key}"
    """
    v = str(vin or "")
    if v:
        import hashlib
        return "v" + hashlib.sha256(v.encode()).hexdigest()[:12]
    return "default"


__all__ = ["route_id_of", "route_id_of_vin", "control_enabled"]
