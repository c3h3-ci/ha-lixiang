"""Constants for Li Auto (Ideal Car) integration.

核心常量来源：对理想汽车 App (com.chehejia.oc.m01) 的逆向分析。
"""

DOMAIN = "lixiang_auto"

# ---------- 理想 IDaaS 登录 (OAuth 设备码 / 验证码) ----------
# 来源: 抓包 account/id.lixiang.com 登录流程 + livis 组件
IDAAS_BASE = "https://id.lixiang.com/api"
ACCOUNT_BASE = "https://account.lixiang.com"

# App OAuth 客户端（来自抓包 /api/auth）
CLIENT_ID = "2AQClOaegaA7XecMSFx1p"
AUDIENCE = "5iIapSfVJlln0vU0OzUCH9"
SCOPE = "iam:client:type:app offline_access"

# livis 侧门客户端（已验证可用，设备码流程）
LIVIS_CLIENT_ID = "6qxd1MLZhAtdWipnmXe1dd"
LIVIS_AUDIENCE = "rZgT0SETDNueMVAhfRN10"
LIVIS_SCOPE = "super offline_access"

# ---------- 车辆 API 域名 ----------
API_APP = "https://api-app.lixiang.com"   # 车辆主网关（强制 x-chj-sign）

# ---------- API 端点 ----------
EP_KEY_SUITE = "/aisp-app-api/v1-0/keySuite"          # 密钥套件（登录后获取）
EP_VEHICLES = "/aisp-account-api/v1-0/vehicles"       # 车辆列表（X-CHJ-TOKEN 已过期，240225）
# ★ 可用的车辆列表端点（2026-09-23 实测成功）
#   audience=7gbeHMwBPMZA5SU1b2awIo, scope=login
#   返回: {"data":[{vin, modelName, seriesName, vehicleType, vehicleRoleId, ...}]}
AUD_SAOS_VEHICLE = "7gbeHMwBPMZA5SU1b2awIo"
SCOPE_SAOS_VEHICLE = "login"
EP_SAOS_VEHICLES = (
    "/saos-vehicle-api/v2-0/vehicles/basics"
    "?types=owned,transferring,authorized,inviting"
    "&roleIds=1,10,11,13,15&vehicleInfo=true"
)
EP_VEHICLE = "/aisp-account-api/v1-0/vehicles/{vin}"  # 车辆详情
EP_VEHICLE_BASICS = "/saos-vehicle-api/v2-0/vehicles/basics"  # 车辆基础
EP_PROFILE = "/aisp-account-api/v1-0/profile"         # 用户资料

# 车辆控制（逆向自抓包）
EP_WAKEUP = "/iot-connect-manager-service/v2/wakeup"          # 远程唤醒
EP_KMS_JWT = "/bcs-kms-jwt/jwt/iot2/v1-0/"                    # KMS JWT（控制通道）
EP_ICN_GNS = "/icn-gns/gns/app/service/vin/{vin}"            # 控制通道

# ---------- 签名常量 ----------
# 11 参数分隔符 = '\n'（liblxnetwork.so 0xa1768 证实）
SIGN_SEP = "\n"
# 空 body 的 Content-MD5
EMPTY_MD5 = "1B2M2Y8AsgTpgAmY7PhCfg=="

# ---------- 请求头固定值 ----------
# 注: iOS app 实证值（来自抓取的实际请求头）
DEFAULT_ACCEPT = "*/*"                 # iOS 捕获实际为 */*
DEFAULT_CONTENT_TYPE = "application/json"
DEFAULT_CONTENT_LANG = "zh-Hans-CN"    # iOS 捕获
ENV = "prod"
DEVICE_TYPE = "2"                       # iOS
MODEL_NAME = "IOS"
DEVICE_MODEL = "9.7-INCH IPAD"

# 别名（兼容 client 直接引用短名）
CONTENT_TYPE = DEFAULT_CONTENT_TYPE
CONTENT_LANG = DEFAULT_CONTENT_LANG
DEVICE_MODEL_NAME = DEVICE_MODEL

