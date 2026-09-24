"""Li Auto (Ideal Car) Home Assistant integration.

认证链 (2026-09-06 端到端验证): PAKE 密码登录 → 会话 cookie 换 vss scope token
→ x-chj 签名调 vss/get-batch 读实时信号. 见 docs/实时状态打通_20260906.md.

车控 (2026-09-22 实测打通): 同一登录会话换【双 token】——
  MESH token (Authorization 头) + VAT token (body.token 字段)
→ x-chj 签名 POST cmd/send → 轮询 cmd-result 至 pushState=5.
见 docs/车控Token突破_20260922.md / docs/HA集成车控实现_20260922.md.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, aiohttp_client
from homeassistant.helpers.typing import ConfigType

from .client import LiCarClient
from .const import (
    CONF_APP_TOKEN,
    CONF_DEVICE_ID,
    CONF_HAC_KEY,
    CONF_KEY_ID,
    CONF_PASSWORD,
    CONF_PHONE,
    CONF_VIN,
    CONF_XDEV,
    DEFAULT_APP_TOKEN,
    DEFAULT_DEVICE_ID,
    DEFAULT_HAC_KEY,
    DEFAULT_KEY_ID,
    DEFAULT_XDEV,
    DOMAIN,
    LOGGER_NAME,
)
from .coordinator import LiCarCoordinator
from .signer import LiCarSigner

PLATFORMS: list[Platform] = [
    Platform.SENSOR, Platform.BINARY_SENSOR, Platform.DEVICE_TRACKER,
    Platform.LOCK, Platform.SWITCH, Platform.BUTTON, Platform.NUMBER,
    Platform.CLIMATE, Platform.SELECT, Platform.NOTIFY, Platform.COVER,
    Platform.FAN,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LOGGER = logging.getLogger(LOGGER_NAME)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """集成加载时执行（早于 config_entry）。

    ★ 在这里注册登录辅助页面 —— 因为用户【还没有配置条目】时
      就可能需要访问 /lixiang-login（首次登录场景）。
    """
    hass.data.setdefault(DOMAIN, {})
    try:
        from .auth_web import async_register_login_views
        await async_register_login_views(hass)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("注册登录辅助页面失败: %s", err)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """从配置条目设置理想汽车集成."""
    hass.data.setdefault(DOMAIN, {})

    session = aiohttp_client.async_get_clientsession(hass)

    hac_key = entry.data.get(CONF_HAC_KEY) or DEFAULT_HAC_KEY
    key_id = entry.data.get(CONF_KEY_ID) or DEFAULT_KEY_ID
    xdev = entry.data.get(CONF_XDEV) or DEFAULT_XDEV
    app_token = entry.data.get(CONF_APP_TOKEN) or DEFAULT_APP_TOKEN
    device_id = entry.data.get(CONF_DEVICE_ID) or DEFAULT_DEVICE_ID
    vin = entry.data.get(CONF_VIN)

    signer = LiCarSigner(hac_key=hac_key, key_id=key_id, device_id=xdev)
    client = LiCarClient(session, signer, app_token=app_token, vin=vin)

    li_api = None
    phone = entry.data.get(CONF_PHONE)
    password = entry.data.get(CONF_PASSWORD)
    if phone and password:
        from .li_api import LiApiClient

        li_api = LiApiClient(
            phone=phone, password=password, vin=vin or "",
            hac_key=hac_key, key_id=key_id, xdev=xdev,
            app_token=app_token, device_id=device_id,
        )
    else:
        _LOGGER.warning(
            "lixiang_auto 未配置密码登录 (phone/password 缺失), "
            "仅提供静态车辆信息, 无实时信号."
        )

    coordinator = LiCarCoordinator(hass, client, li_api=li_api, entry=entry)

    # 首次刷新（验证凭据）
    await coordinator.async_config_entry_first_refresh()

    # 车型功能探测（VSS 信号探测法; 失败则全部按不支持处理, 不影响只读实体）
    features: dict[str, bool] = {}
    vehicle_config: dict[str, str] = {}
    if li_api is not None:
        try:
            from .features import detect_features, read_vehicle_config

            features = await hass.async_add_executor_job(detect_features, li_api)
            vehicle_config = await hass.async_add_executor_job(
                read_vehicle_config, li_api)
            _LOGGER.info(
                "车型功能: 支持=%s",
                [k for k, v in features.items() if v] or "（探测失败）")
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("车型功能探测异常（忽略）: %s", err)

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator, "client": client, "li_api": li_api,
        "features": features, "vehicle_config": vehicle_config,
    }

    # ★ 注册服务（仅首次）
    _async_register_services(hass)

    # ★ 注册首次登录辅助页面（让用户自己过滑动验证）
    try:
        from .auth_web import async_register_login_views
        await async_register_login_views(hass)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("注册登录辅助页面失败: %s", err)

    _LOGGER.info(
        "lixiang_auto 配置成功: vin=%s 实时信号=%d 条",
        vin, len((coordinator.data or {}).get("vss") or {}),
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # ★ 巴法云桥接（选项填了 uid 才启动；须在平台实体创建之后）
    try:
        from .bemfa import async_setup_bemfa
        bridge = await async_setup_bemfa(hass, entry)
        if bridge is not None:
            hass.data[DOMAIN][entry.entry_id]["bemfa"] = bridge
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("巴法云桥接启动失败: %s", err)

    return True


SERVICE_WAKEUP = "wakeup"
SERVICE_REFRESH = "refresh"


def _async_register_services(hass: HomeAssistant) -> None:
    """注册集成服务（幂等，只在首次调用时注册）。"""
    if hass.services.has_service(DOMAIN, SERVICE_REFRESH):
        return

    async def _handle_refresh(call) -> None:
        """立即刷新所有（或指定 VIN 的）条目。"""
        target_vin = (call.data or {}).get("vin")
        for eid, d in (hass.data.get(DOMAIN) or {}).items():
            if not isinstance(d, dict):
                continue
            coord = d.get("coordinator")
            entry = hass.config_entries.async_get_entry(eid)
            if coord is None or entry is None:
                continue
            if target_vin and (entry.data.get(CONF_VIN) or "") != target_vin:
                continue
            await coord.async_request_refresh()
        _LOGGER.debug("已触发手动刷新 vin=%s", target_vin)

    async def _handle_wakeup(call) -> None:
        """唤醒车辆。"""
        target_vin = (call.data or {}).get("vin")
        for eid, d in (hass.data.get(DOMAIN) or {}).items():
            if not isinstance(d, dict):
                continue
            api = d.get("li_api")
            coord = d.get("coordinator")
            entry = hass.config_entries.async_get_entry(eid)
            if api is None or entry is None:
                continue
            if target_vin and (entry.data.get(CONF_VIN) or "") != target_vin:
                continue
            try:
                await hass.async_add_executor_job(api.wakeup)
                _LOGGER.info("已发送唤醒命令")
                if coord is not None:
                    await coord.async_request_refresh()
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("唤醒失败: %s", err)

    hass.services.async_register(DOMAIN, SERVICE_REFRESH, _handle_refresh)
    hass.services.async_register(DOMAIN, SERVICE_WAKEUP, _handle_wakeup)

    # ---- 车窗物理开/关（巴法/自动化用，不经过 HA cover 反向 UI）----
    if not hass.services.has_service(DOMAIN, "open_windows"):

        async def _handle_open_windows(call) -> None:
            pct = int((call.data or {}).get("percent", 99))
            await _foreach_window_entity(hass, "async_physical_open", pct)

        async def _handle_close_windows(call) -> None:
            await _foreach_window_entity(hass, "async_physical_close")

        hass.services.async_register(DOMAIN, "open_windows", _handle_open_windows)
        hass.services.async_register(DOMAIN, "close_windows", _handle_close_windows)

    _LOGGER.debug("已注册服务: %s.refresh / %s.wakeup / %s.open_windows / %s.close_windows",
                  DOMAIN, DOMAIN, DOMAIN, DOMAIN)


async def _foreach_window_entity(hass: HomeAssistant, method: str, *args) -> None:
    """对所有 lixiang_auto 车窗 cover 调用物理方法。"""
    try:
        from homeassistant.helpers import entity_registry as er
        reg = er.async_get(hass)
        comp = hass.data.get("entity_components", {}).get("cover")
        for ent in reg.entities.values():
            if ent.platform != DOMAIN or ent.domain != "cover":
                continue
            if "cover_window" not in (ent.unique_id or ""):
                continue
            obj = None
            if comp is not None and hasattr(comp, "get_entity"):
                obj = comp.get_entity(ent.entity_id)
            if obj is not None and hasattr(obj, method):
                fn = getattr(obj, method)
                await fn(*args)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("车窗物理动作 %s 失败: %s", method, err)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """卸载条目."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # ★ 清理通知轮询定时器（否则重载后 poller 叠加，重复请求）
        data = hass.data[DOMAIN].get(entry.entry_id) or {}
        poller = data.get("notify_poller")
        if poller is not None:
            try:
                poller.stop()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("停止通知轮询失败")
        bridge = data.get("bemfa")
        if bridge is not None:
            try:
                await bridge.async_stop()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("停止巴法云桥接失败")
        hass.data[DOMAIN].pop(entry.entry_id)
        # 最后一个条目卸载时移除服务
        if not hass.data.get(DOMAIN):
            for svc in (SERVICE_REFRESH, SERVICE_WAKEUP):
                if hass.services.has_service(DOMAIN, svc):
                    hass.services.async_remove(DOMAIN, svc)
            _LOGGER.debug("已移除服务")
    return unload_ok
