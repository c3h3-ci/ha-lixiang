"""理想汽车 fan 实体 — 主驾/副驾座椅加热、通风（档位 UI）.

用 Home Assistant fan 域表现「关闭 / 低 / 中 / 高」：
  档位 0=关, 1=低, 2=中, 3=高
  百分比: 0 / 33 / 66 / 100
  命令: remoteVehACSmartControl + LEVEL{1-3} / OFF

⚠️ 车控会真实作用于车辆。
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.fan import (
    FanEntity,
    FanEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_VIN, DOMAIN, LOGGER_NAME
from .gate import require_control
from .entity_helper import route_id_of_vin

_LOGGER = logging.getLogger(LOGGER_NAME)

CMD_AC = "remoteVehACSmartControl"
DEFAULT_TEMP = 22.5
DEFAULT_LEVEL = 3  # 打开默认高档

# ★ 2026-09-24 新增：乐观更新的有效期（秒）
#   发命令后，车机上报状态有延迟（几秒~几十秒）。
#   在这段时间内如果 VSS 还没跟上，就用乐观值显示，
#   避免"刚打开就显示关闭"的问题。
OPTIMISTIC_TTL = 150.0

# 低→中→高（HA fan 百分比 ordered list）
_ORDERED_SPEEDS = ["low", "medium", "high"]
_LEVEL_TO_PERCENT = {1: 33, 2: 66, 3: 100}
_PERCENT_TO_LEVEL = {0: 0, 33: 1, 66: 2, 100: 3}


def _seat_fan_features() -> FanEntityFeature:
    """必须含 TURN_ON/TURN_OFF，否则实体列表开关报「不支持 fan.turn_off」。

    HA 服务注册强制检查这些位（services.py: [FanEntityFeature.TURN_OFF]）。
    SET_SPEED=1 PRESET_MODE=8 TURN_OFF=16 TURN_ON=32。
    """
    features = FanEntityFeature.SET_SPEED | FanEntityFeature.PRESET_MODE
    # 优先用枚举成员
    features |= getattr(FanEntityFeature, "TURN_OFF", FanEntityFeature(0))
    features |= getattr(FanEntityFeature, "TURN_ON", FanEntityFeature(0))
    # 再按官方数值 OR 一遍（防止 getattr 拿到 0 但服务端仍校验 16/32）
    try:
        features |= FanEntityFeature(16)  # TURN_OFF
        features |= FanEntityFeature(32)  # TURN_ON
    except Exception:  # noqa: BLE001
        pass
    return features


_SEAT_FAN_FEATURES = _seat_fan_features()


def _level_to_percent(level: int) -> int:
    level = max(0, min(3, int(level)))
    if level <= 0:
        return 0
    return _LEVEL_TO_PERCENT[level]


def _percent_to_level(pct: int) -> int:
    pct = max(0, min(100, int(pct)))
    if pct <= 0:
        return 0
    if pct <= 33:
        return 1
    if pct <= 66:
        return 2
    return 3


def _custom(control_type: str, level: int) -> dict:
    if level is None or level <= 0:
        ctrl_value = "OFF"
    else:
        ctrl_value = f"LEVEL{int(level)}"
    return {
        "acCtrlType": control_type,
        "acCtrlValue": ctrl_value,
        "acCountdownTimer": 30,
        "acCtrlTemp": DEFAULT_TEMP,
    }


def _seat_level_from_vss(vss: dict, state_key: str) -> int | None:
    sig = (vss or {}).get(state_key) or {}
    raw = sig.get("value")
    if raw is None:
        return None
    try:
        return max(0, min(3, int(float(raw))))
    except (TypeError, ValueError):
        return None


# (suffix, name, icon, state_key, control_type)
# (唯一后缀, 名称, 图标, 状态key, controlType, 所属功能)
# ★ 2026-09-24 整合：在 shinnaluo 的 fan.py 基础上补上二排座椅
#   （他的原版只含主/副驾；二排是 L6 五座车实际有的）
SEAT_FANS = (
    ("seat_fl_heat", "主驾座椅加热", "mdi:car-seat-heater",
     "seat_fl_heat", "flSeatHeatSw", "座椅加热"),
    ("seat_fr_heat", "副驾座椅加热", "mdi:car-seat-heater",
     "seat_fr_heat", "frSeatHeatSw", "座椅加热"),
    ("seat_fl_vent", "主驾座椅通风", "mdi:car-seat-cooler",
     "seat_fl_vent", "flSeatVentSw", "座椅加热"),
    ("seat_fr_vent", "副驾座椅通风", "mdi:car-seat-cooler",
     "seat_fr_vent", "frSeatVentSw", "座椅加热"),
    # ★ 二排（L6 五座车的二排：左/中/右三个位置）
    #   ★★ 2026-09-26 更正：这 3 个 controlType 都是【App 就有的】，
    #      定义在 assets/index.vehicle.js 的 jobTypes 对象里：
    #        secLSeatHeatSw / secLSeatVentSw / secMSeatHeatSw
    #        secRSeatHeatSw / secRSeatVentSw
    #      ⚠️ 之前的注释说"App 里没有、是推测命名" —— 那是错的，
    #         因为只查了 smali（MVehicleControlManager 里只有 6 个），
    #         没查 JS bundle（jobTypes 里有 12 个）。
    #      ★ 权威来源 = JS bundle 的 jobTypes；smali 那份是子集白名单。
    ("seat_sl_heat", "二排左座椅加热", "mdi:car-seat-heater",
     "seat_sl_heat", "secLSeatHeatSw", "二排座椅"),
    ("seat_sr_heat", "二排右座椅加热", "mdi:car-seat-heater",
     "seat_sr_heat", "secRSeatHeatSw", "二排座椅"),
    ("seat_sm_heat", "二排中座椅加热", "mdi:car-seat-heater",
     "seat_sm_heat", "secMSeatHeatSw", "二排座椅"),
    ("seat_sl_vent", "二排左座椅通风", "mdi:car-seat-cooler",
     "seat_sl_vent", "secLSeatVentSw", "二排座椅"),
    ("seat_sr_vent", "二排右座椅通风", "mdi:car-seat-cooler",
     "seat_sr_vent", "secRSeatVentSw", "二排座椅"),
    # 注：App 还有三排 3 个（thirdL/M/RSeatHeatSw），L6 五座车没有 → 不实现
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][config_entry.entry_id]
    coordinator, li_api = data["coordinator"], data.get("li_api")
    vin = config_entry.data.get(CONF_VIN) or ""
    identifiers = {(DOMAIN, vin)} if vin else {(DOMAIN, config_entry.entry_id)}
    device_info = DeviceInfo(
        identifiers=identifiers, manufacturer="理想汽车",
        model="理想 L6", name="Li Auto L6" if vin else "Li Auto",
    )
    if li_api is None:
        _LOGGER.warning("无密码登录凭据，跳过 fan 实体")
        return
    # 按车型功能过滤（features 由 __init__.py 探测）
    features = (data.get("features") or {})
    entities = []
    for spec in SEAT_FANS:
        # spec = (suffix, name, icon, state_key, ctrl_type, feat)
        feat = spec[5] if len(spec) > 5 else None
        if feat and not features.get(feat, True):
            _LOGGER.debug("车型不支持 %s，跳过 %s", feat, spec[0])
            continue
        entities.append(LiCarSeatFan(coordinator, li_api, device_info, vin,
                                     *spec[:5]))
    async_add_entities(entities)


class LiCarSeatFan(CoordinatorEntity, FanEntity):
    """座椅加热/通风：关闭 / 低 / 中 / 高（fan UI）."""

    _attr_has_entity_name = True
    # ★ 类属性：在 cached_property 首次读取前就位，避免 super().__init__ 时缓存成 0
    _attr_supported_features = _SEAT_FAN_FEATURES
    _attr_preset_modes = list(_ORDERED_SPEEDS)
    _attr_speed_count = 3
    # 关闭 HA 自动补 TURN_* 的兼容逻辑（我们已显式声明）
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator, li_api, device_info, vin: str,
                 suffix: str, name: str, icon: str,
                 state_key: str, control_type: str) -> None:
        # 先写 features，再 super().__init__（cached_property 安全）
        self._attr_supported_features = _SEAT_FAN_FEATURES
        super().__init__(coordinator)
        self._api = li_api
        self._state_key = state_key
        self._control_type = control_type
        self._suffix = suffix
        self._attr_name = name
        self._attr_icon = icon
        self._rid = route_id_of_vin(vin)
        self._attr_unique_id = f"{DOMAIN}_{self._rid}_fan_{suffix}"
        self._attr_device_info = device_info
        self._optimistic_level: int | None = None
        # ★ 乐观值有效期（monotonic 时间戳）
        self._optimistic_until: float = 0.0
        self._last_result: dict | None = None
        # 再写一次，防止 super 里被覆盖
        self._attr_supported_features = _SEAT_FAN_FEATURES
        self._attr_preset_modes = list(_ORDERED_SPEEDS)
        self._attr_speed_count = 3

    @property
    def supported_features(self) -> FanEntityFeature:
        """始终返回含 TURN_ON/TURN_OFF 的特性（绕过可能已缓存的 0）。"""
        return _SEAT_FAN_FEATURES

    @property
    def current_level(self) -> int:
        """当前档位（0=关, 1-3）。

        ★ 2026-09-24 修复（用户反馈"打开开关默认3档，
          在其他地方切换成1档就显示关闭了"）：

          问题：原逻辑【VSS 优先】，但 VSS 上报有延迟。
                发命令后立刻拉 VSS（还是旧值 0）→ 显示关闭。

          新逻辑（乐观更新带 TTL）：
            ① 乐观值未过期 且 与 VSS 不一致 → 用乐观值（保持显示）
            ② 乐观值与 VSS 一致 → 清掉乐观值，用 VSS
            ③ 超过 TTL → 无条件用 VSS（以服务端为准）
        """
        import time as _t

        vss = _seat_level_from_vss(
            (self.coordinator.data or {}).get("vss") or {}, self._state_key)

        if self._optimistic_level is not None:
            if _t.monotonic() < self._optimistic_until:
                # 乐观窗口内：VSS 未追上就继续用乐观值
                if vss is None or vss != self._optimistic_level:
                    return self._optimistic_level
            # 已一致或已过期 → 清除乐观状态
            self._optimistic_level = None
            self._optimistic_until = 0.0

        return vss if vss is not None else 0

    @property
    def percentage(self) -> int | None:
        return _level_to_percent(self.current_level)

    @property
    def speed_count(self) -> int:
        return 3

    @property
    def preset_mode(self) -> str | None:
        lvl = self.current_level
        if lvl <= 0:
            return None
        return _ORDERED_SPEEDS[min(lvl, 3) - 1]

    @property
    def is_on(self) -> bool | None:
        return self.current_level > 0

    @property
    def extra_state_attributes(self) -> dict:
        attrs: dict = {
            "cmd_key": CMD_AC,
            "control_type": self._control_type,
            "level": self.current_level,
            "level_range": "0关/1低/2中/3高",
            "default_on_level": DEFAULT_LEVEL,
        }
        if self._last_result is not None:
            attrs["last_command_result"] = self._last_result
        return attrs

    @require_control
    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """打开座椅加热/通风.

        ★ 2026-09-24 修复 bug（用户反馈"加热出错"）：
          HA 的 FanEntity 内部调用约定是：
            await self.async_turn_on(percentage, preset_mode, **kwargs)
          ★ 两个【位置参数】！
          原签名只有 (percentage, **kwargs) → TypeError:
            "takes from 1 to 2 positional arguments but 3 were given"

          依据：homeassistant/components/fan/__init__.py:315
        """
        if percentage is not None:
            level = _percent_to_level(percentage)
            if level <= 0:
                level = DEFAULT_LEVEL
        elif preset_mode in _ORDERED_SPEEDS:
            level = _ORDERED_SPEEDS.index(preset_mode) + 1
        else:
            level = DEFAULT_LEVEL
        await self._send(level)

    @require_control
    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send(0)

    @require_control
    async def async_set_percentage(self, percentage: int, **kwargs: Any) -> None:
        level = _percent_to_level(percentage)
        if level <= 0:
            await self._send(0)
        else:
            await self._send(level)

    @require_control
    async def async_set_preset_mode(self, preset_mode: str, **kwargs: Any) -> None:
        if preset_mode not in _ORDERED_SPEEDS:
            return
        level = _ORDERED_SPEEDS.index(preset_mode) + 1
        await self._send(level)

    @require_control
    async def async_set_level(self, level: int) -> None:
        """外部服务调用：0-3 档。"""
        await self._send(max(0, min(3, int(level))))

    async def _send(self, level: int) -> None:
        cmd_data = _custom(self._control_type, level)
        try:
            res = await self.hass.async_add_executor_job(
                self._api.send_command, CMD_AC, cmd_data)
            self._last_result = res
            self._optimistic_level = max(0, min(3, level))
            # ★ 记录有效期起点（TTL 内保持乐观显示）
            import time as _t2
            self._optimistic_until = _t2.monotonic() + OPTIMISTIC_TTL
            _LOGGER.info("车控 %s 已执行: %s（乐观值 %d，%d秒内优先）",
                         cmd_data, res, self._optimistic_level,
                         int(OPTIMISTIC_TTL))
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("车控 %s 失败: %s", cmd_data, err)
            raise
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
        self.async_write_ha_state()