# ---------- 配置项 ----------
CONF_PHONE = "phone"
CONF_PASSWORD = "password"        # PAKE 登录密码 (sso_token 会话13天过期后自动重登)
CONF_REFRESH_TOKEN = "refresh_token"
CONF_ACCESS_TOKEN = "access_token"
CONF_APP_TOKEN = "app_token"      # X-CHJ-TOKEN (APP-xxx), frida从app抓取
CONF_HAC_KEY = "hac_key"          # x-chj-sign 的 HMAC 密钥（k11）
CONF_KEY_ID = "key_id"            # x-chj-key
CONF_DEVICE_ID = "device_id"      # 登录身份 device_id (受信任的可跳短信风控)
CONF_XDEV = "x_chj_deviceid"      # x-chj 签名身份 deviceid (与 hac_key 绑定)
CONF_VIN = "vin"
# 主Bearer(登录后签发的JWT, client=2AQ...). 任意车主登录一次可得, 用它换各scope token
CONF_MAIN_BEARER = "main_bearer"

# ---------- x-chj 签名身份默认值 (自有车辆 iPad 捕获, 密码登录流程直接复用;
# 手动凭据流程可覆盖) ----------
#
# ★ 2026-09-24 说明：
#   这些是【API 签名常量】（非用户私有凭据），随集成一起分发以便开箱即用。
#   优先级：config entry 里的用户值 > 这里的默认值。
#
#   如果不想用内置值，可在 HA 里通过「手动凭据」入口填写自己的；
#   或创建 .secrets.json（优先级低于 config entry，高于这里的默认值）。
try:
    from .secrets import (  # noqa: E402
        DEFAULT_APP_TOKEN as _S_APP_TOKEN,
        DEFAULT_HAC_KEY as _S_HAC_KEY,
        DEFAULT_KEY_ID as _S_KEY_ID,
        DEFAULT_XDEV as _S_XDEV,
    )
except ImportError:  # pragma: no cover
    _S_APP_TOKEN = _S_HAC_KEY = _S_KEY_ID = _S_XDEV = ""

DEFAULT_HAC_KEY = _S_HAC_KEY or "2020a7738b35f7d253741a88963ea2902b770ac508d89a78ae9036ee8aeb5d8a"
DEFAULT_KEY_ID = _S_KEY_ID or "22004e67c0f7a60a1561980000b7440f"
DEFAULT_XDEV = _S_XDEV or "13BFCE38F5774D0DBE21B625AA179AE0"
DEFAULT_APP_TOKEN = _S_APP_TOKEN or "APP-50dbc95ceba84c05ac159ea96f2e6ffe"
# ★ 默认登录 device_id（留空 = 由 identity store 自动生成/复用）
#   说明：不要硬编码他人的 device_id —— 那会把所有用户绑到同一设备身份。
#   首次登录时【辅助页面】会让用户的 device_id 受信任，之后免 MFA。
DEFAULT_DEVICE_ID = ""

