"""Li Auto 二元传感器（车门/车窗/充电枪/连接/告警类）— 数据源 vss/get-batch."""

from __future__ import annotations

import json
import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import CONF_VIN, DOMAIN, LOGGER_NAME, VSS_PATHS
from .entity_helper import route_id_of_vin

_LOGGER = logging.getLogger(LOGGER_NAME)

# kind 决定值的语义:
#   lock   : 0=已锁, 非0=未锁   → on = 未落锁
#   door   : 0=关闭, 非0=打开   → on = 打开
#   plug   : 0=未插, 非0=已插   → on = 已连接
#   conn   : False=断, True=连  → on = 已连接
#   warn   : 0=正常, 非0=告警   → on = 告警
#   heat   : 0=关, 非0=开       → on = 开启
#   json   : 从 JSON 字段判读
BINARY_DESCRIPTIONS: tuple[tuple[BinarySensorEntityDescription, str], ...] = (
    # ---- 车门锁（on = 未落锁）----
    (BinarySensorEntityDescription(key="lock_main", name="主驾门锁",
        device_class=BinarySensorDeviceClass.LOCK, icon="mdi:car-door-lock"), "lock"),
    (BinarySensorEntityDescription(key="lock_copilot", name="副驾门锁",
        device_class=BinarySensorDeviceClass.LOCK, icon="mdi:car-door-lock"), "lock"),
    (BinarySensorEntityDescription(key="lock_back_left", name="左后门锁",
        device_class=BinarySensorDeviceClass.LOCK, icon="mdi:car-door-lock"), "lock"),
    (BinarySensorEntityDescription(key="lock_back_right", name="右后门锁",
        device_class=BinarySensorDeviceClass.LOCK, icon="mdi:car-door-lock"), "lock"),
    (BinarySensorEntityDescription(key="lock_trunk", name="后备箱锁",
        device_class=BinarySensorDeviceClass.LOCK, icon="mdi:car-door-lock"), "lock"),
    (BinarySensorEntityDescription(key="lock_front_trunk", name="前备箱锁",
        device_class=BinarySensorDeviceClass.LOCK, icon="mdi:car-door-lock"), "lock"),
    # ---- 车门开关（on = 打开）----
    (BinarySensorEntityDescription(key="door_main", name="主驾车门",
        device_class=BinarySensorDeviceClass.DOOR, icon="mdi:car-door"), "door"),
    (BinarySensorEntityDescription(key="door_copilot", name="副驾车门",
        device_class=BinarySensorDeviceClass.DOOR, icon="mdi:car-door"), "door"),
    (BinarySensorEntityDescription(key="door_back_left", name="左后车门",
        device_class=BinarySensorDeviceClass.DOOR, icon="mdi:car-door"), "door"),
    (BinarySensorEntityDescription(key="door_back_right", name="右后车门",
        device_class=BinarySensorDeviceClass.DOOR, icon="mdi:car-door"), "door"),
    (BinarySensorEntityDescription(key="door_trunk", name="后备箱门",
        device_class=BinarySensorDeviceClass.DOOR, icon="mdi:car-door"), "door"),
    (BinarySensorEntityDescription(key="charge_port_lid", name="充电口盖",
        icon="mdi:ev-plug-type2"), "door"),
    (BinarySensorEntityDescription(key="tank_lock", name="油箱盖",
        icon="mdi:gas-station"), "door"),
    # ---- 充电枪（on = 已连接）----
    (BinarySensorEntityDescription(key="charge_gun_ac", name="交流充电枪",
        device_class=BinarySensorDeviceClass.PLUG, icon="mdi:power-plug"), "plug"),
    (BinarySensorEntityDescription(key="charge_gun_dc", name="直流充电枪",
        device_class=BinarySensorDeviceClass.PLUG, icon="mdi:power-plug-outline"), "plug"),
    # ---- 连接（on = 已连接）----
    (BinarySensorEntityDescription(key="online_5g", name="5G 连接",
        device_class=BinarySensorDeviceClass.CONNECTIVITY, icon="mdi:signal-5g"), "conn"),
    (BinarySensorEntityDescription(key="online_xcu", name="XCU 连接",
        device_class=BinarySensorDeviceClass.CONNECTIVITY, icon="mdi:chip"), "conn"),
    # ---- 告警（on = 告警）----
    (BinarySensorEntityDescription(key="tire_fl_warning", name="胎压告警 左前",
        device_class=BinarySensorDeviceClass.PROBLEM, icon="mdi:car-tire-alert"), "warn"),
    (BinarySensorEntityDescription(key="tire_fr_warning", name="胎压告警 右前",
        device_class=BinarySensorDeviceClass.PROBLEM, icon="mdi:car-tire-alert"), "warn"),
    (BinarySensorEntityDescription(key="tire_rl_warning", name="胎压告警 左后",
        device_class=BinarySensorDeviceClass.PROBLEM, icon="mdi:car-tire-alert"), "warn"),
    (BinarySensorEntityDescription(key="tire_rr_warning", name="胎压告警 右后",
        device_class=BinarySensorDeviceClass.PROBLEM, icon="mdi:car-tire-alert"), "warn"),
    (BinarySensorEntityDescription(key="tpms_status", name="TPMS 系统告警",
        device_class=BinarySensorDeviceClass.PROBLEM, icon="mdi:car-tire-alert"), "warn"),
    (BinarySensorEntityDescription(key="charge_fault", name="充电故障",
        device_class=BinarySensorDeviceClass.PROBLEM, icon="mdi:alert-circle"), "warn"),
    (BinarySensorEntityDescription(key="fuel_low_warning", name="油量低告警",
        device_class=BinarySensorDeviceClass.PROBLEM, icon="mdi:fuel-alert"), "warn"),
    (BinarySensorEntityDescription(key="low_vol_flag", name="低压电源标志",
        icon="mdi:flag"), "warn"),
    # ---- 功能开关（on = 开启）----
    (BinarySensorEntityDescription(key="scheduled_charge_switch", name="预约充电",
        icon="mdi:calendar-clock"), "heat"),
    (BinarySensorEntityDescription(key="wheel_heat", name="方向盘加热",
        icon="mdi:steering"), "heat"),
    (BinarySensorEntityDescription(key="provision_auth", name="车辆授权",
        icon="mdi:key-check"), "conn"),
    # ---- JSON 字段判读 ----
    (BinarySensorEntityDescription(key="sentry", name="哨兵模式",
        icon="mdi:shield-car"), "json:sentinelStatus"),
    (BinarySensorEntityDescription(key="sentry_switch", name="哨兵开关",
        icon="mdi:shield-check"), "json:sentinelSwitch"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    vin = config_entry.data.get(CONF_VIN) or ""
    identifiers = {(DOMAIN, vin)} if vin else {(DOMAIN, config_entry.entry_id)}
    device_info = DeviceInfo(
        identifiers=identifiers, manufacturer="理想汽车",
        model="理想 L6" if vin else "理想汽车",
        name="Li Auto L6" if vin else "Li Auto",
    )
    if vin:
        device_info["serial_number"] = vin
    async_add_entities(
        LiCarBinarySensor(coordinator, desc, kind, vin, device_info)
        for desc, kind in BINARY_DESCRIPTIONS
    )


class LiCarBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """理想车二元传感器（值来自 coordinator.data["vss"]）"""

    _attr_has_entity_name = True

    def __init__(self, coordinator, description, kind: str, vin: str,
                 device_info=None) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._rid = route_id_of_vin(vin)

        self._attr_unique_id = f"{DOMAIN}_{self._rid}_{description.key}"
        if device_info is not None:
            self._attr_device_info = device_info
        self._kind = kind

    @property
    def is_on(self) -> bool | None:
        sig = (self.coordinator.data or {}).get("vss", {}).get(
            self.entity_description.key)
        if sig is None or sig.get("value") is None:
            return None
        val = sig.get("value")
        kind = self._kind

        # JSON 字段
        if kind.startswith("json:"):
            field = kind.split(":", 1)[1]
            try:
                obj = json.loads(val) if isinstance(val, str) else val
                return int(obj.get(field, 0)) != 0
            except (TypeError, ValueError, AttributeError):
                return None

        # 布尔直读
        if isinstance(val, bool):
            return val

        try:
            n = int(val)
        except (TypeError, ValueError):
            try:
                return bool(val)
            except Exception:
                return None

        if kind == "lock":
            return n != 0                     # 0=已落锁 → on=未落锁
        if kind == "door":
            # ★ 2026-09-23 修复：不同门信号的语义不同
            #   App 源码（LXLiMeshStateDelegate.getTrunkState）还原：
            #     · 优先用 DoorLockStatus.TrunkDoor：0=关闭，其他=打开
            #     · 无 lock 时用 DoorSwitchStatus.TrunkDoor：0/2/3=关闭，1=打开
            #   实测：L6 的后备箱 DoorSwitchStatus.TrunkDoor 恒为 2
            #         （旧代码把 2 判成"打开"→ 一直显示 on）
            key = self.entity_description.key
            if key in ("door_trunk",):
                return n == 1                 # 0/2/3=关闭，1=打开
            return n != 0                     # 其他车门：0=关闭
        if kind == "plug":
            return n != 0                     # 0=未插 → on=已连接
        if kind == "conn":
            return n != 0
        if kind == "warn":
            return n != 0                     # 0=正常 → on=告警
        if kind == "heat":
            return n != 0
        return n != 0
