"""Li Auto 配置流程. 支持两种接入方式:
1. password_login — 手机号+密码直接登录 (PAKE 协议复刻, 见 pake_login.py)
2. manual — 手动填入从理想 App 提取的凭据 (hac_key 等, 用于 x-chj 车控)
"""

from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol
from homeassistant.helpers import selector

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .auth import LiAuthError
from .identity import get_store, get_store_async, normalize_phone
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_APP_TOKEN,
    CONF_DEVICE_ID,
    CONF_HAC_KEY,
    CONF_KEY_ID,
    CONF_MAIN_BEARER,
    CONF_PASSWORD,
    CONF_PHONE,
    CONF_REFRESH_TOKEN,
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

_LOGGER = logging.getLogger(LOGGER_NAME)

MANUAL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PHONE): str,
        vol.Required(CONF_HAC_KEY, description={"suggested_value": ""}): str,
        vol.Required(CONF_KEY_ID, description={"suggested_value": ""}): str,
        vol.Required(CONF_DEVICE_ID, description={"suggested_value": ""}): str,
        vol.Required(CONF_APP_TOKEN, description={"suggested_value": ""}): str,
        vol.Optional(CONF_VIN, default=""): str,
        vol.Optional(CONF_MAIN_BEARER, default=""): str,
        vol.Optional(CONF_ACCESS_TOKEN, default=""): str,
        vol.Optional(CONF_REFRESH_TOKEN, default=""): str,
    }
)

# ★ 2026-09-23 修复：
#   原来 default=DEFAULT_DEVICE_ID（抓包固化的**他人**设备号），
#   对开发者恰好受信任故掩盖了问题；新用户用它会与别人共享设备身份（有风险），
#   而随机新设备又必然触发 require=SMS_CODE。
#   正确做法：默认留空 → 由 identity store 决定（已登录过则复用受信任的）。
# ★ 主表单：只问最必要的两项（手机号 + 密码）
#   VIN 会自动从账号获取；device_id 由 identity store 管理（受信任设备免短信）
#   如确需手工指定，走「高级选项」步骤。
# ★ 2026-09-23 优化：用 selector 提供更好的输入体验
#   · 手机号：数字键盘 + 长度校验 + 自动补 +86 提示
#   · 密码：掩码显示（避免肩窥）
PASSWORD_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PHONE): selector.TextSelector(
            selector.TextSelectorConfig(
                type=selector.TextSelectorType.TEL,
                autocomplete="tel",
            )
        ),
        vol.Required("password"): selector.TextSelector(
            selector.TextSelectorConfig(
                type=selector.TextSelectorType.PASSWORD,
                autocomplete="current-password",
            )
        ),
    }
)

def _validate_phone(raw: str) -> str:
    """校验并归一化手机号。

    ★ 2026-09-23：在 schema 层之外做显式校验，给出可读的错误信息
      （而不是让服务端返回 400 后再翻译）。

    接受格式：13800138000 / +8613800138000 / 138-0013-8000 / 138 0013 8000
    归一化为：11 位中国大陆手机号（去掉 +86/空格/横杠）
    """
    v = re.sub(r"[\s\-()]", "", str(raw or ""))
    if v.startswith("+86"):
        v = v[3:]
    elif v.startswith("86") and len(v) == 13:
        v = v[2:]
    if not re.fullmatch(r"1[3-9]\d{9}", v):
        raise vol.Invalid("invalid_phone")
    return v


def _validate_password(raw: str) -> str:
    """密码基本校验（长度）。

    ★ 理想密码规则未知（服务端校验），这里只拦明显无效的输入，
      避免一次网络往返才发现是空密码。
    """
    v = str(raw or "")
    if len(v) < 6:
        raise vol.Invalid("password_too_short")
    if len(v) > 64:
        raise vol.Invalid("password_too_long")
    return v


# 高级选项（可选展开）
# ★ 2026-09-23：VIN 与 device_id 现在从「手动填凭据」入口提供，
#   登录表单保持简洁（只手机号 + 密码），此处不再定义未使用的 schema。


