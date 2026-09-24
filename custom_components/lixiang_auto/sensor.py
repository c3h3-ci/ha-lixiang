"""Li Auto 传感器实体（110 个信号）.

- online_status: basics.vehicleStatus 在线标记
- 实时信号 (vss/get-batch): 电池/充电/续航/车门/空调/座椅/轮胎/位置...

VSS 路径全集见 docs/VSS路径全集_20260922.md
"""

from __future__ import annotations

import json
from datetime import datetime
import logging
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    STATE_UNKNOWN,
    UnitOfTemperature,
    UnitOfPressure,
    UnitOfLength,
    UnitOfSpeed,
    UnitOfPower,
    UnitOfElectricPotential,
    UnitOfElectricCurrent,
    UnitOfTime,
    PERCENTAGE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_VIN, DOMAIN, LOGGER_NAME
from .entity_helper import route_id_of_vin

_LOGGER = logging.getLogger(LOGGER_NAME)

# 单位名 → HA 常量
_UNITS = {
    "PERCENTAGE": PERCENTAGE, "°C": UnitOfTemperature.CELSIUS,
    "kPa": UnitOfPressure.KPA, "km": UnitOfLength.KILOMETERS,
    "km/h": UnitOfSpeed.KILOMETERS_PER_HOUR, "kW": UnitOfPower.KILO_WATT,
    "V": UnitOfElectricPotential.VOLT, "A": UnitOfElectricCurrent.AMPERE,
    "min": UnitOfTime.MINUTES, "%": PERCENTAGE,
    "L": "L",           # 油量升

}
_DCLASS = {
    "BATTERY": SensorDeviceClass.BATTERY,
    "TEMPERATURE": SensorDeviceClass.TEMPERATURE,
    "PRESSURE": SensorDeviceClass.PRESSURE,
    "DISTANCE": SensorDeviceClass.DISTANCE,
    "SPEED": SensorDeviceClass.SPEED,
    "POWER": SensorDeviceClass.POWER,
    "VOLTAGE": SensorDeviceClass.VOLTAGE,
    "CURRENT": SensorDeviceClass.CURRENT,
    "DURATION": SensorDeviceClass.DURATION,
}
_SCLASS = {
    "MEASUREMENT": SensorStateClass.MEASUREMENT,
    "TOTAL": SensorStateClass.TOTAL,
    "TOTAL_INCREASING": SensorStateClass.TOTAL_INCREASING,
}


# ★ 诊断类实体（借自 huawei-auto-cloud 的 EntityCategory 用法）
#   这些是"排查/元数据"类信息，不是日常关心的状态 →
#   归入 HA 的「诊断」分组，设备页面自动折叠，界面清爽。
_DIAGNOSTIC_CATS = frozenset({
    "OTA", "保养", "信息", "设置", "电源",
})
_DIAGNOSTIC_KEYS = frozenset({
    "config_code", "provision_auth", "hu_diag", "ota_version", "ota_short",
    "ota_state", "ota_status", "ota_progress", "maint_acfilter",
    "maint_coolfuild", "maint_engine_oil", "maint_brake_oil", "maint_sparkplug",
    "low_vol_flag", "low_vol_mode", "battery_keep_warm",
})


def _mk(key, spec):
    name, dclass, unit, sclass, icon, cat = spec
    kw = dict(key=key, name=name, icon=icon)
    if dclass in _DCLASS: kw["device_class"] = _DCLASS[dclass]
    if unit in _UNITS: kw["native_unit_of_measurement"] = _UNITS[unit]
    if sclass in _SCLASS: kw["state_class"] = _SCLASS[sclass]
    # ★ 诊断类实体归入 EntityCategory.DIAGNOSTIC（设备页面折叠显示）
    if cat in _DIAGNOSTIC_CATS or key in _DIAGNOSTIC_KEYS:
        kw["entity_category"] = EntityCategory.DIAGNOSTIC
        # ★ 诊断类默认不启用（减少新用户第一屏噪音，需要时手动启用）
        kw["entity_registry_enabled_default"] = False
    return SensorEntityDescription(**kw)


SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(key="online_status", name="在线状态", icon="mdi:car-connected"),
    # ---- 电池 ----
    _mk("battery_level", ('电池电量', 'BATTERY', 'PERCENTAGE', 'MEASUREMENT', 'mdi:battery-high', '电池')),
    _mk("charge_status", ('充电状态', None, None, None, 'mdi:ev-station', '电池')),
    _mk("charge_power_cltc", ('充电功率(CLTC)', 'POWER', 'kW', 'MEASUREMENT', 'mdi:flash', '电池')),
    _mk("charge_power_wltc", ('充电功率(WLTC)', 'POWER', 'kW', 'MEASUREMENT', 'mdi:flash', '电池')),
    _mk("charge_voltage_ac", ('充电电压(AC)', 'VOLTAGE', 'V', 'MEASUREMENT', 'mdi:sine-wave', '电池')),
    _mk("charge_current_ac", ('充电电流(AC)', 'CURRENT', 'A', 'MEASUREMENT', 'mdi:current-ac', '电池')),
    _mk("battery_pack_voltage", ('电池包电压', 'VOLTAGE', 'V', 'MEASUREMENT', 'mdi:car-battery', '电池')),
    _mk("charge_remain_time", ('剩余充电时间', 'DURATION', 'min', 'MEASUREMENT', 'mdi:timer-sand', '电池')),
    _mk("charge_complete", ('充电完成状态', None, None, None, 'mdi:battery-check', '电池')),
    _mk("discharge_status", ('放电状态', None, None, None, 'mdi:battery-minus', '电池')),
    # ---- 充电桩 ----
    _mk("charge_limit", ('充电上限', None, '%', None, 'mdi:battery-charging-80', '充电桩')),
    _mk("scheduled_charge_state", ('预约充电状态', None, None, None, 'mdi:calendar-check', '充电桩')),
    _mk("scheduled_charge_start", ('预约开始时间', None, None, None, 'mdi:clock-start', '充电桩')),
    _mk("scheduled_charge_end", ('预约结束时间', None, None, None, 'mdi:clock-end', '充电桩')),
    # ---- 续航 ----
    _mk("range_elec_cltc", ('纯电续航(CLTC)', 'DISTANCE', 'km', 'MEASUREMENT', 'mdi:map-marker-distance', '续航')),
    _mk("range_fuel_cltc", ('燃油续航(CLTC)', 'DISTANCE', 'km', 'MEASUREMENT', 'mdi:gas-station', '续航')),
    _mk("range_elec_wltc", ('纯电续航(WLTC)', 'DISTANCE', 'km', 'MEASUREMENT', 'mdi:map-marker-distance', '续航')),
    _mk("range_fuel_wltc", ('燃油续航(WLTC)', 'DISTANCE', 'km', 'MEASUREMENT', 'mdi:gas-station', '续航')),
    _mk("fuel_level", ('油量', None, 'L', 'MEASUREMENT', 'mdi:fuel', '续航')),
    # ---- 车门 ----
    # ---- 车窗 ----
    _mk("window_main", ('主驾车窗', None, '%', None, 'mdi:car-door', '车窗')),
    # ⚠️ window_skylight 移除了：L6 实测 SkylightWindow 返回 None
    #    （该车型可能无天窗，或信号名不同 —— 保留 VSS 路径供其他车型用）
    # ★ 2026-09-23 补充（task-14 高价值遗漏）
    _mk("low_vol_status", ('低压电源状态', None, None, None, 'mdi:car-battery', '电池')),
    # ⚠️ mileage_final 移除了：L6 实测 MileageFinalResult 返回 None
    _mk("battery_type", ('电池类型', None, None, None, 'mdi:battery-sync', '电池')),
    _mk("charge_order_mode", ('预约充电模式', None, None, None, 'mdi:calendar-clock', '充电桩')),
    _mk("window_copilot", ('副驾车窗', None, '%', None, 'mdi:car-door', '车窗')),
    _mk("window_back_left", ('左后车窗', None, '%', None, 'mdi:car-door', '车窗')),
    _mk("window_back_right", ('右后车窗', None, '%', None, 'mdi:car-door', '车窗')),
    _mk("sunshade", ('遮阳帘', None, None, None, 'mdi:window-shutter', '车窗')),
    # ---- 空调 ----
    _mk("inside_temp", ('车内温度', 'TEMPERATURE', '°C', 'MEASUREMENT', 'mdi:thermometer', '空调')),
    _mk("ac_set_temp", ('空调设定温度', 'TEMPERATURE', '°C', None, 'mdi:thermostat', '空调')),
    _mk("ac_wind_mode", ('风向模式', None, None, None, 'mdi:weather-windy', '空调')),
    _mk("ac_defrost", ('除霜模式', None, None, None, 'mdi:snowflake-melt', '空调')),
    _mk("ac_fan_speed", ('快冷快热', None, None, None, 'mdi:fan', '空调')),
    # ---- 座椅 ----
    _mk("seat_fl_heat", ('主驾座椅加热', None, None, None, 'mdi:car-seat-heater', '座椅')),
    _mk("seat_fl_vent", ('主驾座椅通风', None, None, None, 'mdi:car-seat-cooler', '座椅')),
    _mk("seat_fr_heat", ('副驾座椅加热', None, None, None, 'mdi:car-seat-heater', '座椅')),
    _mk("seat_fr_vent", ('副驾座椅通风', None, None, None, 'mdi:car-seat-cooler', '座椅')),
    _mk("seat_sl_heat", ('二排左座椅加热', None, None, None, 'mdi:car-seat-heater', '座椅')),
    _mk("seat_sr_heat", ('二排右座椅加热', None, None, None, 'mdi:car-seat-heater', '座椅')),
    _mk("seat_sm_heat", ('二排中座椅加热', None, None, None, 'mdi:car-seat-heater', '座椅')),
    _mk("seat_tl_heat", ('三排左座椅加热', None, None, None, 'mdi:car-seat-heater', '座椅')),
    _mk("seat_tr_heat", ('三排右座椅加热', None, None, None, 'mdi:car-seat-heater', '座椅')),
    # ★ 2026-09-23 补充（task-14 高价值遗漏）
    _mk("seat_sl_vent", ('二排左座椅通风', None, None, None, 'mdi:car-seat-cooler', '座椅')),
    _mk("seat_sr_vent", ('二排右座椅通风', None, None, None, 'mdi:car-seat-cooler', '座椅')),
    _mk("seat_tl_vent", ('三排左座椅通风', None, None, None, 'mdi:car-seat-cooler', '座椅')),
    _mk("seat_tr_vent", ('三排右座椅通风', None, None, None, 'mdi:car-seat-cooler', '座椅')),
    _mk("seat_tm_heat", ('三排中座椅加热', None, None, None, 'mdi:car-seat-heater', '座椅')),
    # ---- 冰箱 ----
    _mk("fridge_status", ('冰箱工作状态', None, None, None, 'mdi:fridge', '冰箱')),
    _mk("fridge_mode", ('冰箱模式', None, None, None, 'mdi:fridge-outline', '冰箱')),
    _mk("fridge_cool_temp", ('冰箱制冷温度', None, None, None, 'mdi:snowflake', '冰箱')),
    _mk("fridge_remain_time", ('冰箱剩余时间', 'DURATION', 'min', None, 'mdi:timer', '冰箱')),
    # ---- 轮胎 ----
    _mk("tire_fl", ('胎压 左前', 'PRESSURE', 'kPa', 'MEASUREMENT', 'mdi:car-tire-alert', '轮胎')),
    _mk("tire_fr", ('胎压 右前', 'PRESSURE', 'kPa', 'MEASUREMENT', 'mdi:car-tire-alert', '轮胎')),
    _mk("tire_rl", ('胎压 左后', 'PRESSURE', 'kPa', 'MEASUREMENT', 'mdi:car-tire-alert', '轮胎')),
    _mk("tire_rr", ('胎压 右后', 'PRESSURE', 'kPa', 'MEASUREMENT', 'mdi:car-tire-alert', '轮胎')),
    _mk("tire_fl_temp", ('胎温 左前', 'TEMPERATURE', '°C', 'MEASUREMENT', 'mdi:thermometer-lines', '轮胎')),
    _mk("tire_fr_temp", ('胎温 右前', 'TEMPERATURE', '°C', 'MEASUREMENT', 'mdi:thermometer-lines', '轮胎')),
    _mk("tire_rl_temp", ('胎温 左后', 'TEMPERATURE', '°C', 'MEASUREMENT', 'mdi:thermometer-lines', '轮胎')),
    _mk("tire_rr_temp", ('胎温 右后', 'TEMPERATURE', '°C', 'MEASUREMENT', 'mdi:thermometer-lines', '轮胎')),
    # ---- 位置 ----
    _mk("speed", ('车速', 'SPEED', 'km/h', 'MEASUREMENT', 'mdi:speedometer', '位置')),
    # ---- 连接 ----
    # ---- OTA ----
    _mk("ota_version", ('车机版本', None, None, None, 'mdi:car-info', 'OTA')),
    _mk("ota_short", ('车机版本(短)', None, None, None, 'mdi:car-info', 'OTA')),
    _mk("ota_state", ('OTA 状态', None, None, None, 'mdi:download', 'OTA')),
    _mk("ota_status", ('OTA 结果', None, None, None, 'mdi:download-circle', 'OTA')),
    _mk("ota_progress", ('OTA 进度', None, '%', None, 'mdi:progress-download', 'OTA')),
    # ---- 哨兵 ----
    _mk("sentry_video_count", ('哨兵视频数', None, None, 'MEASUREMENT', 'mdi:video', '哨兵')),
    # ---- 保养 ----
    _mk("maint_acfilter", ('空调滤芯', None, None, None, 'mdi:air-filter', '保养')),
    _mk("maint_coolfuild", ('冷却液', None, None, None, 'mdi:coolant-temperature', '保养')),
    _mk("maint_engine_oil", ('机油', None, None, None, 'mdi:oil', '保养')),
    _mk("maint_brake_oil", ('刹车油', None, None, None, 'mdi:car-brake-fluid-level', '保养')),
    _mk("maint_sparkplug", ('火花塞', None, None, None, 'mdi:flash', '保养')),
    _mk("trip_total", ('行程总计', None, None, None, 'mdi:counter', '保养')),
    # ---- 空气 ----
    _mk("air_pollution", ('空气污染指数', None, None, 'MEASUREMENT', 'mdi:air-filter', '空气')),
    _mk("low_battery_mode", ('低电量模式', None, None, None, 'mdi:battery-low', '空气')),
    _mk("travel_status", ('行驶状态', None, None, None, 'mdi:car-cruise-control', '空气')),
    # ---- 灯光 ----
    _mk("light_lic", ('牌照灯', None, None, None, 'mdi:lightbulb', '灯光')),
    _mk("mirror_left", ('左后视镜', None, None, None, 'mdi:mirror', '灯光')),
    _mk("mirror_right", ('右后视镜', None, None, None, 'mdi:mirror', '灯光')),
    # ---- 电源 ----
    _mk("low_vol_mode", ('低压电源模式', None, None, None, 'mdi:power-plug-battery', '电源')),
    # ---- 影像 ----
    _mk("svm_photo_state", ('360 拍照状态', None, None, None, 'mdi:camera', '影像')),
    _mk("svm_filekey", ('360 拍照信息', None, None, None, 'mdi:image', '影像')),
    # ---- 信息 ----
    _mk("config_code", ('车辆配置', None, None, None, 'mdi:car-cog', '信息')),
    _mk("hu_diag", ('车机诊断', None, None, None, 'mdi:stethoscope', '信息')),
    # ---- 设置 ----
    _mk("privacy_pos_service", ('位置服务', None, None, None, 'mdi:map-marker-radius', '设置')),
    _mk("scene_mode", ('场景模式', None, None, None, 'mdi:palette', '设置')),
    # ---- 电池 ----
    _mk("battery_keep_warm", ('电池预热', None, None, None, 'mdi:fire', '电池')),
    # ---- 泊车 ----
    _mk("park_status", ('泊车状态', None, None, None, 'mdi:parking', '泊车')),
    _mk("park_fsd_progress", ('泊车启动进度', None, None, None, 'mdi:progress-clock', '泊车')),
)


