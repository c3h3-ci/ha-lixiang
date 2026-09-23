"""车辆路由模型（多车支持）

★ 2026-09-23 重构：删除死代码
  原先本文件还含 RouteRegistry / derive_route_id / entity_uid /
  device_info_for / account_device_info，经全仓核查：
    · entity_uid / device_info_for / account_device_info  外部调用数 = 0
    · RouteRegistry 仅被 coordinator.py 构造后从未使用
    · derive_route_id 与 entity_helper.route_id_of 重复
  → 全部移除，route_id 权威统一到 entity_helper.py

  本文件现在只保留 VehicleRoute 数据模型（供未来多车功能使用）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .entity_helper import route_id_of_vin


@dataclass(frozen=True, slots=True)
class VehicleRoute:
    """一辆已接入的车（不可变值对象）。"""

    route_id: str                     # 内部主键（entity_helper 派生）
    vin: str = ""
    alias: str = ""                   # 用户可见别名
    model: str = ""                   # 车型名（从 vehicle list 获取，勿硬编码）
    role_id: int = 0                  # 车辆角色（车主 / 家人）
    supports_location: bool = True    # 是否允许定位（隐私开关）

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "VehicleRoute":
        """从 config_entry.data['routes'] 的一项构造。"""
        vin = str(raw.get("vin") or "")
        rid = str(raw.get("route_id") or "") or route_id_of_vin(vin)
        return cls(
            route_id=rid,
            vin=vin,
            alias=str(raw.get("alias") or ""),
            model=str(raw.get("model") or ""),
            role_id=int(raw.get("role_id") or 0),
            supports_location=bool(raw.get("supports_location", True)),
        )

    @property
    def display_name(self) -> str:
        return self.alias or self.vin or self.model or "理想汽车"

    @property
    def vin_tail(self) -> str:
        return self.vin[-6:] if len(self.vin) >= 6 else self.vin


def routes_from_entry(entry: Any) -> list[VehicleRoute]:
    """从 ConfigEntry 解析车辆列表（多车读 data['routes']，单车回退 VIN）。"""
    data = getattr(entry, "data", None) or {}
    raw = data.get("routes")
    if isinstance(raw, list) and raw:
        out = [VehicleRoute.from_dict(x) for x in raw if isinstance(x, Mapping)]
        if out:
            return out
    vin = str(data.get("vin") or "")
    if vin:
        return [VehicleRoute(route_id=route_id_of_vin(vin), vin=vin)]
    return []


__all__ = ["VehicleRoute", "routes_from_entry"]
