"""理想汽车 fan 实体 — 主驾/副驾座椅加热、通风（档位 UI）.

用 Home Assistant fan 域表现「关闭 / 低 / 中 / 高」，与巴法风扇 003 协议一致：
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
SEAT_FANS = (
    ("seat_fl_heat", "主驾座椅加热", "mdi:car-seat-heater",
     "seat_fl_heat", "flSeatHeatSw"),
    ("seat_fr_heat", "副驾座椅加热", "mdi:car-seat-heater",
     "seat_fr_heat", "frSeatHeatSw"),
    ("seat_fl_vent", "主驾座椅通风", "mdi:car-seat-cooler",
     "seat_fl_vent", "flSeatVentSw"),
    ("seat_fr_vent", "副驾座椅通风", "mdi:car-seat-cooler",
     "seat_fr_vent", "frSeatVentSw"),
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
    async_add_entities([
        LiCarSeatFan(coordinator, li_api, device_info, vin, *spec)
        for spec in SEAT_FANS
    ])


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
        vss = _seat_level_from_vss(
            (self.coordinator.data or {}).get("vss") or {}, self._state_key)
        if vss is not None:
            return vss
        if self._optimistic_level is not None:
            return self._optimistic_level
        return 0

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
    async def async_turn_on(self, percentage: int | None = None, **kwargs: Any) -> None:
        if percentage is not None:
            level = _percent_to_level(percentage)
            if level <= 0:
                level = DEFAULT_LEVEL
        else:
            # 预设模式
            preset = kwargs.get("preset_mode")
            if preset in _ORDERED_SPEEDS:
                level = _ORDERED_SPEEDS.index(preset) + 1
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
        """巴法 on#N 等外部调用：0-3 档。"""
        await self._send(max(0, min(3, int(level))))

    async def _send(self, level: int) -> None:
        cmd_data = _custom(self._control_type, level)
        try:
            res = await self.hass.async_add_executor_job(
                self._api.send_command, CMD_AC, cmd_data)
            self._last_result = res
            self._optimistic_level = max(0, min(3, level))
            _LOGGER.info("车控 %s 已执行: %s", cmd_data, res)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("车控 %s 失败: %s", cmd_data, err)
            raise
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
        self.async_write_ha_state()