# vehicleInfo 中适合展示为属性的字段
_VEHICLE_INFO_ATTRS = (
    ("carSeries", "车系"), ("spu", "车型"), ("plateNumber", "车牌"),
    ("vehicleNickname", "昵称"), ("color", "颜色"), ("seat", "座椅"),
    ("wheelName", "轮毂"), ("interiorName", "内饰"), ("deviceId", "车机设备号"),
    ("materialNumber", "物料号"), ("modelNo", "型号"), ("variableModel", "配置"),
    ("isSupportBle", "支持蓝牙钥匙"), ("usageType", "用途类型"),
)


# ---------- 车型功能过滤 (2026-09-23) ----------
# 信号 key 前缀 → 所属功能（features 由 __init__.py 探测）
# 未列出的 key 一律创建（通用信号）
FEATURE_BY_KEY_PREFIX: dict[str, str] = {
    "fridge": "冰箱",
    "sentry": "哨兵模式",
    "lock_front_trunk": "前备箱",
    # ★ 2026-09-24 修复：座椅映射不完整
    #   问题：L6（五座）也创建了三排座椅实体
    #   原因：
    #     ① "seat_tl"/"seat_tr"/"seat_tm"/"seat_sm" 缺映射 → 不受功能过滤
    #     ② 服务端对不存在的三排硬件也返回 value=0 + 有效 ts
    #        → 信号探测无法区分 → 必须靠车型判断
    #
    #   座椅代号：F=Front(前) S=Second(二排) T=Third(三排)
    #             L=Left R=Right M=Middle
    "seat_sl": "二排座椅",
    "seat_sr": "二排座椅",
    "seat_sm": "二排座椅",     # ★ 二排中（L6 有，L8/L9 无）
    "seat_tl": "三排座椅",     # ★ 三排左（仅 L8/L9/MEGA）
    "seat_tr": "三排座椅",     # ★ 三排右
    "seat_tm": "三排座椅",     # ★ 三排中
    "wheel_heat": "方向盘加热",
    "spoiler": "电动尾翼",
    "suspension": "空气悬架",
}