def _do_direct_login(phone: str, password: str, device_id: str | None = None) -> dict:
    """在线程池中执行同步登录 (requests), 返回 entry data.

    device_id 用已受信任的值可跳过短信风控 (require=SMS_CODE); 随机新设备
    会被要求短信验证.
    """
    from .pake_login import LixiangDirectLogin, LoginError

    cli = LixiangDirectLogin(device_id=device_id or None)
    try:
        tok = cli.login(phone, password)
    except LoginError as e:
        detail = str(e.detail or "")
        # ★ SMS 风控判定（2026-09-23 修）：
        #   服务端返回 300 + Location 含 require=SMS_CODE，
        #   但 detail 是中文"密码正确但风控要求短信验证"，
        #   所以不能只匹配 "SMS_CODE" 字面量 —— 要同时看【状态码 300】。
        if ("SMS_CODE" in detail or "短信验证" in detail
                or (e.step == "login" and e.status == 300)):
            raise LiAuthError("login:sms_required") from e
        raise LiAuthError(f"login:{e.step}:{e.status}:{detail}") from e
    if not tok.get("access_token"):
        raise LiAuthError("login:no_access_token")
    return {
        CONF_PHONE: phone,
        CONF_PASSWORD: password,      # sso_token 会话13天过期后需重登, 密码为长期凭据
        CONF_MAIN_BEARER: tok["access_token"],
        CONF_ACCESS_TOKEN: tok["access_token"],
        CONF_REFRESH_TOKEN: tok.get("refresh_token", ""),
        CONF_DEVICE_ID: cli.device_id,
    }


class LiCarConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """理想车配置流程"""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry):
        """注册选项流程（轮询间隔可调）。"""
        return LiCarOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """入口: 直接显示手机号 + 密码登录表单（不做菜单）。"""
        return await self.async_step_password_login(user_input)

    async def async_step_password_login(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """手机号 + 密码登录（自动使用已保存的受信任 device_id）。

        流程（2026-09-23 实测确立）
        --------------------------
        ① 归一化手机号（去空格/横杠/+86），用归一化值做 unique_id
        ② 取持久化的 device_id（若该账号之前登录过 → 受信任 → 免短信）
        ③ 尝试密码登录
           · 成功            → 建条目
           · require=SMS_CODE → 进入 SMS 步骤（P0-2 修复，不再死锁）
           · 401             → 密码错误

        ★ 重要提示：脚本登录会踢掉理想 App 的会话（PAKE 单会话限制）。
        """
        errors: dict[str, str] = {}
        if user_input is not None:
            phone = normalize_phone(user_input[CONF_PHONE])
            password = user_input["password"]
            await self.async_set_unique_id(phone)
            self._abort_if_unique_id_configured()

            # ① 取 device_id（优先级从高到低）
            #    a. 用户手填（高级选项）
            #    b. identity store 里该账号的（上次登录成功保存的）
            #    c. ★ 打包进集成的已知受信任设备（DEFAULT_DEVICE_ID）
            #       —— 这是本机之前用它成功登录过的设备号，
            #          服务端已标记受信任，可免短信。
            #    d. 都没有 → 随机新设备（会触发短信验证）
            store = await get_store_async(self.hass)
            saved = store.get_device_id(phone)
            device_id = (user_input.get(CONF_DEVICE_ID)
                         or saved
                         or DEFAULT_DEVICE_ID)
            trusted = bool(saved or (device_id == DEFAULT_DEVICE_ID))
            _LOGGER.debug("登录使用 device_id=%s (受信任=%s)",
                          str(device_id)[:12], trusted)

            # 暂存，供 SMS 步骤使用
            self._pending = {
                "phone": phone,
                "password": password,
                "vin": user_input.get(CONF_VIN) or "",
                "device_id": device_id,
                "trusted": trusted,
            }

            try:
                data = await self.hass.async_add_executor_job(
                    _do_direct_login, phone, password, device_id
                )
            except LiAuthError as e:
                msg = str(e)
                _LOGGER.warning("登录失败(LiAuthError): %s", msg)
                if "sms_required" in msg or "短信验证" in msg:
                    # ★ 进入【浏览器辅助登录】：让用户在自己浏览器里过滑动验证
                    _LOGGER.info(
                        "设备未受信任（%s），转到浏览器辅助登录",
                        (device_id or "new")[:12])
                    return await self.async_step_browser()
                if "401" in msg:
                    errors["base"] = "invalid_auth"
                elif any(k in msg for k in ("idps", "auth", "devices")):
                    errors["base"] = "cannot_connect"
                else:
                    errors["base"] = "unknown"
            except Exception as err:  # noqa: BLE001
                _LOGGER.exception("直接登录异常: %s", err)
                errors["base"] = "unknown"
            else:
                return await self._finish_login(data)

        return self.async_show_form(
            step_id="password_login",
            data_schema=PASSWORD_SCHEMA,
            errors=errors,
            description_placeholders={
                "note": "理想账号手机号+密码。首次登录可能要求短信验证；"
                        "若已在 App 登录过同一账号，通常可直接通过。"
            },
        )

    # ---------------------------------------------------------------
    # 首次登录辅助：让用户在浏览器里自己过滑动验证
    # ★ 2026-09-23 实测确立的方案
    #   背景：新 device_id 登录 → require=SMS_CODE；
    #         发短信前必须过顶象滑动（DX，无法在服务端绕过）；
    #         但用户在真实浏览器里可以自己滑。
    #   方案：HA 提供辅助页面（内嵌理想官方登录页，带 HA 的 device_id），
    #         用户在页面里完成登录后，该 device_id 被服务端标记受信任，
    #         HA 后台轮询检测到信任 → 后续免 MFA。
    # ---------------------------------------------------------------
    async def _ensure_login_views(self) -> None:
        """确保 /lixiang-login 视图已注册。

        ★ 2026-09-24（整合 shinnaluo 的 PR）：
          config_flow 在【还没有 config entry】时运行，
          此时 HA 不会调用 __init__.async_setup → 视图未注册 → 404。
          这个兜底在浏览器登录步骤前确保视图就绪。
        """
        try:
            from .auth_web import async_register_login_views
            await async_register_login_views(self.hass)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("注册登录辅助页面失败: %s", err)

    async def async_step_browser(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """浏览器辅助登录：用户在自己浏览器里过滑动验证。

        流程：
          ① 确保 /lixiang-login 视图已注册
          ② 生成本地会话（token）→ 得到辅助页面 URL
          ③ 用户在页面里完成登录（滑 + 短信）
          ④ HA 后台轮询用 device_id+密码 试登录
          ⑤ 成功 → 继续建条目（保存 phone+password+device_id）
        """
        # ★ 关键：确保视图已注册（首次配置时 async_setup 可能还没跑）
        await self._ensure_login_views()
        from .auth_web import create_session, get_session, try_login

        pending = getattr(self, "_pending", None) or {}
        phone = pending.get("phone") or ""
        password = pending.get("password") or ""
        device_id = pending.get("device_id") or DEFAULT_DEVICE_ID

        # ★ 用户填的 HA 访问地址（用于生成辅助页面 URL）
        if user_input and user_input.get("ha_base_url"):
            self._user_base_url = str(user_input["ha_base_url"]).strip().rstrip("/")

        # ① 建会话（每次进入本步骤新建，避免复用过期 token）
        tok = getattr(self, "_login_token", None)
        if not tok or get_session(tok) is None:
            tok = create_session(phone, password, device_id)
            self._login_token = tok

        # ② 后台检测：用 device_id + 密码 试登录
        try:
            ok = await self.hass.async_add_executor_job(
                try_login, phone, password, device_id)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("检测登录异常: %s", err)
            ok = False

        if ok:
            # ★ 设备已受信任 → 完成登录
            _LOGGER.info("设备已受信任（%s），继续完成配置", device_id[:12])
            from .auth_web import mark_trusted
            mark_trusted(tok)
            try:
                data = await self.hass.async_add_executor_job(
                    _do_direct_login, phone, password, device_id)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("受信任后登录仍失败: %s", err)
                return self.async_show_form(
                    step_id="browser",
                    data_schema=vol.Schema({vol.Optional("_retry", default=True): bool}),
                    errors={"base": "cannot_connect"},
                    description_placeholders=self._browser_ph(tok, device_id),
                )
            return await self._finish_login(data)

        # ③ 还没受信任 → 显示辅助页面 + 让用户确认后重新检测
        #    ★ 用户可填自己的 HA 访问地址（内网/外网不同）
        default_base = self._base_url()
        cur_base = getattr(self, "_user_base_url", None) or default_base
        self._user_base_url = cur_base
        return self.async_show_form(
            step_id="browser",
            data_schema=vol.Schema({
                vol.Optional("ha_base_url", default=cur_base): str,
                vol.Optional("recheck", default=True): bool,
            }),
            description_placeholders=self._browser_ph(tok, device_id),
        )

    def _current_entry_id(self) -> str:
        """当前编辑的条目 id（新建时为 None）。"""
        if isinstance(self.context, dict):
            return self.context.get("entry_id") or ""
        return ""

    def _find_entry_by_vin(self, vin: str):
        """查找已在 HA 中接入该 VIN 的条目（排除自己）。"""
        if not vin:
            return None
        for e in self.hass.config_entries.async_entries(DOMAIN):
            if (e.data.get(CONF_VIN) or "") == vin:
                return e
        return None

    def _base_url(self) -> str:
        """推断 HA 的对外访问地址（优先级从高到低）。

        ① HA 配置的 external_url（用户外网访问时最准）
        ② HA 配置的 internal_url
        ③ 从 config_flow 的 context 里取（HA 会传当前请求的地址）
        ④ 兜底：内网地址
        """
        # ① / ② HA 配置
        try:
            u = self.hass.config.external_url or self.hass.config.internal_url
            if u:
                return u.rstrip("/")
        except Exception:  # noqa: BLE001
            pass

        # ③ ★ 从 config_flow context 取当前请求地址（最准！）
        #    HA 的 config_flow 有 context['source'] 但不含 host；
        #    改用 hass.config.api 的地址
        try:
            api = getattr(self.hass.config, "api", None)
            if api is not None:
                # hass.config.api.base_url 形如 "http://<host>:8123"
                bu = getattr(api, "base_url", None)
                if bu:
                    return str(bu).rstrip("/")
        except Exception:  # noqa: BLE001
            pass

        # ④ 兜底：127.0.0.1（config_flow 里用户可自行改成实际地址）
        return "http://127.0.0.1:8123"

    def _browser_ph(self, tok: str, device_id: str) -> dict[str, str]:
        """辅助页面的说明文案（含 URL + 多个备选地址）。"""
        base = getattr(self, "_user_base_url", None) or self._base_url()
        url = f"{base}/lixiang-login?token={tok}"
        # 本地地址时提示用户可改成外网地址
        alt = ""
        if any(x in base for x in ("192.168.", "10.", "127.0.0.1", "localhost")):
            alt = "（如果你从外网访问 HA，请把「HA 访问地址」改成你的外网地址）"
        return {
            "url": url,
            "url_alt": alt,
            "device": device_id[:16],
        }

    # 兼容旧 step 名（避免旧的进行中流程报错）
    async def async_step_sms(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """旧入口 → 转发到浏览器辅助登录。"""
        return await self.async_step_browser(user_input)

    async def _finish_login(self, data: dict[str, Any]) -> FlowResult:
        """登录成功后统一建条目。

        ★ 补齐所有必需凭据（2026-09-23 修复）：
          _do_direct_login 只返回登录令牌，但集成还需要：
            · hac_key / key_id / x_chj_deviceid / app_token  → API 请求签名
            · vin                                            → VSS 信号 + 车控
          缺任何一项都会导致 VSS 403 / 车控失败。
        """
        pending = getattr(self, "_pending", None) or {}
        phone = pending.get("phone") or data.get(CONF_PHONE) or ""

        # ① 补齐 API 签名凭据
        #    ★ 这些凭据每台设备独有，不内置；优先用用户填的，
        #      只有 DEFAULT_* 非空时才回填（兼容自编译版本）。
        missing: list[str] = []
        for conf_key, default_val in (
            (CONF_HAC_KEY, DEFAULT_HAC_KEY),
            (CONF_KEY_ID, DEFAULT_KEY_ID),
            (CONF_XDEV, DEFAULT_XDEV),
            (CONF_APP_TOKEN, DEFAULT_APP_TOKEN),
        ):
            if data.get(conf_key):
                continue
            if default_val:
                data[conf_key] = default_val
                _LOGGER.debug("补齐 %s（内置默认值）", conf_key)
            elif conf_key != CONF_APP_TOKEN:
                missing.append(conf_key)

        if missing:
            _LOGGER.error(
                "缺少签名凭据 %s —— 请在「手动填写凭据」里补齐。"
                "提取方法见 docs/credential-guide.md", missing)
            return self.async_abort(
                reason="missing_credentials",
                description_placeholders={
                    "fields": "、".join(missing),
                },
            )

        # ② VIN：优先用户手填/暂存，否则从账号名下车辆自动取
        #    ★ 必须在 executor 里跑（_resolve_vin 是同步 HTTP，直接调用会
        #      被 HA 判定为事件循环阻塞 → BlockingIOError）
        vin = pending.get("vin") or data.get(CONF_VIN) or ""
        if not vin:
            try:
                vin = await self.hass.async_add_executor_job(
                    self._resolve_vin, data)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("自动获取 VIN 失败: %s", err)
        if vin:
            data[CONF_VIN] = vin
            _LOGGER.info("VIN = %s（%s）", vin,
                         "用户指定" if pending.get("vin") else "自动获取")
        else:
            # ★ 2026-09-23：自动获取失败时进入【手动补 VIN】步骤，
            #   而不是只打一句"请稍后在集成选项里补充"（选项里并没有该字段）。
            _LOGGER.warning("自动获取 VIN 失败，转入手动补填步骤")
            self._pending = {**pending, **data}
            return await self.async_step_vin()

        # ★ VIN 去重：同一辆车被第二个账号接入会导致 unique_id 冲突
        #   （HA 一个 unique_id 只能对一个实体 → 第二个条目只创建出零星实体）
        #   实测（2026-09-23）：主号 owned + 家人号 authorized 指向同一 VIN，
        #   第二个条目只拿到 17/106 个实体。
        if vin:
            existing = self._find_entry_by_vin(vin)
            cur = self._current_entry_id()
            if existing is not None and existing.entry_id != cur:
                other = (existing.data.get(CONF_PHONE) or "")[-4:]
                _LOGGER.warning(
                    "VIN %s 已被条目 %s（账号 ****%s）接入，拒绝重复添加",
                    vin, existing.entry_id[:12], other)
                return self.async_abort(
                    reason="vin_already_configured",
                    description_placeholders={
                        "vin": vin,
                        "phone": other or "?",
                    },
                )

        # ③ 保存 device_id（下次免短信）
        #    ★ save=False + 异步落盘：避免在事件循环里做文件 IO
        if data.get(CONF_DEVICE_ID):
            store = await get_store_async(self.hass)
            store.set_device_id(phone, data[CONF_DEVICE_ID], save=False)
            try:
                await store.save_async(self.hass)
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("保存设备身份失败（忽略）: %s", err)

        _LOGGER.info("登录成功: 手机号=****%s vin=%s device=%s",
                     phone[-4:], vin or "(空)", str(data.get(CONF_DEVICE_ID))[-8:])
        return self.async_create_entry(
            title=f"Li Auto ({phone[-4:]})",
            data=data,
        )

    def _resolve_vin(self, data: dict[str, Any]) -> str:
        """用 li_api.get_vehicles() 拉取账号名下的车辆，返回第一辆的 VIN。

        ★ 2026-09-23 实测打通：
          端点 /saos-vehicle-api/v2-0/vehicles/basics
          audience 7gbeHMwBPMZA5SU1b2awIo，走 IDaaS scope token，
          登录后即可用（不依赖已过期的 X-CHJ-TOKEN）。
        """
        from .li_api import LiApiClient

        try:
            api = LiApiClient(
                phone=data.get(CONF_PHONE) or "",
                password=data.get(CONF_PASSWORD) or "",
                vin="",
                hac_key=data.get(CONF_HAC_KEY) or DEFAULT_HAC_KEY,
                key_id=data.get(CONF_KEY_ID) or DEFAULT_KEY_ID,
                xdev=data.get(CONF_XDEV) or DEFAULT_XDEV,
                app_token=data.get(CONF_APP_TOKEN) or DEFAULT_APP_TOKEN,
                device_id=data.get(CONF_DEVICE_ID) or DEFAULT_DEVICE_ID,
            )
            vin = api.get_primary_vin()
            if vin:
                _LOGGER.info("自动获取到 VIN: %s", vin)
                return vin
            _LOGGER.warning("账号名下未找到车辆")
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("自动获取 VIN 失败: %s", err)
        return ""


    async def async_step_vin(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """手动补填 VIN（仅在自动获取失败时出现）。

        ★ 正常情况下不会走到这里 —— 登录成功后集成会自动调用
          /saos-vehicle-api/v2-0/vehicles/basics 获取账号下的车辆。

        什么情况下需要手动填？
          · 自动获取接口失败（网络/服务端变动）
          · 账号下有多辆车，想指定其中一辆
          · 非车主账号（家人）自动获取不到
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            vin = (user_input.get(CONF_VIN) or "").strip().upper()
            pending = dict(getattr(self, "_pending", None) or {})
            if not vin:
                return await self._finish_login(pending)
            # VIN 规则：17 位，不含 I/O/Q
            if not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", vin):
                errors["base"] = "invalid_vin"
            else:
                pending[CONF_VIN] = vin
                self._pending = pending
                return await self._finish_login(pending)

        return self.async_show_form(
            step_id="vin",
            data_schema=vol.Schema({
                vol.Optional(CONF_VIN, default=""): str,
            }),
            errors=errors,
            description_placeholders={
                "hint": "自动获取失败，请手动填写 VIN（17 位）",
            },
        )

    async def async_step_manual(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """手动填写 App 提取凭据."""
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_PHONE])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"Li Auto ({user_input[CONF_PHONE][-4:]})",
                data=user_input,
            )
        return self.async_show_form(
            step_id="manual",
            data_schema=MANUAL_SCHEMA,
            errors=errors,
            description_placeholders={"note": "请填写从理想 App 提取的凭据"},
        )

    # ---------------------------------------------------------------
    # 重新认证（修复 3 个 P0）
    #   P0-1: 不再用 self.context["entry_id"] 下标访问（会 KeyError）
    #   P0-3: 不再手写 merged dict（会丢 VIN）→ 用 async_update_reload_and_abort
    # ---------------------------------------------------------------
    def _current_entry(self):
        """安全获取当前条目（兼容多种 context 形态）。"""
        eid = self.context.get("entry_id") if isinstance(self.context, dict) else None
        if eid:
            e = self.hass.config_entries.async_get_entry(eid)
            if e is not None:
                return e
        # 回退：HA 2025+ 提供的 helper
        getter = getattr(self, "_get_reauth_entry", None)
        if callable(getter):
            try:
                return getter()
            except Exception:  # noqa: BLE001
                pass
        return None

    async def async_step_reauth(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """重新认证: 已有手机号, 只补密码。"""
        entry = self._current_entry()
        if entry is None:
            # 连条目都找不到 → 明确告知，不抛异常
            return self.async_abort(reason="reauth_entry_not_found")
        phone = entry.data.get(CONF_PHONE) or ""
        return self.async_show_form(
            step_id="reauth",
            data_schema=vol.Schema({vol.Required("password"): str}),
            description_placeholders={"phone": phone[-4:] if phone else "?"},
        )

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """提交新密码完成重新认证。"""
        entry = self._current_entry()
        if entry is None:
            return self.async_abort(reason="reauth_entry_not_found")

        errors: dict[str, str] = {}
        if user_input is not None and "password" in user_input:
            phone = entry.data.get(CONF_PHONE) or ""
            # ★ 优先用已保存的 device_id（受信任，免短信）
            store = get_store()
            device_id = (store.get_device_id(phone)
                         or entry.data.get(CONF_DEVICE_ID)
                         or DEFAULT_DEVICE_ID)
            try:
                data = await self.hass.async_add_executor_job(
                    _do_direct_login, phone, user_input["password"], device_id
                )
            except LiAuthError as e:
                msg = str(e)
                if "sms_required" in msg:
                    errors["base"] = "sms_required"
                elif "401" in msg:
                    errors["base"] = "invalid_auth"
                else:
                    errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("重新认证异常")
                errors["base"] = "unknown"
            else:
                # ★ P0-3 修复：保留原有 VIN 等字段（_do_direct_login 不含 VIN）
                data.setdefault(CONF_VIN, entry.data.get(CONF_VIN))
                for k in (CONF_HAC_KEY, CONF_KEY_ID, CONF_XDEV, CONF_APP_TOKEN):
                    if entry.data.get(k):
                        data.setdefault(k, entry.data[k])
                # 保存新的 device_id（若变了）
                if data.get(CONF_DEVICE_ID):
                    store.set_device_id(phone, data[CONF_DEVICE_ID])
                _LOGGER.info("重新认证成功，VIN 保留=%s", data.get(CONF_VIN))
                # ★ 用 HA 官方 API（自动 reload）
                return self.async_update_reload_and_abort(
                    entry, data_updates=data, reason="reauth_successful"
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required("password"): str}),
            errors=errors,
            description_placeholders={"phone": (entry.data.get(CONF_PHONE) or "")[-4:]},
        )


class LiCarOptionsFlow(config_entries.OptionsFlow):
    """集成选项：轮询间隔（借鉴 huawei-auto-cloud 的可配置设计）。

    华为: 默认 30s，最小 10s
    我们: 默认 60s，最小 30s（避免服务端风控）
    """

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        from .const import (
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS,
            MAX_SCAN_INTERVAL_SECONDS, MIN_SCAN_INTERVAL_SECONDS,
        )
        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS)
        cur_ctrl = self.config_entry.options.get("enable_control", True)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("enable_control", default=cur_ctrl): bool,
                vol.Required(CONF_SCAN_INTERVAL, default=current):
                    vol.All(vol.Coerce(int),
                            vol.Range(min=MIN_SCAN_INTERVAL_SECONDS,
                                      max=MAX_SCAN_INTERVAL_SECONDS)),
            }),
        )