# ---------- VSS 实时信号路径 (实体key → VSS path, 见 docs/VSS信号映射_HA实体.md) ----------
VSS_PATHS = {
    # ===== 电池/充电 =====
    "battery_level": "Vehicle.Powertrain.Battery.ResidueBattery",
    "charge_status": "Vehicle.Powertrain.Battery.ChargeStatus",
    "charge_gun_ac": "Vehicle.Powertrain.Battery.ACChgrActualConnSts",
    "charge_gun_dc": "Vehicle.Powertrain.Battery.DCChrgngGunActuSts",
    "charge_power_cltc": "Vehicle.Powertrain.Battery.CLTCChargePower",
    "charge_power_wltc": "Vehicle.Powertrain.Battery.WLTCChargePower",
    "charge_voltage_ac": "Vehicle.Powertrain.Battery.ACChargeVoltage",
    "charge_current_ac": "Vehicle.Powertrain.Battery.ACChargeCurrent",
    "battery_pack_voltage": "Vehicle.Powertrain.Battery.MSG_RESSInterVolt",
    "charge_remain_time": "Vehicle.Powertrain.Battery.ChargeSurplusTime",
    "charge_complete": "Vehicle.Powertrain.Battery.VehicleChrgComplete",
    "charge_fault": "Vehicle.Powertrain.Battery.ChargeFaults",
    "discharge_status": "Vehicle.Powertrain.Battery.DischargeStatus",
    # ===== 充电桩/预约 =====
    "charge_limit": "Vehicle.Powertrain.ChargingPile.ChargingLimit",
    "scheduled_charge_switch": "Vehicle.Powertrain.ChargingPile.ScheduledCharging.Switch",
    "scheduled_charge_state": "Vehicle.Powertrain.ChargingPile.ScheduledCharging.State",
    "scheduled_charge_start": "Vehicle.Powertrain.ChargingPile.ScheduledCharging.ReserveStartTime",
    "scheduled_charge_end": "Vehicle.Powertrain.ChargingPile.ScheduledCharging.NewReserveFinishTime",
    # ===== 续航/油量 =====
    "range_elec_cltc": "Vehicle.Cabin.CLTC.PureElecEnduranceMileInd",
    "range_fuel_cltc": "Vehicle.Cabin.CLTC.FuelEnduranceMileInd",
    "range_elec_wltc": "Vehicle.Cabin.WLTC.PureElecEnduranceMileInd",
    "range_fuel_wltc": "Vehicle.Cabin.WLTC.FuelEnduranceMileInd",
    "fuel_level": "Vehicle.MSG.MSG_FuelLevelPos",
    "fuel_low_warning": "Vehicle.MSG.MSG_FuelLevelWrnng",
    # ===== 车门锁 =====
    "lock_main": "Vehicle.Body.DoorLockStatus.MainDoor",
    "lock_copilot": "Vehicle.Body.DoorLockStatus.CopilotDoor",
    "lock_back_left": "Vehicle.Body.DoorLockStatus.BackLeftDoor",
    "lock_back_right": "Vehicle.Body.DoorLockStatus.BackRightDoor",
    "lock_trunk": "Vehicle.Body.DoorLockStatus.TrunkDoor",
    "lock_front_trunk": "Vehicle.Body.DoorLockStatus.FrontTrunkDoor",
    # ===== 车门开关 =====
    "door_main": "Vehicle.Body.DoorSwitchStatus.MainDoor",
    "door_copilot": "Vehicle.Body.DoorSwitchStatus.CopilotDoor",
    "door_back_left": "Vehicle.Body.DoorSwitchStatus.BackLeftDoor",
    "door_back_right": "Vehicle.Body.DoorSwitchStatus.BackRightDoor",
    "door_trunk": "Vehicle.Body.DoorSwitchStatus.TrunkDoor",
    # ★ 2026-09-23：ChrgPorLidSts（旧版）在 L6 上恒为 1（无效信号），
    #   改用 ChrgPorLidStsV2（实测 0 = 关闭）
    "charge_port_lid": "Vehicle.Body.DoorSwitchStatus.ChrgPorLidStsV2",
    "charge_port_lid_old": "Vehicle.Body.DoorSwitchStatus.ChrgPorLidSts",
    "tank_lock": "Vehicle.Body.DoorSwitchStatus.TankLockDrvSts",
    # ===== 车窗 =====
    "window_main": "Vehicle.Body.WindowPosition.MainWindow",
    "window_copilot": "Vehicle.Body.WindowPosition.CopilotWindow",
    "window_back_left": "Vehicle.Body.WindowPosition.BackLeftWindow",
    "window_back_right": "Vehicle.Body.WindowPosition.BackRightWindow",
    "sunshade": "Vehicle.Body.SunshadeStatus.FrtSunshdSwSts",
    # ===== 空调 =====
    "inside_temp": "Vehicle.Cabin.AC.FrtACIncarTemp",
    "ac_set_temp": "Vehicle.Cabin.AC.SetTemp",
    "ac_wind_mode": "Vehicle.Cabin.AC.WindMode",
    "ac_defrost": "Vehicle.Cabin.AC.DefrostModeStatus",
    # ⚠️ 语义实为"快冷快热"（getNeedRapidCoolheat），历史名保留
    "ac_fan_speed": "Vehicle.Cabin.AC.ExSpeedStatus",
    # ★ 空调真实开关信号（2026-09-23 从 App 源码 LiMeshPathHelper 还原）
    #   LXVehicleInfoKeyAC → Vehicle.Cabin.AC.FOffStatus
    #   App 逻辑：FOffStatus==1 → setACSwitch(true)
    #   实测：空调开着=1，关着=0；时间戳随操作实时更新
    "ac_on": "Vehicle.Cabin.AC.FOffStatus",
    # ===== 座椅加热/通风 =====
    "seat_fl_heat": "Vehicle.Cabin.Seat.FLSeatHeatState",
    "seat_fl_vent": "Vehicle.Cabin.Seat.FLSeatVentilationState",
    "seat_fr_heat": "Vehicle.Cabin.Seat.FRSeatHeatState",
    "seat_fr_vent": "Vehicle.Cabin.Seat.FRSeatVentilationState",
    "seat_sl_heat": "Vehicle.Cabin.Seat.SLSeatHeatState",
    "seat_sr_heat": "Vehicle.Cabin.Seat.SRSeatHeatState",
    "seat_sm_heat": "Vehicle.Cabin.Seat.SMSeatHeatState",
    "seat_tl_heat": "Vehicle.Cabin.Seat.TLSeatHeatState",
    "seat_tr_heat": "Vehicle.Cabin.Seat.TRSeatHeatState",
    # ★ 2026-09-23 补充（task-14 报告的高价值遗漏项）
    #   二/三排座椅通风（原先只有前排）
    "seat_sl_vent": "Vehicle.Cabin.Seat.SLSeatVentilationState",
    "seat_sr_vent": "Vehicle.Cabin.Seat.SRSeatVentilationState",
    "seat_tl_vent": "Vehicle.Cabin.Seat.TLSeatVentilationState",
    "seat_tr_vent": "Vehicle.Cabin.Seat.TRSeatVentilationState",
    # 三排中间加热
    "seat_tm_heat": "Vehicle.Cabin.Seat.TMSeatHeatState",
    # 天窗位置（0-100）
    "window_skylight": "Vehicle.Body.WindowPosition.SkylightWindow",
    # 车机连接（App 官方订阅，原先只接了 5G/xcu）
    "online_huf": "Vehicle.ConnectManager.ConnectStatus.hu-f",
    # 钥匙壳/保护套状态
    "case_cover": "Vehicle.Body.DoorSwitchStatus.CaseCoverStatus",
    # 充电相关（getChargeState 的判据）
    "eves_flt_stop_chrg": "Vehicle.Powertrain.Battery.EVESFltStopChrg",
    "battery_insulation": "Vehicle.Powertrain.ChargingPile.BatteryInsulation",
    # 低压电源状态（App 订阅，原先只接了 Flag）
    "low_vol_status": "Vehicle.Body.Power.LowVolPwrMdSts",
    # DCDC 故障等级
    "dcdc_fault_level": "Vehicle.MSG.MSG_DCDCFltLvl",
    # CLTC 里程最终结果（App 订阅）
    "mileage_final": "Vehicle.Cabin.CLTC.MileageFinalResult",
    # 电池类型（三元锂/磷酸铁锂）
    "battery_type": "Vehicle.Powertrain.Battery.PowerBatteryType",
    # 预约充电模式
    "charge_order_mode": "Vehicle.Powertrain.ChargingPile.ScheduledCharging.OrderChargingMode",
    "wheel_heat": "Vehicle.Cabin.WheelWarmStatus.WarmOnOff",
    # ===== 冰箱 =====
    "fridge_status": "Vehicle.Cabin.Fridge.ActWorkSts",
    "fridge_mode": "Vehicle.Cabin.Fridge.ModeState",
    "fridge_cool_temp": "Vehicle.Cabin.Fridge.CoolTempSt",
    "fridge_remain_time": "Vehicle.Cabin.Fridge.DlyTmRemain",
    # ===== 轮胎 =====
    "tire_fl": "Vehicle.Chassis.Tire.FLTirePressure",
    "tire_fr": "Vehicle.Chassis.Tire.FRTirePressure",
    "tire_rl": "Vehicle.Chassis.Tire.RLTirePressure",
    "tire_rr": "Vehicle.Chassis.Tire.RRTirePressure",
    "tire_fl_temp": "Vehicle.Chassis.Tire.FLTireTemp",
    "tire_fr_temp": "Vehicle.Chassis.Tire.FRTireTemp",
    "tire_rl_temp": "Vehicle.Chassis.Tire.RLTireTemp",
    "tire_rr_temp": "Vehicle.Chassis.Tire.RRTireTemp",
    "tire_fl_warning": "Vehicle.Chassis.Tire.FLTireWarning",
    "tire_fr_warning": "Vehicle.Chassis.Tire.FRTireWarning",
    "tire_rl_warning": "Vehicle.Chassis.Tire.RLTireWarning",
    "tire_rr_warning": "Vehicle.Chassis.Tire.RRTireWarning",
    "tpms_status": "Vehicle.Chassis.Tire.TPMSSysSts",
    # ===== 位置/连接 =====
    "location": "Vehicle.Location.CurrentLocationInfo",
    "speed": "Vehicle.XCU.VehSpd",
    "online_5g": "Vehicle.ConnectManager.ConnectStatus.5G",
    "online_xcu": "Vehicle.ConnectManager.ConnectStatus.xcu",
    # ===== 版本/OTA =====
    "ota_version": "Vehicle.Version.OTA.Baseline",
    "ota_short": "Vehicle.Version.OTA.displayedBaseline",
    "ota_state": "Vehicle.OTA.Upgrade.UpgradeState",
    "ota_status": "Vehicle.OTA.Upgrade.UpgradeStatus",
    "ota_progress": "Vehicle.OTA.Upgrade.UpgradeProgress",
    # ===== 哨兵 =====
    "sentry": "Vehicle.Sentry.SentinelStatus",
    "sentry_switch": "Vehicle.Sentry.SettingsStatus",
    "sentry_video_count": "Vehicle.Sentry.Video.Count",
    # ===== 保养 =====
    "maint_acfilter": "Vehicle.Carcenter.Maintain.acfilter",
    "maint_coolfuild": "Vehicle.Carcenter.Maintain.coolfuild",
    "maint_engine_oil": "Vehicle.Carcenter.Maintain.enginelevel1",
    "maint_brake_oil": "Vehicle.Carcenter.Maintain.gearbrakeoil",
    "maint_sparkplug": "Vehicle.Carcenter.Maintain.sparkplug",
    "trip_total": "Vehicle.Carcenter.Trip.Total",
    # ===== 空气/模式 =====
    "air_pollution": "Vehicle.Cabin.AirPollutionIndex",
    "low_battery_mode": "Vehicle.Cabin.LowBatteryMode",
    "travel_status": "Vehicle.Cabin.TravelStatus",
    # ===== 灯光/后视镜 =====
    "light_lic": "Vehicle.Body.Light.LicLghtSts",
    "mirror_left": "Vehicle.Body.RearMirro.LRearMirro",
    "mirror_right": "Vehicle.Body.RearMirro.RRearMirro",
    # ===== 低压电源 =====
    "low_vol_mode": "Vehicle.Body.Power.LowVolEngyMngtMd",
    "low_vol_flag": "Vehicle.Body.Power.LowVolPwrMdFlag",
    # ===== 360影像 =====
    "svm_photo_state": "Vehicle.360Svm.ParkPhoto.State",
    "svm_filekey": "Vehicle.360Svm.Park.Filekey",
    # ===== 车辆信息 =====
    "config_code": "Vehicle.Information.ConfigCode",
    "hu_diag": "Vehicle.HU.Diag.Hpcm",
    "provision_auth": "Vehicle.Provision.Authorize.State",
    # ===== 设置 =====
    "privacy_pos_service": "Vehicle.CarSettings.Privacy.PosService",
    "scene_mode": "Vehicle.CarSettings.SceneMode.ModeState",
    # ===== 电池预热 =====
    "battery_keep_warm": "Vehicle.APP.BMS.KeepWarm",
    # ===== 泊车 =====
    "park_status": "Vehicle.ParkMeshAgent.Park.ParkStatus",
    "park_fsd_progress": "Vehicle.ParkMeshAgent.Park.FSDBootProgress",
}