def _feature_of(key: str) -> str | None:
    """根据信号 key 判断所属功能；None 表示通用信号（始终创建）。"""
    for prefix, feat in FEATURE_BY_KEY_PREFIX.items():
        if key == prefix or key.startswith(prefix + "_"):
            return feat
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """设置传感器，并注册"理想L6"设备."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    vin = config_entry.data.get(CONF_VIN) or ""

    identifiers = {(DOMAIN, vin)} if vin else {(DOMAIN, config_entry.entry_id)}
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers=identifiers,
        name="Li Auto L6" if vin else "Li Auto",
        manufacturer="理想汽车",
        model="理想 L6",
    )
    device_info = DeviceInfo(
        identifiers=identifiers, manufacturer="理想汽车",
        model="理想 L6", name="Li Auto L6" if vin else "Li Auto",
    )

    # ★ 2026-09-24 接入 signals.py（架构方案 2.4）
    #   描述表改由 SIGNALS 生成 —— 新增信号只需在 signals.py 加一行。
    #
    #   等价性：已验证 signals.py 的 78 个 sensor 与旧 _mk 表
    #          在 name/icon/category/diagnostic 上完全一致
    #          （见 tests/test_signals.py::TestDescriptionEquivalence）
    features = (hass.data[DOMAIN][config_entry.entry_id].get("features") or {})
    from .signals import to_sensor_descriptions
    keep, skipped = [], []
    for desc in to_sensor_descriptions():
        key = getattr(desc, "key", "") or ""
        feat = _feature_of(key)
        if feat and not features.get(feat, True):
            skipped.append(f"{key}({feat})")
            continue
        keep.append(desc)
    if skipped:
        _LOGGER.info("车型不支持, 跳过传感器 %d 个: %s", len(skipped), skipped[:8])

    entities = [
        LiCarSensor(coordinator, desc, device_info, vin) for desc in keep
    ]
    async_add_entities(entities)


def _vehicle_info(data: dict) -> dict:
    """从 coordinator.data 提取 vehicleInfo 字典."""
    basics = data.get("basics")
    if isinstance(basics, dict):
        vi = basics.get("vehicleInfo")
        if isinstance(vi, dict):
            return vi
    vehicles = data.get("vehicles") or []
    if vehicles and isinstance(vehicles[0], dict):
        vi = vehicles[0].get("vehicleInfo")
        if isinstance(vi, dict):
            return vi
    return {}


def _signal_age(ts: str | None) -> str | None:
    """把上报时间戳转成可读的年龄字符串（如 "5 分钟前" / "3 天前"）。

    ★ 2026-09-23：用于 extra_state_attributes —— 让用户能判断数据是否新鲜，
      而不改变实体状态（避免"实体突然变 unknown"的负面体验）。

    ts 格式："2026-09-23 20:15:32"（VSS 的 tsFormat）
    返回 None 表示 ts 无效（空/0/无法解析）。
    """
    if not ts:
        return None
    t = str(ts).strip()
    if t in ("", "0"):
        return None
    try:
        dt = datetime.strptime(t[:19], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None
    delta = datetime.now() - dt
    secs = int(delta.total_seconds())
    if secs < 0:
        return "刚刚"
    if secs < 60:
        return f"{secs} 秒前"
    if secs < 3600:
        return f"{secs // 60} 分钟前"
    if secs < 86400:
        return f"{secs // 3600} 小时前"
    days = secs // 86400
    if days < 30:
        return f"{days} 天前"
    if days < 365:
        return f"{days // 30} 个月前"
    return f"{days // 365} 年前"



class LiCarSensor(CoordinatorEntity, RestoreSensor):
    """理想车传感器 (在线状态 + 实时信号)"""

    _attr_has_entity_name = True

    def __init__(self, coordinator, description, device_info, vin: str) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._rid = route_id_of_vin(vin)

        self._attr_unique_id = f"{DOMAIN}_{self._rid}_{description.key}"
        self._attr_device_info = device_info
        # ★ 断连保留最后有效值（借自 huawei-auto-cloud 的 sticky 设计）
        self._last_value: Any = None
        self._last_ts: str | None = None

    def _vss(self) -> dict | None:
        """当前 key 的 VSS 信号 {"value":..,"ts":..}, 无数据返回 None."""
        return (self.coordinator.data or {}).get("vss", {}).get(
            self.entity_description.key)

    def _compute_value(self):
        """计算实体值（★ 2026-09-23 已抽到 rendering.render_value，便于单测）。

        这里只负责取数，渲染逻辑全在 rendering.py（纯函数）。
        """
        from .rendering import render_value

        key = self.entity_description.key
        data = self.coordinator.data or {}
        sig = self._vss()
        val = sig.get("value") if isinstance(sig, dict) else None
        return render_value(key, val, sig, data)

    @property
    def native_value(self):
        """★ sticky 包装：优先当前值，无值时回退上次有效值。

        借自 huawei-auto-cloud 的 sticky 设计：
        车辆离线/信号缺失时保留最后一帧有效数据，
        避免 HA 界面出现大片 unknown。
        """
        v = self._compute_value()
        # ★ 数值型实体不能返回字符串（HA 会报 int()/float() 转换失败）
        #   因此把 STATE_UNKNOWN 哨兵统一转成 None
        if v == STATE_UNKNOWN or v == "unknown":
            v = None
        # ★ 2026-09-23 信号新鲜度（ROADMAP P1）：
        #   VSS 的 ts 能反映信号是否真的在上报：
        #     ts == "0"  → 从未上报（硬件不存在，如 L6 无冰箱）
        #     无 ts      → 同 ts==0
        #   → 这类实体的值即使非 None 也无意义（多为默认 0），
        #     标为 unavailable 而不是显示误导性的 0。
        #
        #   ⚠️ 保守策略：只处理 ts=="0"（确定的"从未上报"）。
        #      ts 陈旧但仍有效的信号（如 config_code 两年没变）
        #      不做判定 —— 那些值是真有效的，只是不常变。
        #      陈旧程度通过 extra_state_attributes 的「上报时间」暴露。
        sig_now = self._vss()
        if sig_now is not None:
            ts = str(sig_now.get("ts") or "").strip()
            if ts in ("", "0"):
                # 从未上报：只有历史有效值时才回退（否则 unavailable）
                if self._last_value is None:
                    return None
        else:
            # ★ 2026-09-24 修复：非 VSS 信号（如 online_status）跳过此判定
            #   它的 _vss() 恒为 None → ts="" → 会被误判为"从未上报"
            #   → 永远显示 unknown（实测踩坑：在线状态一直 unknown）
            ts = ""

        if v is not None:
            self._last_value = v
            self._last_ts = ts
            return v
        # 无新值 → 回退最后有效值
        if self._last_value is not None:
            return self._last_value
        # ★ 无历史值：数值类实体返回 None（HA 显示 unknown）
        #   不能返回字符串 "unknown"，否则会被 HA 校验拒绝
        return None

    @property
    def extra_state_attributes(self) -> dict:
        attrs: dict = {}
        vi = _vehicle_info(self.coordinator.data or {})
        for key, label in _VEHICLE_INFO_ATTRS:
            if key in vi and vi[key] not in (None, ""):
                attrs[label] = vi[key]
        sig = self._vss()
        if sig:
            ts = sig.get("ts")
            attrs["上报时间"] = ts
            # ★ 2026-09-23：暴露信号年龄（便于判断数据是否新鲜）
            age = _signal_age(ts)
            if age is not None:
                attrs["数据年龄"] = age
        polled = (self.coordinator.data or {}).get("vss_polled_at")
        if polled:
            attrs["轮询时间"] = polled
        key = self.entity_description.key
        if key == "location":
            loc_sig = (self.coordinator.data or {}).get("vss", {}).get("location")
            if loc_sig and isinstance(loc_sig.get("value"), str):
                try:
                    loc = json.loads(loc_sig["value"])
                    attrs.update({
                        "纬度": loc.get("lat"), "经度": loc.get("lon"),
                        "海拔": loc.get("alt"), "朝向": loc.get("dir"),
                        "速度": loc.get("spd"), "GPS时间": loc.get("utc"),
                    })
                except (ValueError, TypeError):
                    pass
        elif key in ("ota_state", "ota_status"):
            sig2 = self._vss()
            if sig2 and isinstance(sig2.get("value"), str):
                try:
                    o = json.loads(sig2["value"])
                    for k2, label in (("currentVersion", "当前版本"), ("displayTargetVersion", "目标版本"),
                                      ("errorType", "错误类型"), ("status", "状态"),
                                      ("progress", "进度"), ("remainingSeconds", "剩余秒数"),
                                      ("addInfo", "附加信息")):
                        if o.get(k2) not in (None, ""):
                            attrs[label] = o[k2]
                except (ValueError, TypeError):
                    pass
        elif key in ("maint_acfilter", "maint_coolfuild", "maint_engine_oil",
                     "maint_brake_oil", "maint_sparkplug"):
            sig2 = self._vss()
            if sig2 and isinstance(sig2.get("value"), str):
                try:
                    o = json.loads(sig2["value"])
                    for k2, label in (("engineMileage", "发动机里程"), ("higherLevel", "上限"),
                                      ("lowerLevel", "下限"), ("percentage", "剩余百分比"),
                                      ("remainMileage", "剩余里程"), ("dateColor", "状态色")):
                        if o.get(k2) not in (None, ""):
                            attrs[label] = o[k2]
                except (ValueError, TypeError):
                    pass
        elif key == "trip_total":
            sig2 = self._vss()
            if sig2 and isinstance(sig2.get("value"), str):
                try:
                    o = json.loads(sig2["value"])
                    for k2, label in (("accMileage", "辅助驾驶里程"), ("adMileage", "总里程"),
                                      ("totalMileage", "累计里程"), ("tripMileage", "本次里程")):
                        if o.get(k2) not in (None, ""):
                            attrs[label] = o[k2]
                except (ValueError, TypeError):
                    pass
        elif key == "sentry":
            sig2 = self._vss()
            if sig2 and isinstance(sig2.get("value"), str):
                try:
                    o = json.loads(sig2["value"])
                    attrs["哨兵主状态"] = o.get("sentinelStatus")
                    attrs["哨兵子状态"] = o.get("sentinelSubStatus")
                except (ValueError, TypeError):
                    pass
        elif key == "battery_keep_warm":
            sig2 = self._vss()
            if sig2 and isinstance(sig2.get("value"), str):
                try:
                    o = json.loads(sig2["value"])
                    attrs["开始时间"] = o.get("startTime")
                    attrs["结束时间"] = o.get("endTime")
                except (ValueError, TypeError):
                    pass
        elif key == "config_code":
            sig2 = self._vss()
            if sig2 and isinstance(sig2.get("value"), str):
                try:
                    o = json.loads(sig2["value"])
                    for k2, label in (("autopilot", "辅助驾驶"), ("configLevel", "配置等级"),
                                      ("electricPackage", "电动包"), ("carSeries", "车系")):
                        if o.get(k2) not in (None, ""):
                            attrs[label] = o[k2]
                except (ValueError, TypeError):
                    pass
        elif key == "svm_filekey":
            sig2 = self._vss()
            if sig2 and isinstance(sig2.get("value"), str):
                try:
                    o = json.loads(sig2["value"])
                    for k2, label in (("picProduct", "图片类型"), ("picTime", "拍照时间")):
                        if o.get(k2) not in (None, ""):
                            attrs[label] = o[k2]
                except (ValueError, TypeError):
                    pass
        return attrs
