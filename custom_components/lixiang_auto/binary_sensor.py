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
        device_class=BinarySensorDeviceClass.DOOR, icon="mdi:car-door"), "trunk"),
    (BinarySensorEntityDescription(key="charge_port_lid", name="充电口盖",
        icon="mdi:ev-plug-type2"), "charge_lid"),
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
    (BinarySensorEntityDescription(key="online_huf", name="车机连接",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        icon="mdi:car-connected"), "conn"),
    # ---- 充电/车辆状态（★ 2026-09-23 补充）----
    (BinarySensorEntityDescription(key="eves_flt_stop_chrg", name="故障停止充电",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:alert-circle"), "warn"),
    (BinarySensorEntityDescription(key="battery_insulation", name="电池保温",
        icon="mdi:thermometer-plus"), "door"),
    (BinarySensorEntityDescription(key="case_cover", name="钥匙保护套",
        icon="mdi:key-variant"), "door"),
    (BinarySensorEntityDescription(key="dcdc_fault_level", name="DCDC 故障",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:alert-octagon"), "warn"),
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
            # ★ 2026-09-23 从 App 源码还原（XDoorDataHandle）：
            #   所有 DoorSwitchStatus.* 的统一语义是「== 1 才算打开」：
            #
            #     int v = toInt(doorValue);
            #     boolean open = (v == 1);        // 只有 1 → true
            #     model.setXxxDoorState(open);
            #
            #   尾门的额外证据：
            #     XHttpOpenTrunkControl  → 等 v == 1 视为开成功
            #     XHttpCloseTrunkControl → 等 v == 2 视为关成功
            #
            #   ⚠️ 旧实现用 `n != 0`，会把尾门的 2 误判成「打开」。
            return n == 1
        if kind == "trunk":
            # ★ 尾门聚合（复刻 App 的 LXLiMeshStateDelegate.getTrunkState()
            #   smali:37730-37930）：
            #
            #     if (lockVal != null) {
            #         return convertAnyToInt(lockVal) == 0 ? 0 : 1;   // Lock 优先
            #     }
            #     int v = convertAnyToInt(switchVal);
            #     return (v == 2 || v == 0 || v == 3) ? 0 : 1;        // Switch 兜底
            #
            #   即：有锁信号时以【锁】为准（0=关，非0=开）；
            #       否则用开关信号（0/2/3=关，1=开）。
            #
            #   ★ 实测（2026-09-23 实车）：
            #       DoorLockStatus.TrunkDoor   = 0  （已上锁 → 关）
            #       DoorSwitchStatus.TrunkDoor = 2  （关）
            #     两者一致，聚合后判定为「关闭」。
            lock_sig = (self.coordinator.data or {}).get("vss", {}).get(
                self.entity_description.key.replace("door_trunk", "lock_trunk"))
            if lock_sig and lock_sig.get("value") is not None:
                try:
                    return int(lock_sig["value"]) != 0
                except (TypeError, ValueError):
                    pass
            return n != 0 if n in (0, 1) else (n == 1)
        if kind == "plug":
            # ★ 2026-09-23 源码：App 用 ACChgrActualConnSts == 2 判"已插枪"
            #   （XChargeDataHandle.smali:102）
            #   ⚠️ 值 1 的确切含义未在源码中显式标注（可能"握手中"），
            #      所以保留 n != 0 的宽松判定 + translations 标注 1 为"连接中"
            return n != 0                     # 0=未插 → on=已连接
        if kind == "charge_lid":
            # ★ 2026-09-23：ChrgPorLidStsV2 用 -1 作【无效哨兵】
            #   （LXLiMeshStateDelegate.getChrgPorLidSts() smali:11921/11972）
            #   → -1 应映射为 unknown（None），不是"关闭"
            if n == -1:
                return None
            return n != 0                     # 0=关闭，非0=打开
        if kind == "conn":
            return n != 0
        if kind == "warn":
            return n != 0                     # 0=正常 → on=告警
        if kind == "heat":
            return n != 0
        return n != 0
