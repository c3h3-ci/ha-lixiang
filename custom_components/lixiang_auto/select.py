"""理想汽车模式选择实体（select 平台）.

提供空调控制模式选择（前排空调开关 vs 前排自动空调）—— 这两个 acCtrlType
均已实测可用（cmd_table_verified.json: acCtrlType=frtACSw / frtACAUTOSw 均可）。

★ 说明: 本项目【没有】把充电上限/能量回收做成 select，因为:
  - 充电上限的写入命令不在已实测命令表内（cmdKey/cmdData 均未确认）；
  - 能量回收等级同理。
  宁可少做，也不给出虚假的可控能力。这两项目前仅作 sensor 只读展示。

当前实体用途: 维护"下次开空调时使用的 acCtrlType"，持久化在实体属性里，
由 climate 实体读取（见 climate.AC_TYPE_*）。这是一个配置型 select，不发命令。

⚠️ 修改该 select 本身不下发车控命令。
"""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_VIN, DOMAIN, LOGGER_NAME
from .gate import require_control
from .entity_helper import route_id_of_vin

_LOGGER = logging.getLogger(LOGGER_NAME)

# 显示名 → acCtrlType（两者均已实测可用）
AC_TYPE_OPTIONS = {
    "前排空调": "frtACSw",
    "前排自动空调": "frtACAUTOSw",
}
_OPTION_TO_TYPE = AC_TYPE_OPTIONS
_TYPE_TO_OPTION = {v: k for k, v in AC_TYPE_OPTIONS.items()}

DEFAULT_OPTION = "前排空调"


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
        _LOGGER.warning("无密码登录凭据，跳过 select 实体")
        return
    async_add_entities([LiCarAcTypeSelect(coordinator, li_api, device_info, vin)])


class LiCarAcTypeSelect(CoordinatorEntity, SelectEntity):
    """空调控制类型选择（配置型，仅维护 acCtrlType，不下发命令）."""

    _attr_has_entity_name = True
    _attr_name = "空调控制类型"
    _attr_icon = "mdi:air-conditioner"
    _attr_options = list(AC_TYPE_OPTIONS.keys())
    # 配置型 → 设备页归入「配置」区，与实体控制分开
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, li_api, device_info, vin: str) -> None:
        super().__init__(coordinator)
        self._api = li_api
        self._rid = route_id_of_vin(vin)

        self._attr_unique_id = f"{DOMAIN}_{self._rid}_sel_ac_ctrl_type"
        self._attr_device_info = device_info
        self._option = DEFAULT_OPTION

    @property
    def current_option(self) -> str:
        return self._option

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "ac_ctrl_type": _OPTION_TO_TYPE.get(self._option, ""),
            "role": "配置型（修改此项本身不下发车控命令）",
            "options_map": dict(AC_TYPE_OPTIONS),
        }

    @require_control
    async def async_select_option(self, option: str) -> None:
        if option not in AC_TYPE_OPTIONS:
            _LOGGER.warning("未知空调控制类型: %s", option)
            return
        self._option = option
        _LOGGER.info("空调控制类型设为 %s (%s)", option, _OPTION_TO_TYPE[option])
        self.async_write_ha_state()


def option_to_type(option: str) -> str:
    """选项名 → acCtrlType（供 climate 复用）."""
    return _OPTION_TO_TYPE.get(option, AC_TYPE_OPTIONS[DEFAULT_OPTION])


def type_to_option(ac_type: str) -> str:
    """acCtrlType → 选项名."""
    return _TYPE_TO_OPTION.get(ac_type, DEFAULT_OPTION)
