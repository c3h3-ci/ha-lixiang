"""车辆路由抽象层（多车支持）

背景（2026-09-23 审查）
---------------------
原来架构是「一个 ConfigEntry == 一辆车」：
    vin = config_entry.data.get(CONF_VIN) or ""
    unique_id = f"{DOMAIN}_{vin or 'default'}_{key}"

当账号绑了多辆车时：
  · VIN 为空 → 所有车塌缩到 `{DOMAIN}_default_*` → **unique_id 碰撞**
  · coordinator 的 _online / _mid_freq_cache 是单值 → L9 数据被 L6 覆盖
  · 车型硬编码 "理想 L6" → L9 车主看到错误车型

本模块提供 **route_id** 抽象（借鉴 huawei-auto-cloud 的 RouteRegistry）：
  · route_id 是内部主键，与上游 VIN 解耦
  · 车辆改别名 / VIN 补全 / 换授权 → route_id 不变 → 实体不重建
  · 多车天然成立（routes 是字典）
  · 每辆车独立的 device_info / 轮询状态

兼容性
------
单车场景（绝大多数用户）：
  route_id 由 VIN 确定性派生 → 与旧 unique_id 行为一致（VIN 存在时）
  VIN 缺失时用 entry_id 派生，避免多车碰撞

多车场景：
  config_entry.data["routes"] = [{route_id, vin, alias, model, role_id}, ...]
  各平台遍历 routes 创建实体
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .const import CONF_VIN


@dataclass(frozen=True)
class VehicleRoute:
    """一辆车的稳定身份（route_id 与上游 ID 解耦）。"""

    route_id: str
    vin: str = ""
    alias: str = ""            # 车辆别名（App 里显示的名字）
    model: str = "理想汽车"     # 真实车型名（从 vehicle list 取）
    role_id: int = 0           # 车主角色（家人账号权限不同）
    supports_location: bool = True   # 由 privacy_pos_service 决定

    @property
    def display_name(self) -> str:
        return self.alias or self.vin or self.model or "理想汽车"

    @property
    def vin_tail(self) -> str:
        return self.vin[-6:] if len(self.vin) >= 6 else self.vin


def derive_route_id(*, vin: str = "", entry_id: str = "",
                    index: int = 0) -> str:
    """派生 route_id（确定性，保证同一辆车每次得到相同值）。

    规则（优先级）：
      ① 有 VIN → 用 VIN 的 hash 前 16 位（稳定，跨 entry 一致）
      ② 无 VIN 但有多车 → 用 entry_id + index 的 hash（避免碰撞）
      ③ 都没有 → "default"

    ★ 为什么不用 VIN 明文？
      旧代码直接用 VIN 拼 unique_id（`{DOMAIN}_{vin}_sensor_key`），
      这在多车时是能用的，但 VIN 可能被补全/修正（从空变成有值），
      用 hash 派生后只要 VIN 一致，route_id 就一致。
    """
    if vin:
        h = hashlib.sha256(vin.encode()).hexdigest()[:12]
        return f"v{h}"
    if entry_id:
        h = hashlib.sha256(f"{entry_id}:{index}".encode()).hexdigest()[:12]
        return f"e{h}"
    return "default"


@dataclass
class RouteRegistry:
    """一辆或多辆车的集合（请求上下文的唯一入口）。"""

    routes: dict[str, VehicleRoute] = field(default_factory=dict)

    # ---------- 构造 ----------
    @classmethod
    def from_entry(cls, entry) -> "RouteRegistry":
        """从 ConfigEntry 构造。多车读 data['routes']，单车回退到旧字段。"""
        data = getattr(entry, "data", None) or {}
        raw = data.get("routes")
        reg = cls()
        if isinstance(raw, list) and raw:
            for i, item in enumerate(raw):
                if not isinstance(item, Mapping):
                    continue
                vin = str(item.get("vin") or "")
                rid = str(item.get("route_id") or
                          derive_route_id(vin=vin,
                                          entry_id=entry.entry_id, index=i))
                reg.routes[rid] = VehicleRoute(
                    route_id=rid,
                    vin=vin,
                    alias=str(item.get("alias") or ""),
                    model=str(item.get("model") or "理想汽车"),
                    role_id=int(item.get("role_id") or 0),
                    supports_location=bool(item.get("supports_location", True)),
                )
            if reg.routes:
                return reg
        # 单车 / 向后兼容
        vin = str(data.get(CONF_VIN) or "")
        rid = derive_route_id(vin=vin, entry_id=entry.entry_id)
        reg.routes[rid] = VehicleRoute(
            route_id=rid, vin=vin,
            alias=str(data.get("alias") or ""),
            model=str(data.get("model") or "理想汽车"),
        )
        return reg

    # ---------- 查询 ----------
    def get(self, route_id: str) -> VehicleRoute | None:
        return self.routes.get(route_id)

    def all(self) -> list[VehicleRoute]:
        return list(self.routes.values())

    def first(self) -> VehicleRoute | None:
        return next(iter(self.routes.values()), None)

    def __len__(self) -> int:
        return len(self.routes)

    def __iter__(self) -> Iterable[VehicleRoute]:
        return iter(self.routes.values())

    @property
    def is_multi(self) -> bool:
        return len(self.routes) > 1


# ---------- 实体起名 / 设备信息 ----------

def entity_uid(route: VehicleRoute | None, suffix: str) -> str:
    """统一 unique_id 构造（所有平台共用）。

    ★ 改造后：`{DOMAIN}_{route_id}_{suffix}`
      旧行为：`{DOMAIN}_{vin or 'default'}_{suffix}`
      当 VIN 存在时，route_id = "v"+sha256(vin)[:12]，
      unique_id 会变化 → 实体需要重建一次（一次性迁移）。
    """
    DOMAIN = "lixiang_auto"
    rid = route.route_id if route else "default"
    return f"{DOMAIN}_{rid}_{suffix}"


def device_info_for(route: VehicleRoute | None, *, entry_id: str = "",
                    account_uid: str | None = None) -> dict[str, Any]:
    """构造 device_info。

    · identifiers 用 route_id（稳定）
    · model 用真实车型名（不再硬编码"理想 L6"）
    · 可选 via_device 指向「理想账号」虚拟设备，形成 账号→车辆 层级
    """
    DOMAIN = "lixiang_auto"
    rid = route.route_id if route else "default"
    info: dict[str, Any] = {
        "identifiers": {(DOMAIN, rid)},
        "manufacturer": "理想汽车",
        "model": (route.model if route else "理想汽车") or "理想汽车",
        "name": (route.display_name if route else "理想汽车") or "理想汽车",
    }
    if route and route.vin:
        info["serial_number"] = route.vin
    if account_uid:
        info["via_device"] = (DOMAIN, account_uid)
    return info


def account_device_info(phone_tail: str = "") -> dict[str, Any]:
    """「理想账号」虚拟设备（多账号时形成层级树）。"""
    DOMAIN = "lixiang_auto"
    return {
        "identifiers": {(DOMAIN, f"account_{phone_tail or 'default'}")},
        "manufacturer": "理想汽车",
        "model": "理想账号",
        "name": f"理想账号 ****{phone_tail}" if phone_tail else "理想账号",
        "entry_type": "service",
    }


__all__ = [
    "VehicleRoute", "RouteRegistry", "derive_route_id",
    "entity_uid", "device_info_for", "account_device_info",
]
