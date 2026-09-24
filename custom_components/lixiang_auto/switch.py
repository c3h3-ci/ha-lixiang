"""理想汽车开关实体（switch 平台）— 车控 cmd/send.

命令（remoteVehACSmartControl 自定义控制）:
  {"acCtrlType": controlType, "acCtrlValue": "OFF"|"LEVEL1"|"LEVEL2"|"LEVEL3",
   "acCountdownTimer": 30, "acCtrlTemp": <Number>}

开关逻辑:
  打开 → 默认 LEVEL3；关闭 → OFF；状态读 VSS（0=关, 非0=开）。
  档位 0-3 可用 number 实体调节；巴法 on#N 也走 async_set_level。

仅：方向盘 + 主驾/副驾 加热通风。

⚠️ 车控会真实作用于车辆。
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
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
# 主驾/副驾加热通风：打开默认 3 档
DEFAULT_LEVEL = 3
DEFAULT_TEMP = 22.5

_AC_ONOFF_TYPES = frozenset({
    "strgWhlHeatSw", "acHeatFast", "dfstSw", "acCoolFast",
})


def format_temp(temp: float | None) -> float:
    try:
        t = float(temp) if temp is not None else 16.0
    except (TypeError, ValueError):
        t = 16.0
    return round(t * 2) / 2


def _custom(control_type: str, level: int) -> dict:
    if level is None or level <= 0:
        ctrl_value = "OFF"
    elif control_type in _AC_ONOFF_TYPES:
        ctrl_value = "ON"
    else:
        ctrl_value = f"LEVEL{int(level)}"
    return {
        "acCtrlType": control_type,
        "acCtrlValue": ctrl_value,
        "acCountdownTimer": 30,
        "acCtrlTemp": format_temp(DEFAULT_TEMP),
    }


# (suffix, name, icon, state_key, control_type, feature|None)
# 座椅加热/通风已迁至 fan.py（档位 UI）；此处仅方向盘 + 寻车
SWITCHES = (
    ("wheel_heat", "方向盘加热", "mdi:steering",
     "wheel_heat", "strgWhlHeatSw", "方向盘加热"),
)


def seat_level_from_vss(vss: dict, state_key: str) -> int | None:
    sig = (vss or {}).get(state_key) or {}
    raw = sig.get("value")
    if raw is None:
        return None
    try:
        return max(0, min(3, int(float(raw))))
    except (TypeError, ValueError):
        return None


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
        _LOGGER.warning("无密码登录凭据，跳过 switch 实体")
        return

    features = (data.get("features") or {})
    specs = [
        spec for spec in SWITCHES
        if spec[5] is None or features.get(spec[5], True)
    ]
    async_add_entities([
        LiCarSwitch(coordinator, li_api, device_info, vin, *spec[:5])
        for spec in specs
    ] + [LiCarFindCarSwitch(coordinator, li_api, device_info, vin)])


class LiCarSwitch(CoordinatorEntity, SwitchEntity):
    """座椅/方向盘开关。打开=3 档；关闭=0。"""

    _attr_has_entity_name = True

    def __init__(self, coordinator, li_api, device_info, vin: str,
                 suffix: str, name: str, icon: str,
                 state_key: str, control_type: str) -> None:
        super().__init__(coordinator)
        self._api = li_api
        self._state_key = state_key
        self._control_type = control_type
        self._suffix = suffix
        self._attr_name = name
        self._attr_icon = icon
        self._rid = route_id_of_vin(vin)

        self._attr_unique_id = f"{DOMAIN}_{self._rid}_sw_{suffix}"
        self._attr_device_info = device_info
        self._optimistic_on: bool | None = None
        self._last_result: dict | None = None

    @property
    def current_level(self) -> int | None:
        if self._control_type in _AC_ONOFF_TYPES:
            return None
        return seat_level_from_vss(
            (self.coordinator.data or {}).get("vss") or {}, self._state_key)

    @property
    def is_on(self) -> bool | None:
        sig = (self.coordinator.data or {}).get("vss", {}).get(self._state_key)
        if sig and sig.get("value") is not None:
            v = sig["value"]
            try:
                return int(float(v)) != 0
            except (TypeError, ValueError):
                return bool(v)
        return self._optimistic_on

    @property
    def extra_state_attributes(self) -> dict:
        attrs: dict = {
            "cmd_key": CMD_AC,
            "control_type": self._control_type,
            "level_range": "0(关)/1-3(档位)",
            "default_on_level": DEFAULT_LEVEL,
        }
        lvl = self.current_level
        if lvl is not None:
            attrs["level"] = lvl
        if self._last_result is not None:
            attrs["last_command_result"] = self._last_result
        return attrs

    @require_control
    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._send(DEFAULT_LEVEL)

    @require_control
    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send(0)

    @require_control
    async def async_set_level(self, level: int) -> None:
        """设 0-3 档（巴法 on#N / 自动化调用）。"""
        lvl = max(0, min(3, int(level)))
        await self._send(lvl)

    async def _send(self, level: int) -> None:
        cmd_data = _custom(self._control_type, level)
        try:
            res = await self.hass.async_add_executor_job(
                self._api.send_command, CMD_AC, cmd_data)
            self._last_result = res
            self._optimistic_on = level != 0
            _LOGGER.info("车控 %s 已执行: %s", cmd_data, res)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("车控 %s 失败: %s", cmd_data, err)
            self._optimistic_on = None
            raise
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()


class LiCarFindCarSwitch(CoordinatorEntity, SwitchEntity):
    """寻车 momentary switch — 巴法云不识别 button，用「打开」触发鸣笛闪灯."""

    _attr_has_entity_name = True
    _attr_name = "寻车"
    _attr_icon = "mdi:car-search"

    def __init__(self, coordinator, li_api, device_info, vin: str) -> None:
        super().__init__(coordinator)
        self._api = li_api
        self._rid = route_id_of_vin(vin)
        self._attr_unique_id = f"{DOMAIN}_{self._rid}_sw_find_car"
        self._attr_device_info = device_info
        self._on_until: float | None = None
        self._last_result: dict | None = None

    @property
    def is_on(self) -> bool | None:
        import time
        if self._on_until is None:
            return False
        if time.monotonic() >= self._on_until:
            self._on_until = None
            return False
        return True

    @property
    def extra_state_attributes(self) -> dict:
        attrs: dict = {"cmd_key": "remoteVehSearch", "momentary": True}
        if self._last_result is not None:
            attrs["last_command_result"] = self._last_result
        return attrs

    @require_control
    async def async_turn_on(self, **kwargs: Any) -> None:
        import time
        try:
            res = await self.hass.async_add_executor_job(
                self._api.send_command_fire_and_forget,
                "remoteVehSearch", {"searchType": "0"})
            self._last_result = res
            self._on_until = time.monotonic() + 8
            _LOGGER.info("寻车已触发: %s", res)
            self.async_write_ha_state()
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("寻车失败: %s", err)
            raise

    @require_control
    async def async_turn_off(self, **kwargs: Any) -> None:
        self._on_until = None
        self.async_write_ha_state()