# ---------- 各服务 audience / scope（鸿蒙逆向 /api/auth 实证） ----------
# 用主Bearer POST /api/auth, body{scope, audience, response_type:"token"} 换该服务token
# client_id 统一为 2AQClOaegaA7XecMSFx1p (App主客户端), device_id 用登录时的
REDIRECT_URI = "https://app.lixiang.com/login/subidaas/callback"

# service-card(首页状态): login scope
AUD_SERVICE_CARD = "26FehzsHlrllCSaqI9bFYG"
SCOPE_SERVICE_CARD = "login"
# vss/get-batch + 车控结果 + wakeup: 
AUD_VEHICLE_VSS = "1j0vgTqagJUHuT6nLmbTGx"
SCOPE_VEHICLE_VSS = (
    "remote-wakeup:wakeup veh-ctrl:cmd-result-get veh-ctrl:cmd-send "
    "vss:get-batch task-master"
)
# 车控(锁车/空调等, scope里VIN后缀)
AUD_VEHICLE_CTRL = "1j0vgTqagJUHuT6nLmbTGx"
def veh_ctrl_scope(vin):  # 车控scope含VIN, 运行时动态构造
    scopes = [
        f"remoteVehFrgControl:{vin}",
        f"remoteVehAuth:{vin}",
        f"remoteVehLockControl:{vin}",
        f"remoteVehPlgControl:{vin}",
        f"remoteVehSearch:{vin}",
        f"remoteVehWdwControl:{vin}",
        f"remoteVehACSmartControl:{vin}",
        f"remoteVehACFirstControl:{vin}",
        f"ssCtrl:{vin}",
        f"rmCtrl:{vin}",
        f"cpCtrl:{vin}",
    ]
    return " ".join(scopes)
