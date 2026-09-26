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
    """基础特性：SET_SPEED + PRESET_MODE。

    TURN_ON/TURN_OFF 另在 __init__ 里按小米 xiaomi_home 方式
    用 `|=` 写入，并依赖 HA 的 turn_on/off 兼容补位兜底。
    SET_SPEED=1 PRESET_MODE=8 TURN_OFF=16 TURN_ON=32（HA 官方值）。
    """
    return FanEntityFeature.SET_SPEED | FanEntityFeature.PRESET_MODE


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
# ★ 排序约定：按座位位置分组，每座「先加热、后通风」：
#   主驾 → 副驾 → 二排左 → 二排中 → 二排右
SEAT_FANS = (
    # ---- 主驾 ----
    ("seat_fl_heat", "主驾座椅加热", "mdi:car-seat-heater",
     "seat_fl_heat", "flSeatHeatSw", "座椅加热"),
    ("seat_fl_vent", "主驾座椅通风", "mdi:car-seat-cooler",
     "seat_fl_vent", "flSeatVentSw", "座椅加热"),
    # ---- 副驾 ----
    ("seat_fr_heat", "副驾座椅加热", "mdi:car-seat-heater",
     "seat_fr_heat", "frSeatHeatSw", "座椅加热"),
    ("seat_fr_vent", "副驾座椅通风", "mdi:car-seat-cooler",
     "seat_fr_vent", "frSeatVentSw", "座椅加热"),
    # ---- 二排左 ----
    ("seat_sl_heat", "二排左座椅加热", "mdi:car-seat-heater",
     "seat_sl_heat", "secLSeatHeatSw", "二排座椅"),
    ("seat_sl_vent", "二排左座椅通风", "mdi:car-seat-cooler",
     "seat_sl_vent", "secLSeatVentSw", "二排座椅"),
    # ---- 二排中（仅有加热信号；App 无 controlType，命名推测）----
    ("seat_sm_heat", "二排中座椅加热", "mdi:car-seat-heater",
     "seat_sm_heat", "secMSeatHeatSw", "二排座椅"),
    # ---- 二排右 ----
    ("seat_sr_heat", "二排右座椅加热", "mdi:car-seat-heater",
     "seat_sr_heat", "secRSeatHeatSw", "二排座椅"),
    ("seat_sr_vent", "二排右座椅通风", "mdi:car-seat-cooler",
     "seat_sr_vent", "secRSeatVentSw", "二排座椅"),
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
    """座椅加热/通风：关闭 / 低 / 中 / 高（fan UI）.

    ★ 特性位对齐 xiaomi_home/fan.py：
      · __init__ 里 `|=` 写入 TURN_ON | TURN_OFF
      · 不关 `_enable_turn_on_off_backwards_compatibility`
        （关了之后若特性没写上，列表开关会报「不支持 fan.turn_off」）
      · async_turn_on(percentage, preset_mode, **kwargs) 两个位置参数
        （HA FanEntity 约定，否则 TypeError: 3 positional arguments）
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator, li_api, device_info, vin: str,
                 suffix: str, name: str, icon: str,
                 state_key: str, control_type: str) -> None:
        super().__init__(coordinator)
        # ★ 模仿 xiaomi_home：super 之后再写 features
        self._attr_supported_features = FanEntityFeature(
            _SEAT_FAN_FEATURES
        )
        self._attr_supported_features |= FanEntityFeature.TURN_ON
        self._attr_supported_features |= FanEntityFeature.TURN_OFF
        self._attr_preset_modes = list(_ORDERED_SPEEDS)
        self._attr_speed_count = 3

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
        self._optimistic_until: float = 0.0
        self._last_result: dict | None = None

    @property
    def current_level(self) -> int:
        """当前档位（0=关, 1-3）。

        优先级：有效乐观值 → VSS。
        乐观 TTL 内 VSS 未跟上则继续用乐观值。
        """
        import time as _t

        vss = _seat_level_from_vss(
            (self.coordinator.data or {}).get("vss") or {}, self._state_key)

        if self._optimistic_level is not None:
            if _t.monotonic() < self._optimistic_until:
                if vss is None or vss != self._optimistic_level:
                    return self._optimistic_level
            self._optimistic_level = None
            self._optimistic_until = 0.0

        return vss if vss is not None else 0

    @property
    def percentage(self) -> int | None:
        # ★ 同步写 _attr_percentage，兼容父类 cached_property 读 _attr
        pct = _level_to_percent(self.current_level)
        if getattr(self, "_attr_percentage", None) != pct:
            self._attr_percentage = pct
        return pct

    @property
    def speed_count(self) -> int:
        return 3

    @property
    def preset_mode(self) -> str | None:
        lvl = self.current_level
        mode = None if lvl <= 0 else _ORDERED_SPEEDS[min(lvl, 3) - 1]
        if getattr(self, "_attr_preset_mode", None) != mode:
            self._attr_preset_mode = mode
        return mode

    @property
    def is_on(self) -> bool | None:
        # 与详情页一致：档位 > 0 即为开
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

    def _apply_level_state(self, level: int) -> None:
        """命令成功后：同步乐观值 + _attr_*，保证列表开关与详情一致。"""
        import time as _t
        level = max(0, min(3, int(level)))
        self._optimistic_level = level
        self._optimistic_until = _t.monotonic() + OPTIMISTIC_TTL
        self._attr_percentage = _level_to_percent(level)
        self._attr_preset_mode = (
            None if level <= 0 else _ORDERED_SPEEDS[min(level, 3) - 1]
        )
        # 前端可能缓存 is_on/percentage；强制再写一次状态
        for cache_attr in ("is_on", "percentage", "preset_mode", "state"):
            try:
                self.__dict__.pop(cache_attr, None)
            except Exception:  # noqa: BLE001
                pass

    @require_control
    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """打开：支持 HA 传 (percentage, preset_mode) 两个位置参数。"""
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
            # 未知预设不要静默失败——按低档兜底，保证详情页操作有反馈
            level = 1
        else:
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
            self._apply_level_state(level)
            _LOGGER.info("车控 %s 已执行: %s（level=%s pct=%s）",
                         cmd_data, res, self._optimistic_level,
                         self._attr_percentage)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("车控 %s 失败: %s", cmd_data, err)
            raise
        # 先写状态（列表开关立刻反映），再补拉 VSS
        self.async_write_ha_state()
        try:
            await self.coordinator.async_request_refresh()
        finally:
            # 刷新后再写一次：VSS 若已跟上用 VSS，否则仍是乐观值
            self.async_write_ha_state()
