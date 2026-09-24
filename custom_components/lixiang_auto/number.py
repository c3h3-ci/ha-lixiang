"""理想汽车数值设置实体（number 平台）.

功能（仅保留已实测命令）:
  - 空调设定温度: remoteVehACSmartControl
      {"acCtrlValue":"ON","acCtrlType":"frtACSw","acCountdownTimer":"15",
       "acCtrlTemp":<16-30>}     ← acCtrlTemp 必须是 Number, 不能 str()

★ 旧实现用 remote_ac_temp_adjust + {"temperature":..} 是错的（APK 枚举值），
  已修正为真实的 remoteVehACSmartControl + acCtrlTemp。

★ 旧的"充电上限"(charge_percent + {"chargePercent":..}) 已【移除】:
  该命令不在已实测命令表 (cmd_table_verified.json) 内，无法确认 cmdKey/cmdData，
  保留会给出虚假的控制能力。充电上限目前只作为 sensor 只读展示。

状态读取: VSS 实时信号 ac_set_temp (Vehicle.Cabin.AC.SetTemp)

⚠️ 写入会真实作用于车辆。
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_VIN, DOMAIN, LOGGER_NAME
from .gate import require_control
from .entity_helper import route_id_of_vin

_LOGGER = logging.getLogger(LOGGER_NAME)

CMD_AC = "remoteVehACSmartControl"
AC_TYPE_FRONT = "frtACSw"
AC_COUNTDOWN = "15"

AC_MIN_TEMP = 16
AC_MAX_TEMP = 30


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
        _LOGGER.warning("无密码登录凭据，跳过 number 实体")
        return
    # ★ 2026-09-24 补充：座椅加热/通风档位（0-3）
    #   0 = 关闭，1/2/3 = 档位
    #   controlType 来自 VehicleControlModel$Companion
    seat_specs = [
        ("seat_fl_heat_level", "主驾加热档位", "seat_fl_heat", "flSeatHeatSw",
         "mdi:car-seat-heater", "座椅加热"),
        ("seat_fr_heat_level", "副驾加热档位", "seat_fr_heat", "frSeatHeatSw",
         "mdi:car-seat-heater", "座椅加热"),
        ("seat_sl_heat_level", "二排左加热档位", "seat_sl_heat", "secLSeatHeatSw",
         "mdi:car-seat-heater", "二排座椅"),
        ("seat_sr_heat_level", "二排右加热档位", "seat_sr_heat", "secRSeatHeatSw",
         "mdi:car-seat-heater", "二排座椅"),
        ("seat_fl_vent_level", "主驾通风档位", "seat_fl_vent", "flSeatVentSw",
         "mdi:car-seat-cooler", "座椅加热"),
        ("seat_fr_vent_level", "副驾通风档位", "seat_fr_vent", "frSeatVentSw",
         "mdi:car-seat-cooler", "座椅加热"),
        ("seat_sl_vent_level", "二排左通风档位", "seat_sl_vent", "secLSeatVentSw",
         "mdi:car-seat-cooler", "二排座椅"),
        ("seat_sr_vent_level", "二排右通风档位", "seat_sr_vent", "secRSeatVentSw",
         "mdi:car-seat-cooler", "二排座椅"),
    ]

    features = (data.get("features") or {})
    entities = [
        LiCarNumber(
            coordinator, li_api, device_info, vin,
            suffix="ac_set_temp", name="空调设定温度",
            icon="mdi:thermostat", state_key="ac_set_temp",
            cmd_key=CMD_AC, data_builder=_ac_temp_payload,
            minimum=AC_MIN_TEMP, maximum=AC_MAX_TEMP, step=1,
            unit=UnitOfTemperature.CELSIUS,
            device_class=NumberDeviceClass.TEMPERATURE,
        ),
    ]
    for suffix, name, state_key, ctrl_type, icon, feat in seat_specs:
        if not features.get(feat, True):
            _LOGGER.debug("车型不支持 %s，跳过 %s", feat, suffix)
            continue
        entities.append(
            LiCarNumber(
                coordinator, li_api, device_info, vin,
                suffix=suffix, name=name,
                icon=icon, state_key=state_key,
                cmd_key=CMD_AC, data_builder=_seat_level_payload_factory(ctrl_type),
                minimum=0, maximum=3, step=1,
                unit=None, device_class=None,
            )
        )
    async_add_entities(entities)


def _ac_temp_payload(value: float) -> dict:
    """构造空调设定温度报文. ★ acCtrlTemp 必须是 Number."""
    f = float(value)
    return {
        "acCtrlValue": "ON",
        "acCtrlType": AC_TYPE_FRONT,
        "acCountdownTimer": AC_COUNTDOWN,
        "acCtrlTemp": int(f) if f.is_integer() else round(f, 1),
    }


def _seat_level_payload_factory(control_type: str):
    """构造座椅加热/通风的档位报文（0=关，1/2/3=档位）.

    ★ 2026-09-24 依据 App 的 XVehicleJobHelper$Companion.customVehicleACControl():
        RN 侧入参 {controlType, level, temp} 会被翻译为：
          {"acCtrlType": controlType,
           "acCtrlValue": level>0 ? "LEVEL"+level : "OFF",
           "acCountdownTimer": 30,
           "acCtrlTemp": <Number>}
      ⚠️ 座椅类用的是 "LEVEL1/2/3" 字符串编码，没有 level 字段！
         （白名单类如 strgWhlHeatSw 才用 "ON"/"OFF"）
    """
    def builder(value: float) -> dict:
        lv = int(round(float(value)))
        lv = max(0, min(3, lv))
        return {
            "acCtrlType": control_type,
            "acCtrlValue": f"LEVEL{lv}" if lv > 0 else "OFF",
            "acCountdownTimer": 30,
            "acCtrlTemp": DEFAULT_SEAT_TEMP,
        }
    return builder


DEFAULT_SEAT_TEMP = 22.5


class LiCarNumber(CoordinatorEntity, NumberEntity):
    """理想车数值设置."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, li_api, device_info, vin: str, *,
                 suffix: str, name: str, icon: str, state_key: str,
                 cmd_key: str, data_builder,
                 minimum: float, maximum: float, step: float,
                 unit: str | None, device_class) -> None:
        super().__init__(coordinator)
        self._api = li_api
        self._state_key = state_key
        self._cmd_key = cmd_key
        self._data_builder = data_builder
        self._attr_name = name
        self._attr_icon = icon
        self._rid = route_id_of_vin(vin)

        self._attr_unique_id = f"{DOMAIN}_{self._rid}_num_{suffix}"
        self._attr_device_info = device_info
        self._attr_native_min_value = minimum
        self._attr_native_max_value = maximum
        self._attr_native_step = step
        if unit:
            self._attr_native_unit_of_measurement = unit
        if device_class is not None:
            self._attr_device_class = device_class
        self._optimistic_value: float | None = None
        self._last_result: dict | None = None

    @property
    def native_value(self) -> float | None:
        sig = (self.coordinator.data or {}).get("vss", {}).get(self._state_key)
        if sig and sig.get("value") is not None:
            try:
                return float(sig["value"])
            except (TypeError, ValueError):
                pass
        return self._optimistic_value

    @property
    def extra_state_attributes(self) -> dict:
        attrs: dict = {"cmd_key": self._cmd_key}
        if self._last_result is not None:
            attrs["last_command_result"] = self._last_result
        return attrs

    @require_control
    async def async_set_native_value(self, value: float) -> None:
        cmd_data = self._data_builder(value)
        try:
            res = await self.hass.async_add_executor_job(
                self._api.send_command, self._cmd_key, cmd_data)
            self._last_result = res
            self._optimistic_value = float(value)
            _LOGGER.info("车控 %s %s 已执行: %s", self._cmd_key, cmd_data, res)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("车控 %s %s 失败: %s", self._cmd_key, cmd_data, err)
            self._optimistic_value = None
            raise
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