# 充电状态 bsp-vcp-message/vehicle/charge
AUD_CHARGE = "1j0vgTqagJUHuT6nLmbTGx"  # 待实证, 预留

# 换token请求路径
EP_AUTH = "/api/auth"

# ---------- 状态 ----------
ATTR_STATUS = "status"
ATTR_BATTERY = "battery_level"
ATTR_RANGE = "range"
ATTR_ODOMETER = "odometer"
ATTR_LOCKED = "locked"
ATTR_CHARGING = "charging"
ATTR_TEMP = "temperature"

# 扫描周期（借鉴 huawei-auto-cloud 的可配置设计）
#   华为: DEFAULT=30s, MIN=10s
#   我们: DEFAULT=60s, MIN=30s（理想服务端压力较大，保守取 60s）
CONF_SCAN_INTERVAL = "scan_interval"
# 安全开关：关闭后所有车控实体变只读（防误操作）
CONF_ENABLE_CONTROL = "enable_control"
DEFAULT_ENABLE_CONTROL = True
DEFAULT_SCAN_INTERVAL_SECONDS = 60
MIN_SCAN_INTERVAL_SECONDS = 30
MAX_SCAN_INTERVAL_SECONDS = 3600

SCAN_INTERVAL_SECONDS = DEFAULT_SCAN_INTERVAL_SECONDS


def scan_interval_seconds(options=None) -> int:
    """从集成选项读取轮询间隔（秒），带范围钳制。"""
    try:
        sec = int((options or {}).get(CONF_SCAN_INTERVAL,
                                      DEFAULT_SCAN_INTERVAL_SECONDS))
    except (TypeError, ValueError):
        return DEFAULT_SCAN_INTERVAL_SECONDS
    return max(MIN_SCAN_INTERVAL_SECONDS, min(MAX_SCAN_INTERVAL_SECONDS, sec))

# 日志
LOGGER_NAME = "lixiang_auto"
