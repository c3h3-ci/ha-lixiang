"""信号声明表（自动生成，需人工校对）

来源: /media/duola/devdata/AI-workspace/home-assistant-nas/ha-test/config/custom_components/lixiang_auto
生成: tools/gen_signals.py

⚠️ 这是【机械合并】的结果，语义需人工校对：
  · kind → semantics 的映射需逐条确认
  · 分频是根据前缀猜的，可能不准
  · 翻译需与 translations.py 对齐
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Freq(StrEnum):
    """轮询频率档位。"""
    HIGH = "high"
    MID = "mid"
    LOW = "low"


class Semantics(StrEnum):
    """值语义（决定实体平台与判定）。"""
    RAW = "raw"                # 原样输出
    LOCKED = "locked"          # 0=已锁 → on = 未落锁
    DOOR_OPEN = "door_open"    # ==1 才开（XDoorDataHandle）
    TRUNK = "trunk"            # 尾门：锁优先聚合（getTrunkState）
    PLUGGED = "plugged"        # 非0 = 已连接
    CONNECTED = "connected"    # 非0 = 已连接
    ALARM = "alarm"            # 非0 = 告警
    SWITCH_ON = "switch_on"    # 非0 = 开启
    CHARGE_LID = "charge_lid"  # -1=无效(unknown)，0=关，非0=开
    JSON_FIELD = "json_field"  # 值是 JSON，取 json_field 指定的字段判 0/1


@dataclass(frozen=True, slots=True)
class SignalSpec:
    """一个 VSS 信号的完整声明。"""
    key: str
    path: str
    name: str
    freq: Freq = Freq.HIGH
    semantics: Semantics = Semantics.RAW
    json_field: str | None = None
    device_class: str | None = None
    unit: str | None = None
    state_class: str | None = None
    icon: str | None = None
    category: str = ''
    platforms: frozenset[str] = field(default_factory=lambda: frozenset({'sensor'}))
    diagnostic: bool = False
    value_map: dict | None = None      # 值翻译（0/1 → 中文）


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  ★★★ 以下 SIGNALS 表由 tools/gen_signals.py 生成 ★★★                 ║
# ║                                                                      ║
# ║  ⚠️ 重新生成会【覆盖】这一段 —— 手工修改请放在标记之外！              ║
# ║                                                                      ║
# ║  正确做法：                                                          ║
# ║    1. 生成到临时文件：python3 tools/gen_signals.py <dir> -o /tmp/x.py ║
# ║    2. 人工 diff 后再合并                                             ║
# ║    3. 或把手工修正挪到文件末尾的 _OVERRIDES                          ║
# ╚══════════════════════════════════════════════════════════════════════╝
SIGNALS: dict[str, SignalSpec] = {
    "ac_defrost": SignalSpec(
        key="ac_defrost",
        path="Vehicle.Cabin.AC.DefrostModeStatus",
        name="除霜模式",
        freq=Freq.HIGH,
        icon="mdi:snowflake-melt",
        category="空调",
    ),  # 有翻译映射
    # ★ 2026-09-24 修正：ExSpeedStatus 的真实语义是【快冷快热】
    #   依据：App 的 LXLiMeshStateDelegate.getNeedRapidCoolheat()
    #        读的就是 LxMeshVssConstant.getExSpeedStatus()
    #
    #   ⚠️ key 保留 ac_fan_speed（避免 unique_id 变化、打断用户自动化），
    #      只把显示名改为"快冷快热"（实体 ID 不变）
    "ac_fan_speed": SignalSpec(
        key="ac_fan_speed",
        path="Vehicle.Cabin.AC.ExSpeedStatus",
        name="快冷快热",
        freq=Freq.HIGH,
        icon="mdi:fan",
        category="空调",
    ),
    "ac_on": SignalSpec(
        key="ac_on",
        path="Vehicle.Cabin.AC.FOffStatus",
        name="空调开关",
        freq=Freq.HIGH,
        icon="mdi:air-conditioner",
        platforms=frozenset(),  # ★ 空调开关信号（climate 平台用，不建实体）
    ),
    "ac_set_temp": SignalSpec(
        key="ac_set_temp",
        path="Vehicle.Cabin.AC.SetTemp",
        name="空调设定温度",
        freq=Freq.HIGH,
        device_class="TEMPERATURE",
        unit="°C",
        icon="mdi:thermostat",
        category="空调",
    ),
    "ac_wind_mode": SignalSpec(
        key="ac_wind_mode",
        path="Vehicle.Cabin.AC.WindMode",
        name="风向模式",
        freq=Freq.HIGH,
        icon="mdi:weather-windy",
        category="空调",
    ),  # 有翻译映射
    "air_pollution": SignalSpec(
        key="air_pollution",
        path="Vehicle.Cabin.AirPollutionIndex",
        name="空气污染指数",
        freq=Freq.HIGH,
        state_class="MEASUREMENT",
        icon="mdi:air-filter",
        category="空气",
    ),
    "battery_insulation": SignalSpec(
        key="battery_insulation",
        path="Vehicle.Powertrain.ChargingPile.BatteryInsulation",
        name="电池保温",
        freq=Freq.HIGH,
        semantics=Semantics.DOOR_OPEN,
        icon="mdi:thermometer-plus",
        platforms=frozenset({'binary_sensor'}),
    ),  # 有翻译映射
    "battery_keep_warm": SignalSpec(
        key="battery_keep_warm",
        path="Vehicle.APP.BMS.KeepWarm",
        name="电池预热",
        freq=Freq.LOW,
        icon="mdi:fire",
        category="电池",
        diagnostic=True,
    ),
    "battery_level": SignalSpec(
        key="battery_level",
        path="Vehicle.Powertrain.Battery.ResidueBattery",
        name="电池电量",
        freq=Freq.HIGH,
        device_class="BATTERY",
        unit="PERCENTAGE",
        state_class="MEASUREMENT",
        icon="mdi:battery-high",
        category="电池",
    ),
    "battery_pack_voltage": SignalSpec(
        key="battery_pack_voltage",
        path="Vehicle.Powertrain.Battery.MSG_RESSInterVolt",
        name="电池包电压",
        freq=Freq.HIGH,
        device_class="VOLTAGE",
        unit="V",
        state_class="MEASUREMENT",
        icon="mdi:car-battery",
        category="电池",
    ),
    "battery_type": SignalSpec(
        key="battery_type",
        path="Vehicle.Powertrain.Battery.PowerBatteryType",
        name="电池类型",
        freq=Freq.HIGH,
        icon="mdi:battery-sync",
        category="电池",
    ),  # 有翻译映射
    "case_cover": SignalSpec(
        key="case_cover",
        path="Vehicle.Body.DoorSwitchStatus.CaseCoverStatus",
        name="钥匙保护套",
        freq=Freq.HIGH,
        semantics=Semantics.DOOR_OPEN,
        icon="mdi:key-variant",
        platforms=frozenset({'binary_sensor'}),
    ),  # 有翻译映射
    "charge_complete": SignalSpec(
        key="charge_complete",
        path="Vehicle.Powertrain.Battery.VehicleChrgComplete",
        name="充电完成状态",
        freq=Freq.HIGH,
        icon="mdi:battery-check",
        category="电池",
    ),  # 有翻译映射
    "charge_current_ac": SignalSpec(
        key="charge_current_ac",
        path="Vehicle.Powertrain.Battery.ACChargeCurrent",
        name="交流充电电流",
        unit="A",
        freq=Freq.HIGH,
        icon="mdi:current-ac",
        category="充电",
    ),
    "charge_fault": SignalSpec(
        key="charge_fault",
        path="Vehicle.Powertrain.Battery.ChargeFaults",
        name="充电故障",
        freq=Freq.MID,
        semantics=Semantics.ALARM,
        device_class="PROBLEM",
        icon="mdi:alert-circle",
        platforms=frozenset({'binary_sensor'}),
    ),  # 有翻译映射
    "charge_gun_ac": SignalSpec(
        key="charge_gun_ac",
        path="Vehicle.Powertrain.Battery.ACChgrActualConnSts",
        name="交流充电枪",
        freq=Freq.MID,
        semantics=Semantics.PLUGGED,
        device_class="PLUG",
        icon="mdi:power-plug",
        platforms=frozenset({'binary_sensor'}),
    ),  # 有翻译映射
    "charge_gun_dc": SignalSpec(
        key="charge_gun_dc",
        path="Vehicle.Powertrain.Battery.DCChrgngGunActuSts",
        name="直流充电枪",
        freq=Freq.MID,
        semantics=Semantics.PLUGGED,
        device_class="PLUG",
        icon="mdi:power-plug-outline",
        platforms=frozenset({'binary_sensor'}),
    ),  # 有翻译映射
    "charge_limit": SignalSpec(
        key="charge_limit",
        path="Vehicle.Powertrain.ChargingPile.ChargingLimit",
        name="充电上限",
        freq=Freq.MID,
        unit="%",
        icon="mdi:battery-charging-80",
        category="充电桩",
    ),
    "charge_order_mode": SignalSpec(
        key="charge_order_mode",
        path="Vehicle.Powertrain.ChargingPile.ScheduledCharging.OrderChargingMode",
        name="预约充电模式",
        freq=Freq.HIGH,
        icon="mdi:calendar-clock",
        category="充电桩",
    ),  # 有翻译映射
    "charge_port_lid": SignalSpec(
        key="charge_port_lid",
        path="Vehicle.Body.DoorSwitchStatus.ChrgPorLidStsV2",
        name="充电口盖",
        freq=Freq.HIGH,
        semantics=Semantics.CHARGE_LID,
        icon="mdi:ev-plug-type2",
        platforms=frozenset({'binary_sensor'}),
    ),
    "charge_port_lid_old": SignalSpec(
        key="charge_port_lid_old",
        path="Vehicle.Body.DoorSwitchStatus.ChrgPorLidSts",
        name="充电口盖(旧信号)",
        freq=Freq.HIGH,
        icon="mdi:ev-plug-type2",
        platforms=frozenset(),  # ★ 旧版充电口盖路径（仅保留供参考）
        category="充电",
    ),
    "charge_power_cltc": SignalSpec(
        key="charge_power_cltc",
        path="Vehicle.Powertrain.Battery.CLTCChargePower",
        name="充电功率(CLTC)",
        unit="kW",
        freq=Freq.HIGH,
        icon="mdi:lightning-bolt",
        category="充电",
    ),
    "charge_power_wltc": SignalSpec(
        key="charge_power_wltc",
        path="Vehicle.Powertrain.Battery.WLTCChargePower",
        name="充电功率(WLTC)",
        unit="kW",
        freq=Freq.HIGH,
        icon="mdi:lightning-bolt",
        category="充电",
    ),
    "charge_remain_time": SignalSpec(
        key="charge_remain_time",
        path="Vehicle.Powertrain.Battery.ChargeSurplusTime",
        name="剩余充电时间",
        freq=Freq.MID,
        device_class="DURATION",
        unit="min",
        state_class="MEASUREMENT",
        icon="mdi:timer-sand",
        category="电池",
    ),
    "charge_status": SignalSpec(
        key="charge_status",
        path="Vehicle.Powertrain.Battery.ChargeStatus",
        name="充电状态",
        freq=Freq.HIGH,
        icon="mdi:ev-station",
        category="电池",
    ),  # 有翻译映射
    "charge_voltage_ac": SignalSpec(
        key="charge_voltage_ac",
        path="Vehicle.Powertrain.Battery.ACChargeVoltage",
        name="交流充电电压",
        unit="V",
        freq=Freq.HIGH,
        icon="mdi:sine-wave",
        category="充电",
    ),
    "config_code": SignalSpec(
        key="config_code",
        path="Vehicle.Information.ConfigCode",
        name="车辆配置",
        freq=Freq.LOW,
        icon="mdi:car-cog",
        category="信息",
        diagnostic=True,
    ),
    "dcdc_fault_level": SignalSpec(
        key="dcdc_fault_level",
        path="Vehicle.MSG.MSG_DCDCFltLvl",
        name="DCDC 故障",
        freq=Freq.HIGH,
        semantics=Semantics.ALARM,
        device_class="PROBLEM",
        icon="mdi:alert-octagon",
        platforms=frozenset({'binary_sensor'}),
    ),  # 有翻译映射
    "discharge_status": SignalSpec(
        key="discharge_status",
        path="Vehicle.Powertrain.Battery.DischargeStatus",
        name="放电状态",
        freq=Freq.HIGH,
        icon="mdi:battery-minus",
        category="电池",
    ),
    "door_back_left": SignalSpec(
        key="door_back_left",
        path="Vehicle.Body.DoorSwitchStatus.BackLeftDoor",
        name="左后车门",
        freq=Freq.HIGH,
        semantics=Semantics.DOOR_OPEN,
        device_class="DOOR",
        icon="mdi:car-door",
        platforms=frozenset({'binary_sensor'}),
    ),  # 有翻译映射
    "door_back_right": SignalSpec(
        key="door_back_right",
        path="Vehicle.Body.DoorSwitchStatus.BackRightDoor",
        name="右后车门",
        freq=Freq.HIGH,
        semantics=Semantics.DOOR_OPEN,
        device_class="DOOR",
        icon="mdi:car-door",
        platforms=frozenset({'binary_sensor'}),
    ),  # 有翻译映射
    "door_copilot": SignalSpec(
        key="door_copilot",
        path="Vehicle.Body.DoorSwitchStatus.CopilotDoor",
        name="副驾车门",
        freq=Freq.HIGH,
        semantics=Semantics.DOOR_OPEN,
        device_class="DOOR",
        icon="mdi:car-door",
        platforms=frozenset({'binary_sensor'}),
    ),  # 有翻译映射
    "door_main": SignalSpec(
        key="door_main",
        path="Vehicle.Body.DoorSwitchStatus.MainDoor",
        name="主驾车门",
        freq=Freq.HIGH,
        semantics=Semantics.DOOR_OPEN,
        device_class="DOOR",
        icon="mdi:car-door",
        platforms=frozenset({'binary_sensor'}),
    ),  # 有翻译映射
    "door_trunk": SignalSpec(
        key="door_trunk",
        path="Vehicle.Body.DoorSwitchStatus.TrunkDoor",
        name="后备箱门",
        freq=Freq.HIGH,
        semantics=Semantics.TRUNK,
        device_class="DOOR",
        icon="mdi:car-door",
        platforms=frozenset({'binary_sensor'}),
    ),  # 有翻译映射
    "eves_flt_stop_chrg": SignalSpec(
        key="eves_flt_stop_chrg",
        path="Vehicle.Powertrain.Battery.EVESFltStopChrg",
        name="故障停止充电",
        freq=Freq.HIGH,
        semantics=Semantics.ALARM,
        device_class="PROBLEM",
        icon="mdi:alert-circle",
        platforms=frozenset({'binary_sensor'}),
    ),  # 有翻译映射
    "fridge_cool_temp": SignalSpec(
        key="fridge_cool_temp",
        path="Vehicle.Cabin.Fridge.CoolTempSt",
        name="冰箱制冷温度",
        freq=Freq.MID,
        icon="mdi:snowflake",
        category="冰箱",
    ),
    "fridge_mode": SignalSpec(
        key="fridge_mode",
        path="Vehicle.Cabin.Fridge.ModeState",
        name="冰箱模式",
        freq=Freq.MID,
        icon="mdi:fridge-outline",
        category="冰箱",
    ),  # 有翻译映射
    "fridge_remain_time": SignalSpec(
        key="fridge_remain_time",
        path="Vehicle.Cabin.Fridge.DlyTmRemain",
        name="冰箱剩余时间",
        freq=Freq.MID,
        device_class="DURATION",
        unit="min",
        icon="mdi:timer",
        category="冰箱",
    ),
    "fridge_status": SignalSpec(
        key="fridge_status",
        path="Vehicle.Cabin.Fridge.ActWorkSts",
        name="冰箱工作状态",
        freq=Freq.MID,
        icon="mdi:fridge",
        category="冰箱",
    ),  # 有翻译映射
    "fuel_level": SignalSpec(
        key="fuel_level",
        path="Vehicle.MSG.MSG_FuelLevelPos",
        name="油量",
        freq=Freq.HIGH,
        unit="L",
        state_class="MEASUREMENT",
        icon="mdi:fuel",
        category="续航",
    ),
    "fuel_low_warning": SignalSpec(
        key="fuel_low_warning",
        path="Vehicle.MSG.MSG_FuelLevelWrnng",
        name="油量低告警",
        freq=Freq.MID,
        semantics=Semantics.ALARM,
        device_class="PROBLEM",
        icon="mdi:fuel-alert",
        platforms=frozenset({'binary_sensor'}),
    ),
    "hu_diag": SignalSpec(
        key="hu_diag",
        path="Vehicle.HU.Diag.Hpcm",
        name="车机诊断",
        freq=Freq.HIGH,
        icon="mdi:stethoscope",
        category="信息",
        diagnostic=True,
    ),
    "inside_temp": SignalSpec(
        key="inside_temp",
        path="Vehicle.Cabin.AC.FrtACIncarTemp",
        name="车内温度",
        freq=Freq.HIGH,
        device_class="TEMPERATURE",
        unit="°C",
        state_class="MEASUREMENT",
        icon="mdi:thermometer",
        category="空调",
    ),
    "light_lic": SignalSpec(
        key="light_lic",
        path="Vehicle.Body.Light.LicLghtSts",
        name="牌照灯",
        freq=Freq.HIGH,
        icon="mdi:lightbulb",
        category="灯光",
    ),  # 有翻译映射
    "location": SignalSpec(
        key="location",
        path="Vehicle.Location.CurrentLocationInfo",
        name="location",
        freq=Freq.HIGH,
        platforms=frozenset(),  # ★ 车辆位置（device_tracker 平台用，不建 sensor）
    ),
    "lock_back_left": SignalSpec(
        key="lock_back_left",
        path="Vehicle.Body.DoorLockStatus.BackLeftDoor",
        name="左后门锁",
        freq=Freq.HIGH,
        semantics=Semantics.LOCKED,
        device_class="LOCK",
        icon="mdi:car-door-lock",
        platforms=frozenset({'binary_sensor'}),
    ),  # 有翻译映射
    "lock_back_right": SignalSpec(
        key="lock_back_right",
        path="Vehicle.Body.DoorLockStatus.BackRightDoor",
        name="右后门锁",
        freq=Freq.HIGH,
        semantics=Semantics.LOCKED,
        device_class="LOCK",
        icon="mdi:car-door-lock",
        platforms=frozenset({'binary_sensor'}),
    ),  # 有翻译映射
    "lock_copilot": SignalSpec(
        key="lock_copilot",
        path="Vehicle.Body.DoorLockStatus.CopilotDoor",
        name="副驾门锁",
        freq=Freq.HIGH,
        semantics=Semantics.LOCKED,
        device_class="LOCK",
        icon="mdi:car-door-lock",
        platforms=frozenset({'binary_sensor'}),
    ),  # 有翻译映射
    "lock_front_trunk": SignalSpec(
        key="lock_front_trunk",
        path="Vehicle.Body.DoorLockStatus.FrontTrunkDoor",
        name="前备箱锁",
        freq=Freq.HIGH,
        semantics=Semantics.LOCKED,
        device_class="LOCK",
        icon="mdi:car-door-lock",
        platforms=frozenset({'binary_sensor'}),
    ),  # 有翻译映射
    "lock_main": SignalSpec(
        key="lock_main",
        path="Vehicle.Body.DoorLockStatus.MainDoor",
        name="主驾门锁",
        freq=Freq.HIGH,
        semantics=Semantics.LOCKED,
        device_class="LOCK",
        icon="mdi:car-door-lock",
        platforms=frozenset({'binary_sensor'}),
    ),  # 有翻译映射
    "lock_trunk": SignalSpec(
        key="lock_trunk",
        path="Vehicle.Body.DoorLockStatus.TrunkDoor",
        name="后备箱锁",
        freq=Freq.HIGH,
        semantics=Semantics.LOCKED,
        device_class="LOCK",
        icon="mdi:car-door-lock",
        platforms=frozenset({'binary_sensor'}),
    ),  # 有翻译映射
    "low_battery_mode": SignalSpec(
        key="low_battery_mode",
        path="Vehicle.Cabin.LowBatteryMode",
        name="低电量模式",
        freq=Freq.MID,
        icon="mdi:battery-low",
        category="空气",
    ),  # 有翻译映射
    "low_vol_flag": SignalSpec(
        key="low_vol_flag",
        path="Vehicle.Body.Power.LowVolPwrMdFlag",
        name="低压电源标志",
        freq=Freq.MID,
        semantics=Semantics.ALARM,
        icon="mdi:flag",
        platforms=frozenset({'binary_sensor'}),
    ),  # 有翻译映射
    "low_vol_mode": SignalSpec(
        key="low_vol_mode",
        path="Vehicle.Body.Power.LowVolEngyMngtMd",
        name="低压电源模式",
        freq=Freq.MID,
        icon="mdi:power-plug-battery",
        category="电源",
        diagnostic=True,
    ),  # 有翻译映射
    "low_vol_status": SignalSpec(
        key="low_vol_status",
        path="Vehicle.Body.Power.LowVolPwrMdSts",
        name="低压电源状态",
        freq=Freq.HIGH,
        icon="mdi:car-battery",
        category="电池",
    ),  # 有翻译映射
    "maint_acfilter": SignalSpec(
        key="maint_acfilter",
        path="Vehicle.Carcenter.Maintain.acfilter",
        name="空调滤芯",
        freq=Freq.LOW,
        icon="mdi:air-filter",
        category="保养",
        diagnostic=True,
    ),
    "maint_brake_oil": SignalSpec(
        key="maint_brake_oil",
        path="Vehicle.Carcenter.Maintain.gearbrakeoil",
        name="刹车油",
        freq=Freq.LOW,
        icon="mdi:car-brake-fluid-level",
        category="保养",
        diagnostic=True,
    ),
    "maint_coolfuild": SignalSpec(
        key="maint_coolfuild",
        path="Vehicle.Carcenter.Maintain.coolfuild",
        name="冷却液",
        freq=Freq.LOW,
        icon="mdi:coolant-temperature",
        category="保养",
        diagnostic=True,
    ),
    "maint_engine_oil": SignalSpec(
        key="maint_engine_oil",
        path="Vehicle.Carcenter.Maintain.enginelevel1",
        name="机油",
        freq=Freq.LOW,
        icon="mdi:oil",
        category="保养",
        diagnostic=True,
    ),
    "maint_sparkplug": SignalSpec(
        key="maint_sparkplug",
        path="Vehicle.Carcenter.Maintain.sparkplug",
        name="火花塞",
        freq=Freq.LOW,
        icon="mdi:flash",
        category="保养",
        diagnostic=True,
    ),
    "mileage_final": SignalSpec(
        key="mileage_final",
        path="Vehicle.Cabin.CLTC.MileageFinalResult",
        name="总里程",
        unit="km",
        freq=Freq.HIGH,
        icon="mdi:counter",
        platforms=frozenset(),  # ★ L6 实测无数据（MileageFinalResult 返回 None）
    ),
    "mirror_left": SignalSpec(
        key="mirror_left",
        path="Vehicle.Body.RearMirro.LRearMirro",
        name="左后视镜",
        freq=Freq.HIGH,
        icon="mdi:mirror",
        category="灯光",
    ),  # 有翻译映射
    "mirror_right": SignalSpec(
        key="mirror_right",
        path="Vehicle.Body.RearMirro.RRearMirro",
        name="右后视镜",
        freq=Freq.HIGH,
        icon="mdi:mirror",
        category="灯光",
    ),  # 有翻译映射
    "online_5g": SignalSpec(
        key="online_5g",
        path="Vehicle.ConnectManager.ConnectStatus.5G",
        name="5G 连接",
        freq=Freq.HIGH,
        semantics=Semantics.CONNECTED,
        device_class="CONNECTIVITY",
        icon="mdi:signal-5g",
        platforms=frozenset({'binary_sensor'}),
    ),
    "online_huf": SignalSpec(
        key="online_huf",
        path="Vehicle.ConnectManager.ConnectStatus.hu-f",
        name="车机连接",
        freq=Freq.HIGH,
        semantics=Semantics.CONNECTED,
        device_class="CONNECTIVITY",
        icon="mdi:car-connected",
        platforms=frozenset({'binary_sensor'}),
    ),
    "online_xcu": SignalSpec(
        key="online_xcu",
        path="Vehicle.ConnectManager.ConnectStatus.xcu",
        name="XCU 连接",
        freq=Freq.HIGH,
        semantics=Semantics.CONNECTED,
        device_class="CONNECTIVITY",
        icon="mdi:chip",
        platforms=frozenset({'binary_sensor'}),
    ),
    "ota_progress": SignalSpec(
        key="ota_progress",
        path="Vehicle.OTA.Upgrade.UpgradeProgress",
        name="OTA 进度",
        freq=Freq.LOW,
        unit="%",
        icon="mdi:progress-download",
        category="OTA",
        diagnostic=True,
    ),
    "ota_short": SignalSpec(
        key="ota_short",
        path="Vehicle.Version.OTA.displayedBaseline",
        name="OTA 版本(简)",
        freq=Freq.LOW,
        icon="mdi:cellphone-arrow-down",
        diagnostic=True,
    ),
    "ota_state": SignalSpec(
        key="ota_state",
        path="Vehicle.OTA.Upgrade.UpgradeState",
        name="OTA 状态",
        freq=Freq.LOW,
        icon="mdi:download",
        category="OTA",
        diagnostic=True,
    ),
    "ota_status": SignalSpec(
        key="ota_status",
        path="Vehicle.OTA.Upgrade.UpgradeStatus",
        name="OTA 结果",
        freq=Freq.LOW,
        icon="mdi:download-circle",
        category="OTA",
        diagnostic=True,
    ),
    "ota_version": SignalSpec(
        key="ota_version",
        path="Vehicle.Version.OTA.Baseline",
        name="车机版本",
        freq=Freq.LOW,
        icon="mdi:car-info",
        category="OTA",
        diagnostic=True,
    ),
    "park_fsd_progress": SignalSpec(
        key="park_fsd_progress",
        path="Vehicle.ParkMeshAgent.Park.FSDBootProgress",
        name="泊车启动进度",
        freq=Freq.MID,
        icon="mdi:progress-clock",
        category="泊车",
    ),
    "park_status": SignalSpec(
        key="park_status",
        path="Vehicle.ParkMeshAgent.Park.ParkStatus",
        name="泊车状态",
        freq=Freq.LOW,
        icon="mdi:parking",
        category="泊车",
    ),
    "privacy_pos_service": SignalSpec(
        key="privacy_pos_service",
        path="Vehicle.CarSettings.Privacy.PosService",
        name="位置服务",
        freq=Freq.HIGH,
        icon="mdi:map-marker-radius",
        category="设置",
        diagnostic=True,
    ),  # 有翻译映射
    "provision_auth": SignalSpec(
        key="provision_auth",
        path="Vehicle.Provision.Authorize.State",
        name="车辆授权",
        freq=Freq.LOW,
        semantics=Semantics.CONNECTED,
        icon="mdi:key-check",
        platforms=frozenset({'binary_sensor'}),
    ),
    "range_elec_cltc": SignalSpec(
        key="range_elec_cltc",
        path="Vehicle.Cabin.CLTC.PureElecEnduranceMileInd",
        name="纯电续航(CLTC)",
        unit="km",
        freq=Freq.HIGH,
        icon="mdi:ev-station",
    ),
    "range_elec_wltc": SignalSpec(
        key="range_elec_wltc",
        path="Vehicle.Cabin.WLTC.PureElecEnduranceMileInd",
        name="纯电续航(WLTC)",
        unit="km",
        freq=Freq.HIGH,
        icon="mdi:ev-station",
    ),
    "range_fuel_cltc": SignalSpec(
        key="range_fuel_cltc",
        path="Vehicle.Cabin.CLTC.FuelEnduranceMileInd",
        name="燃油续航(CLTC)",
        unit="km",
        freq=Freq.HIGH,
        icon="mdi:gas-station",
    ),
    "range_fuel_wltc": SignalSpec(
        key="range_fuel_wltc",
        path="Vehicle.Cabin.WLTC.FuelEnduranceMileInd",
        name="燃油续航(WLTC)",
        unit="km",
        freq=Freq.HIGH,
        icon="mdi:gas-station",
    ),
    "scene_mode": SignalSpec(
        key="scene_mode",
        path="Vehicle.CarSettings.SceneMode.ModeState",
        name="场景模式",
        freq=Freq.HIGH,
        icon="mdi:palette",
        category="设置",
        diagnostic=True,
    ),  # 有翻译映射
    "scheduled_charge_end": SignalSpec(
        key="scheduled_charge_end",
        path="Vehicle.Powertrain.ChargingPile.ScheduledCharging.NewReserveFinishTime",
        name="预约结束时间",
        freq=Freq.MID,
        icon="mdi:clock-end",
        category="充电桩",
    ),
    "scheduled_charge_start": SignalSpec(
        key="scheduled_charge_start",
        path="Vehicle.Powertrain.ChargingPile.ScheduledCharging.ReserveStartTime",
        name="预约开始时间",
        freq=Freq.MID,
        icon="mdi:clock-start",
        category="充电桩",
    ),
    "scheduled_charge_state": SignalSpec(
        key="scheduled_charge_state",
        path="Vehicle.Powertrain.ChargingPile.ScheduledCharging.State",
        name="预约充电状态",
        freq=Freq.MID,
        icon="mdi:calendar-check",
        category="充电桩",
    ),  # 有翻译映射
    "scheduled_charge_switch": SignalSpec(
        key="scheduled_charge_switch",
        path="Vehicle.Powertrain.ChargingPile.ScheduledCharging.Switch",
        name="预约充电",
        freq=Freq.MID,
        semantics=Semantics.SWITCH_ON,
        icon="mdi:calendar-clock",
        platforms=frozenset({'binary_sensor'}),
    ),  # 有翻译映射
    "seat_fl_heat": SignalSpec(
        key="seat_fl_heat",
        path="Vehicle.Cabin.Seat.FLSeatHeatState",
        name="主驾座椅加热",
        freq=Freq.HIGH,
        icon="mdi:car-seat-heater",
        category="座椅",
    ),  # 有翻译映射
    "seat_fl_vent": SignalSpec(
        key="seat_fl_vent",
        path="Vehicle.Cabin.Seat.FLSeatVentilationState",
        name="主驾座椅通风",
        freq=Freq.HIGH,
        icon="mdi:car-seat-cooler",
        category="座椅",
    ),  # 有翻译映射
    "seat_fr_heat": SignalSpec(
        key="seat_fr_heat",
        path="Vehicle.Cabin.Seat.FRSeatHeatState",
        name="副驾座椅加热",
        freq=Freq.HIGH,
        icon="mdi:car-seat-heater",
        category="座椅",
    ),  # 有翻译映射
    "seat_fr_vent": SignalSpec(
        key="seat_fr_vent",
        path="Vehicle.Cabin.Seat.FRSeatVentilationState",
        name="副驾座椅通风",
        freq=Freq.HIGH,
        icon="mdi:car-seat-cooler",
        category="座椅",
    ),  # 有翻译映射
    "seat_sl_heat": SignalSpec(
        key="seat_sl_heat",
        path="Vehicle.Cabin.Seat.SLSeatHeatState",
        name="二排左座椅加热",
        freq=Freq.MID,
        icon="mdi:car-seat-heater",
        category="座椅",
    ),  # 有翻译映射
    "seat_sl_vent": SignalSpec(
        key="seat_sl_vent",
        path="Vehicle.Cabin.Seat.SLSeatVentilationState",
        name="二排左座椅通风",
        freq=Freq.MID,
        icon="mdi:car-seat-cooler",
        category="座椅",
    ),  # 有翻译映射
    "seat_sm_heat": SignalSpec(
        key="seat_sm_heat",
        path="Vehicle.Cabin.Seat.SMSeatHeatState",
        name="二排中座椅加热",
        freq=Freq.MID,
        icon="mdi:car-seat-heater",
        category="座椅",
    ),  # 有翻译映射
    "seat_sr_heat": SignalSpec(
        key="seat_sr_heat",
        path="Vehicle.Cabin.Seat.SRSeatHeatState",
        name="二排右座椅加热",
        freq=Freq.MID,
        icon="mdi:car-seat-heater",
        category="座椅",
    ),  # 有翻译映射
    "seat_sr_vent": SignalSpec(
        key="seat_sr_vent",
        path="Vehicle.Cabin.Seat.SRSeatVentilationState",
        name="二排右座椅通风",
        freq=Freq.MID,
        icon="mdi:car-seat-cooler",
        category="座椅",
    ),  # 有翻译映射
    "seat_tl_heat": SignalSpec(
        key="seat_tl_heat",
        path="Vehicle.Cabin.Seat.TLSeatHeatState",
        name="三排左座椅加热",
        freq=Freq.MID,
        icon="mdi:car-seat-heater",
        category="座椅",
    ),  # 有翻译映射
    "seat_tl_vent": SignalSpec(
        key="seat_tl_vent",
        path="Vehicle.Cabin.Seat.TLSeatVentilationState",
        name="三排左座椅通风",
        freq=Freq.MID,
        icon="mdi:car-seat-cooler",
        category="座椅",
    ),  # 有翻译映射
    "seat_tm_heat": SignalSpec(
        key="seat_tm_heat",
        path="Vehicle.Cabin.Seat.TMSeatHeatState",
        name="三排中座椅加热",
        freq=Freq.MID,
        icon="mdi:car-seat-heater",
        category="座椅",
    ),  # 有翻译映射
    "seat_tr_heat": SignalSpec(
        key="seat_tr_heat",
        path="Vehicle.Cabin.Seat.TRSeatHeatState",
        name="三排右座椅加热",
        freq=Freq.MID,
        icon="mdi:car-seat-heater",
        category="座椅",
    ),  # 有翻译映射
    "seat_tr_vent": SignalSpec(
        key="seat_tr_vent",
        path="Vehicle.Cabin.Seat.TRSeatVentilationState",
        name="三排右座椅通风",
        freq=Freq.MID,
        icon="mdi:car-seat-cooler",
        category="座椅",
    ),  # 有翻译映射
    "sentry": SignalSpec(
        key="sentry",
        path="Vehicle.Sentry.SentinelStatus",
        name="哨兵模式",
        freq=Freq.HIGH,
        icon="mdi:shield-car",
        platforms=frozenset({'binary_sensor'}),
        semantics=Semantics.JSON_FIELD,
        json_field="sentinelStatus",
    ),  # 有翻译映射
    "sentry_switch": SignalSpec(
        key="sentry_switch",
        path="Vehicle.Sentry.SettingsStatus",
        name="哨兵开关",
        freq=Freq.HIGH,
        icon="mdi:shield-check",
        platforms=frozenset({'binary_sensor'}),
        semantics=Semantics.JSON_FIELD,
        json_field="sentinelSwitch",
    ),
    "sentry_video_count": SignalSpec(
        key="sentry_video_count",
        path="Vehicle.Sentry.Video.Count",
        name="哨兵视频数",
        freq=Freq.HIGH,
        state_class="MEASUREMENT",
        icon="mdi:video",
        category="哨兵",
    ),
    "speed": SignalSpec(
        key="speed",
        path="Vehicle.XCU.VehSpd",
        name="车速",
        freq=Freq.HIGH,
        device_class="SPEED",
        unit="km/h",
        state_class="MEASUREMENT",
        icon="mdi:speedometer",
        category="位置",
    ),
    "sunshade": SignalSpec(
        key="sunshade",
        path="Vehicle.Body.SunshadeStatus.FrtSunshdSwSts",
        name="遮阳帘",
        freq=Freq.MID,
        icon="mdi:window-shutter",
        category="车窗",
    ),  # 有翻译映射
    "svm_filekey": SignalSpec(
        key="svm_filekey",
        path="Vehicle.360Svm.Park.Filekey",
        name="360 拍照信息",
        freq=Freq.HIGH,
        icon="mdi:image",
        category="影像",
    ),
    "svm_photo_state": SignalSpec(
        key="svm_photo_state",
        path="Vehicle.360Svm.ParkPhoto.State",
        name="360 拍照状态",
        freq=Freq.HIGH,
        icon="mdi:camera",
        category="影像",
    ),  # 有翻译映射
    "tank_lock": SignalSpec(
        key="tank_lock",
        path="Vehicle.Body.DoorSwitchStatus.TankLockDrvSts",
        name="油箱盖",
        freq=Freq.MID,
        semantics=Semantics.DOOR_OPEN,
        icon="mdi:gas-station",
        platforms=frozenset({'binary_sensor'}),
    ),
    "tire_fl": SignalSpec(
        key="tire_fl",
        path="Vehicle.Chassis.Tire.FLTirePressure",
        name="胎压 左前",
        freq=Freq.HIGH,
        device_class="PRESSURE",
        unit="kPa",
        state_class="MEASUREMENT",
        icon="mdi:car-tire-alert",
        category="轮胎",
    ),
    "tire_fl_temp": SignalSpec(
        key="tire_fl_temp",
        path="Vehicle.Chassis.Tire.FLTireTemp",
        name="胎温 左前",
        freq=Freq.HIGH,
        device_class="TEMPERATURE",
        unit="°C",
        state_class="MEASUREMENT",
        icon="mdi:thermometer-lines",
        category="轮胎",
    ),
    "tire_fl_warning": SignalSpec(
        key="tire_fl_warning",
        path="Vehicle.Chassis.Tire.FLTireWarning",
        name="胎压告警 左前",
        freq=Freq.HIGH,
        semantics=Semantics.ALARM,
        device_class="PROBLEM",
        icon="mdi:car-tire-alert",
        platforms=frozenset({'binary_sensor'}),
    ),  # 有翻译映射
    "tire_fr": SignalSpec(
        key="tire_fr",
        path="Vehicle.Chassis.Tire.FRTirePressure",
        name="胎压 右前",
        freq=Freq.HIGH,
        device_class="PRESSURE",
        unit="kPa",
        state_class="MEASUREMENT",
        icon="mdi:car-tire-alert",
        category="轮胎",
    ),
    "tire_fr_temp": SignalSpec(
        key="tire_fr_temp",
        path="Vehicle.Chassis.Tire.FRTireTemp",
        name="胎温 右前",
        freq=Freq.HIGH,
        device_class="TEMPERATURE",
        unit="°C",
        state_class="MEASUREMENT",
        icon="mdi:thermometer-lines",
        category="轮胎",
    ),
    "tire_fr_warning": SignalSpec(
        key="tire_fr_warning",
        path="Vehicle.Chassis.Tire.FRTireWarning",
        name="胎压告警 右前",
        freq=Freq.HIGH,
        semantics=Semantics.ALARM,
        device_class="PROBLEM",
        icon="mdi:car-tire-alert",
        platforms=frozenset({'binary_sensor'}),
    ),  # 有翻译映射
    "tire_rl": SignalSpec(
        key="tire_rl",
        path="Vehicle.Chassis.Tire.RLTirePressure",
        name="胎压 左后",
        freq=Freq.HIGH,
        device_class="PRESSURE",
        unit="kPa",
        state_class="MEASUREMENT",
        icon="mdi:car-tire-alert",
        category="轮胎",
    ),
    "tire_rl_temp": SignalSpec(
        key="tire_rl_temp",
        path="Vehicle.Chassis.Tire.RLTireTemp",
        name="胎温 左后",
        freq=Freq.HIGH,
        device_class="TEMPERATURE",
        unit="°C",
        state_class="MEASUREMENT",
        icon="mdi:thermometer-lines",
        category="轮胎",
    ),
    "tire_rl_warning": SignalSpec(
        key="tire_rl_warning",
        path="Vehicle.Chassis.Tire.RLTireWarning",
        name="胎压告警 左后",
        freq=Freq.HIGH,
        semantics=Semantics.ALARM,
        device_class="PROBLEM",
        icon="mdi:car-tire-alert",
        platforms=frozenset({'binary_sensor'}),
    ),  # 有翻译映射
    "tire_rr": SignalSpec(
        key="tire_rr",
        path="Vehicle.Chassis.Tire.RRTirePressure",
        name="胎压 右后",
        freq=Freq.HIGH,
        device_class="PRESSURE",
        unit="kPa",
        state_class="MEASUREMENT",
        icon="mdi:car-tire-alert",
        category="轮胎",
    ),
    "tire_rr_temp": SignalSpec(
        key="tire_rr_temp",
        path="Vehicle.Chassis.Tire.RRTireTemp",
        name="胎温 右后",
        freq=Freq.HIGH,
        device_class="TEMPERATURE",
        unit="°C",
        state_class="MEASUREMENT",
        icon="mdi:thermometer-lines",
        category="轮胎",
    ),
    "tire_rr_warning": SignalSpec(
        key="tire_rr_warning",
        path="Vehicle.Chassis.Tire.RRTireWarning",
        name="胎压告警 右后",
        freq=Freq.HIGH,
        semantics=Semantics.ALARM,
        device_class="PROBLEM",
        icon="mdi:car-tire-alert",
        platforms=frozenset({'binary_sensor'}),
    ),  # 有翻译映射
    "tpms_status": SignalSpec(
        key="tpms_status",
        path="Vehicle.Chassis.Tire.TPMSSysSts",
        name="TPMS 系统告警",
        freq=Freq.HIGH,
        semantics=Semantics.ALARM,
        device_class="PROBLEM",
        icon="mdi:car-tire-alert",
        platforms=frozenset({'binary_sensor'}),
    ),  # 有翻译映射
    "travel_status": SignalSpec(
        key="travel_status",
        path="Vehicle.Cabin.TravelStatus",
        name="行驶状态",
        freq=Freq.HIGH,
        icon="mdi:car-cruise-control",
        category="空气",
    ),
    "trip_total": SignalSpec(
        key="trip_total",
        path="Vehicle.Carcenter.Trip.Total",
        name="行程总计",
        freq=Freq.HIGH,
        icon="mdi:counter",
        category="保养",
        diagnostic=True,
    ),
    "wheel_heat": SignalSpec(
        key="wheel_heat",
        path="Vehicle.Cabin.WheelWarmStatus.WarmOnOff",
        name="方向盘加热",
        freq=Freq.HIGH,
        semantics=Semantics.SWITCH_ON,
        icon="mdi:steering",
        platforms=frozenset({'binary_sensor'}),
    ),  # 有翻译映射
    "window_back_left": SignalSpec(
        key="window_back_left",
        path="Vehicle.Body.WindowPosition.BackLeftWindow",
        name="左后车窗",
        freq=Freq.HIGH,
        unit="%",
        icon="mdi:car-door",
        category="车窗",
    ),  # 有翻译映射
    "window_back_right": SignalSpec(
        key="window_back_right",
        path="Vehicle.Body.WindowPosition.BackRightWindow",
        name="右后车窗",
        freq=Freq.HIGH,
        unit="%",
        icon="mdi:car-door",
        category="车窗",
    ),  # 有翻译映射
    "window_copilot": SignalSpec(
        key="window_copilot",
        path="Vehicle.Body.WindowPosition.CopilotWindow",
        name="副驾车窗",
        freq=Freq.HIGH,
        unit="%",
        icon="mdi:car-door",
        category="车窗",
    ),  # 有翻译映射
    "window_main": SignalSpec(
        key="window_main",
        path="Vehicle.Body.WindowPosition.MainWindow",
        name="主驾车窗",
        freq=Freq.HIGH,
        unit="%",
        icon="mdi:car-door",
        category="车窗",
    ),  # 有翻译映射
    "window_skylight": SignalSpec(
        key="window_skylight",
        path="Vehicle.Body.WindowPosition.SkylightWindow",
        name="天窗位置",
        unit="%",
        freq=Freq.HIGH,
        icon="mdi:window-closed-variant",
        platforms=frozenset(),  # ★ L6 实测无数据（SkylightWindow 返回 None）
    ),
    # ★ 虚拟信号（非 VSS）—— 值来自 coordinator.data 的其他字段
    # ⚠️ gen_signals.py 从 VSS_PATHS 生成，不会包含它们 —— 需手工维护
    "online_status": SignalSpec(
        key="online_status",
        path="",                      # 无 VSS 路径（虚拟信号）
        name="在线状态",
        freq=Freq.HIGH,
        icon="mdi:car-connected",
        category="状态",
    ),
    # ═══════════════════════════════════════════════════════════════════
    #  ★ 2026-09-24 手工补充的信号（task-14 报告，已实测有数据）
    #  ⚠️ 这些不在 gen_signals.py 的生成源里，需手工维护
    # ═══════════════════════════════════════════════════════════════════
    # ---- 授权 / 账号 ----
    "virtual_key_auth": SignalSpec(
        key="virtual_key_auth",
        path="Vehicle.Cabin.RmtVirtualKeyAuthSts",
        name="远程虚拟钥匙授权",
        freq=Freq.LOW,
        icon="mdi:key-variant",
        category="状态",
        diagnostic=True,
    ),
    "vehicle_accounts": SignalSpec(
        key="vehicle_accounts",
        path="Vehicle.Account.Cloud.VehicleAccounts",
        name="车辆账号",
        freq=Freq.LOW,
        icon="mdi:account-multiple",
        category="信息",
        diagnostic=True,
    ),
    # ---- 激活流程 ----
    "provision_complete": SignalSpec(
        key="provision_complete",
        path="Vehicle.Provision.Process.Complete",
        name="激活完成",
        freq=Freq.LOW,
        icon="mdi:check-circle",
        category="信息",
        diagnostic=True,
    ),
    "provision_finish": SignalSpec(
        key="provision_finish",
        path="Vehicle.Provision.Process.FinishSuccess",
        name="激活成功信息",
        freq=Freq.LOW,
        icon="mdi:clipboard-check",
        category="信息",
        diagnostic=True,
    ),
    # ---- 保养二级 ----
    "maint_engine_level2": SignalSpec(
        key="maint_engine_level2",
        path="Vehicle.Carcenter.Maintain.enginelevel2",
        name="保养二级",
        freq=Freq.LOW,
        icon="mdi:oil-level",
        category="保养",
        diagnostic=True,
    ),
    # ---- 座椅门干涉 ----
    "seat_l_door_interference": SignalSpec(
        key="seat_l_door_interference",
        path="Vehicle.Body.SeatLDoor.InterferenceSts",
        name="左座椅门干涉",
        freq=Freq.MID,
        icon="mdi:alert",
        category="座椅",
        diagnostic=True,
    ),
    "seat_r_door_interference": SignalSpec(
        key="seat_r_door_interference",
        path="Vehicle.Body.SeatRDoor.InterferenceSts",
        name="右座椅门干涉",
        freq=Freq.MID,
        icon="mdi:alert",
        category="座椅",
        diagnostic=True,
    ),
    # ---- 冰箱预约 / 离车模式 ----
    "fridge_reserve": SignalSpec(
        key="fridge_reserve",
        path="Vehicle.CarSettings.Xmode.ReserveFridge",
        name="冰箱预约",
        freq=Freq.MID,
        icon="mdi:fridge-outline",
        category="冰箱",
    ),
    "xmode": SignalSpec(
        key="xmode",
        path="Vehicle.CarSettings.MoveOffOnTime.Xmode",
        name="离车模式",
        freq=Freq.MID,
        icon="mdi:car-off",
        category="设置",
    ),
    # ---- 空调温度色 ----
    "ac_temp_color": SignalSpec(
        key="ac_temp_color",
        path="Vehicle.Cabin.AC.FrtWindTempColor",
        name="空调温度色",
        freq=Freq.MID,
        icon="mdi:palette",
        category="空调",
        diagnostic=True,
    ),
    # ---- 充电校准 / 位置 / 后负载 ----
    "charge_calibration": SignalSpec(
        key="charge_calibration",
        path="Vehicle.VehInfo.CarCenter.ChargeManagement.ChargingCalibration",
        name="充电校准",
        freq=Freq.LOW,
        icon="mdi:tune",
        category="充电桩",
        diagnostic=True,
    ),
    "charge_here": SignalSpec(
        key="charge_here",
        path="Vehicle.Powertrain.ChargingPile.ScheduledCharging.ChargeHere",
        name="充电位置",
        freq=Freq.LOW,
        icon="mdi:map-marker",
        category="充电桩",
    ),
    "rear_load_mode": SignalSpec(
        key="rear_load_mode",
        path="Vehicle.VehInfo.CarSettings.Maintain.RearLoadModeSetting",
        name="后负载模式",
        freq=Freq.LOW,
        icon="mdi:weight",
        category="设置",
        diagnostic=True,
    ),
    # ---- 电池功率条 ----
    "ress_power_bar_color": SignalSpec(
        key="ress_power_bar_color",
        path="Vehicle.Powertrain.Battery.RESSPowerBarCol",
        name="电池功率条颜色",
        freq=Freq.MID,
        icon="mdi:palette-outline",
        category="电池",
        diagnostic=True,
    ),
    # ---- OGC（第三方充电桩）----
    "ogc_charge_current": SignalSpec(
        key="ogc_charge_current",
        path="Vehicle.Powertrain.Battery.OGCChargeCurrent",
        name="OGC 充电电流",
        freq=Freq.MID,
        unit="A",
        icon="mdi:current-ac",
        category="充电桩",
    ),
    "ogc_charge_voltage": SignalSpec(
        key="ogc_charge_voltage",
        path="Vehicle.Powertrain.Battery.OGCChargeVoltage",
        name="OGC 充电电压",
        freq=Freq.MID,
        unit="V",
        icon="mdi:sine-wave",
        category="充电桩",
    ),
    "ogc_type": SignalSpec(
        key="ogc_type",
        path="Vehicle.Powertrain.ChargingPile.OGCType",
        name="OGC 类型",
        freq=Freq.LOW,
        icon="mdi:ev-station",
        category="充电桩",
        diagnostic=True,
    ),
}

# ═══════════════════════════════════════════════════════════════════════════
#  查询辅助
# ═══════════════════════════════════════════════════════════════════════════
def to_sensor_description(spec: SignalSpec):
    """把 SignalSpec 转成 HA 的 SensorEntityDescription。

    ★ 需要 homeassistant 包 → 仅在 HA 运行时调用。
    """
    from homeassistant.components.sensor import SensorEntityDescription
    from homeassistant.const import EntityCategory

    from .sensor import _DCLASS, _SCLASS, _UNITS

    kw: dict = {"key": spec.key, "name": spec.name}
    if spec.icon:
        kw["icon"] = spec.icon
    if spec.device_class and spec.device_class in _DCLASS:
        kw["device_class"] = _DCLASS[spec.device_class]
    if spec.unit and spec.unit in _UNITS:
        kw["native_unit_of_measurement"] = _UNITS[spec.unit]
    if spec.state_class and spec.state_class in _SCLASS:
        kw["state_class"] = _SCLASS[spec.state_class]
    if spec.diagnostic:
        kw["entity_category"] = EntityCategory.DIAGNOSTIC
        kw["entity_registry_enabled_default"] = False
    return SensorEntityDescription(**kw)


def to_sensor_descriptions():
    """批量转换（已按 platforms 过滤）。"""
    return [to_sensor_description(s) for s in specs_for("sensor")]



def to_binary_description(spec: SignalSpec):
    """把 SignalSpec 转成 BinarySensorEntityDescription。

    ★ 架构方案 2.5：替代 binary_sensor.py 的 (Description, kind) 元组。
      语义由 spec.semantics 表达（枚举），不再是字符串分派。
    """
    from homeassistant.components.binary_sensor import BinarySensorEntityDescription

    from .binary_sensor import _DCLASS_BS

    kw: dict = {"key": spec.key, "name": spec.name}
    if spec.icon:
        kw["icon"] = spec.icon
    if spec.device_class and spec.device_class in _DCLASS_BS:
        kw["device_class"] = _DCLASS_BS[spec.device_class]
    return BinarySensorEntityDescription(**kw)


def to_binary_descriptions():
    """批量转换（返回 (desc, spec) 元组）。"""
    return [
        (to_binary_description(s), s)
        for s in specs_for("binary_sensor")
    ]



def specs_for(platform: str, features: dict | None = None) -> list[SignalSpec]:
    """按平台 + 车型功能过滤信号。

    ★ 替代各平台各自的过滤逻辑，新增信号只需在 SIGNALS 里加一行。

    参数
    ----
    platform : "sensor" / "binary_sensor" / ...
    features : 车型功能探测结果（features.py），None 表示不过滤
    """
    feats = features or {}
    return [
        s for s in SIGNALS.values()
        if platform in s.platforms
    ]


def by_freq(freq: Freq) -> list[SignalSpec]:
    """按频率档位筛选（coordinator 用）。

    ★ 2026-09-24：排除虚拟信号（path 为空）—— 它们不走 VSS 轮询。
    """
    return [s for s in SIGNALS.values() if s.freq == freq and s.path]


def paths_for(freq: Freq | None = None) -> list[str]:
    """返回 VSS 路径列表（coordinator 轮询用）。

    freq=None 表示全部。

    ★ 2026-09-24：排除【虚拟信号】（path 为空）——
      它们的值来自 coordinator.data 的其他字段，不通过 VSS 轮询。
    """
    items = [s for s in SIGNALS.values() if s.path]
    if freq is not None:
        items = [s for s in items if s.freq == freq]
    return [s.path for s in items]


def path_of(key: str) -> str:
    """按 key 取 VSS 路径（兼容旧代码的 VSS_PATHS 用法）。"""
    spec = SIGNALS.get(key)
    return spec.path if spec else ""


def value_map_of(key: str) -> dict | None:
    """按 key 取值翻译表。"""
    spec = SIGNALS.get(key)
    return spec.value_map if spec else None


# 兼容：把 SIGNALS 转成旧的 {key: path} 形式
VSS_PATHS_COMPAT: dict[str, str] = {
    k: s.path for k, s in SIGNALS.items() if s.path
}


__all__ = [
    "Freq", "Semantics", "SignalSpec", "SIGNALS",
    "specs_for", "by_freq", "paths_for", "path_of", "value_map_of",
    "to_sensor_description", "to_sensor_descriptions",
    "to_binary_description", "to_binary_descriptions",
    "VSS_PATHS_COMPAT",
]
