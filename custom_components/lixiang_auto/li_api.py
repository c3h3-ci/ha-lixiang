"""理想汽车同步 API 客户端 (认证链端到端验证版, 2026-09-06).

认证链 (全部经真实请求验证, 见 docs/实时状态打通_20260906.md):
  1. PAKE 密码登录 (pake_login) → 会话 sso_token cookie (13天) + 主Bearer + refresh_token
  2. 会话 cookie POST /api/auth (response_type=token) → 各服务 scope token (15分钟)
     注意: 裸 Bearer 换不了 scope token (login_required), 必须带登录会话 cookie;
     refresh_token 续期不会重新种 cookie, 故密码是唯一的长期免维护凭据。
  3. x-chj 签名请求 (hac_key/KEY_ID/X-CHJ-Deviceid 用 iPad 捕获的一套) + scope Bearer
     → /ssp-cloud-vss-service/mobile/vss/get-batch 读实时信号

同步 requests 实现, HA 侧经 hass.async_add_executor_job 调用。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


from .policy import (
    POLICY_COMMAND,
    POLICY_RESULT,
    POLICY_VSS,
    TokenExpired,
    is_token_expired,
    run_with_retry,
)
from .pake_login import (
    APP_VERSION as LOGIN_APP_VERSION,
    BASE_ID,
    CLIENT_ID,
    LixiangDirectLogin,
    LoginError,
    REDIRECT_URI,
    SDK_VERSION,
)

_LOGGER = logging.getLogger(__name__)

API_APP = "https://api-app.lixiang.com"
SIGN_APP_VERSION = "8.25.4-10463"
AUD_VSS = "1j0vgTqagJUHuT6nLmbTGx"
AUD_SERVICE_CARD = "26FehzsHlrllCSaqI9bFYG"
SCOPE_VSS = "vss:get-batch"
SCOPE_CARD = "login offline_access"

# ---------- 车控双 token (2026-09-22 实测打通) ----------
# cmd/send 需要【两个】token, 缺一不可:
#   Authorization: Bearer <MESH>   认证     (aud=1j0vgTqagJUHuT6nLmbTGx, ~15min)
#   body.token     = <VAT>         业务授权 (aud=5Tc7yDrnMzALwc9Rytl9sp, JWT ~20h)
# 两者都用登录会话 POST https://id.lixiang.com/api/auth (response_type=token) 换取。
AUD_MESH = "1j0vgTqagJUHuT6nLmbTGx"
SCOPE_MESH = "remote-wakeup:wakeup veh-ctrl:cmd-send veh-ctrl:cmd-result-get"
AUD_VAT = "5Tc7yDrnMzALwc9Rytl9sp"

# VAT scope 必须以 remoteVeh<Cmd>:<VIN> 形式逐条列出 (14 条)
VAT_SCOPE_COMMANDS = (
    "ACSmartControl", "FrgControl", "Auth", "LockControl", "PlgControl",
    "Search", "WdwControl", "ACFirstControl", "ADCtrl", "ADInit",
    "fTkC", "rmCtrl", "cpCtrl", "ssCtrl",
)

# 车控端点
# ---------- 服务器通知（MMS，2026-09-23 实测打通）----------
# 端点: GET /mms-api/v1-0/message?appId=<>&channelType=1&pageSize=&pageNumber=
# token: audience=5a1X5rZcWZNeEOYlyRigUs, scope=ALL
# 实测: channelType=1 → 通知列表（2165 条）；2/4 → 其他类别
AUD_MMS = "5a1X5rZcWZNeEOYlyRigUs"
SCOPE_MMS = "ALL"
MMS_APP_ID = "chj_app_m01"
EP_MMS_MESSAGE = "/mms-api/v1-0/message"

# ---------- 车辆列表（★ 2026-09-23 实测打通）----------
AUD_SAOS_VEHICLE = "7gbeHMwBPMZA5SU1b2awIo"
SCOPE_SAOS_VEHICLE = "login"
EP_SAOS_VEHICLES = (
    "/saos-vehicle-api/v2-0/vehicles/basics"
    "?types=owned,transferring,authorized,inviting"
    "&roleIds=1,10,11,13,15&vehicleInfo=true"
)
EP_MMS_NOTIFICATION = "/mms-api/v1-0/notification"
EP_MMS_DEVICE = "/mms-api/v1-0/device"
CHANNEL_NOTICE = 1          # 通知类别
CHANNEL_OTHER_2 = 2
CHANNEL_OTHER_4 = 4

EP_CMD_SEND = "/ssp-vehicle-control-service/ssp-vehicle-control/cmd/send"
EP_CMD_RESULT = "/ssp-vehicle-control-service/ssp-vehicle-control/cmd-result"
EP_WAKEUP = "/iot-connect-manager-service/v2/wakeup"
CTRL_DOMAIN = "xcu"

# cmd-result pushState 语义
PUSH_STATE_SUCCESS = 5     # 执行成功
PUSH_STATE_FAILED = 7      # 执行失败

# ★ resultCode 的"成功"集合 (2026-09-23 从 XHttpOpenAcControl.isSuccessResultCode 逆向)
#   "-15" = 倒计时完成 (座椅加热/空调倒计时到期, App 视为成功)
#   "-8"  = 同类特判, 也视为成功
#   源码: if ("-15".equals(code)) return true; if ("-8".equals(code)) return true;
SUCCESS_RESULT_CODES = {0, "0", -15, "-15", -8, "-8"}

# 命令有效期: 源码真实值 (const/16 0x1e = 30 秒, const-wide/16 0x7530 = 30000ms)。
# 服务端只校验 jobExpire >= 1; 填 1 也能成功, 用 30 更贴近真机、更保险。
CMD_EXPIRE = 30
CMD_EXPIRE_MS = 30_000

# ★ 长短命令分级 (2026-09-23 实测):
#   短命令 (锁/窗/寻车/启动)     -> jobExpire=30 足够
#   长命令 (座椅加热/通风/空调)  -> jobExpire>=900 (实测 30 会超时 ps=7 rc=空)
#   App 源码里开空调也有 1860 的分支 (getVehPowerMode()!=2)
LONG_RUNNING_CMD_KEYS = {
    "remoteVehACSmartControl",   # 空调/座椅/方向盘加热/除霜
}
LONG_CMD_EXPIRE = 900
LONG_CMD_EXPIRE_MS = 900_000

# 空请求体 Content-MD5 常量 (base64(MD5("")))
EMPTY_MD5 = "1B2M2Y8AsgTpgAmY7PhCfg=="


def vat_scope(vin: str) -> str:
    """构造 VAT scope: remoteVeh<Cmd>:<VIN> × 14."""
    return " ".join(f"remoteVeh{c}:{vin}" for c in VAT_SCOPE_COMMANDS)


class LiApiError(RuntimeError):
    """理想 API 认证/请求错误"""


class LiCommandError(LiApiError):
    """车控命令执行失败 (含服务端 resultCode / pushState)."""

    def __init__(self, message: str, *, request_id: str = "",
                 result_code: int | None = None, push_state: int | None = None) -> None:
        super().__init__(message)
        self.request_id = request_id
        self.result_code = result_code
        self.push_state = push_state


class _TokenExpired(TokenExpired):
    """VSS token 失效（401），触发上层清除缓存并重试。

    ★ 2026-09-23：改为继承 policy.TokenExpired（结构化异常）。
      名字保留，避免改动所有调用点。
    """


class LiApiClient:
    """同步版理想客户端: 管理登录会话与 scope token, 提供实时信号读取."""

    def __init__(
        self,
        phone: str,
        password: str,
        vin: str,
        hac_key: str,
        key_id: str,
        xdev: str,
        app_token: str,
        device_id: str | None = None,
        refresh_token: str = "",
    ) -> None:
        self._phone = str(phone) if phone is not None else ""
        self._password = str(password) if password is not None else ""
        self._vin = str(vin) if vin is not None else ""
        # ★ 2026-09-24 修复（严重 bug）：
        #   secrets 模块的 _LazySecret 是 str 子类，构造时内容为空，
        #   真实值靠 __str__() 延迟求值。
        #   如果直接存对象（self._key_id = key_id），
        #   后续用作 HTTP 头时可能拿到【空字符串】：
        #     requests 对 str 子类可能不调用 __str__()
        #   → 服务端报「缺少必要的请求参数: X-CHJ-Key,X-CHJ-Deviceid」
        #
        #   ★ 必须显式 str() 强制求值。
        self._hac = _hac_key_bytes(hac_key)
        self._key_id = str(key_id) if key_id is not None else ""
        self._xdev = str(xdev) if xdev is not None else ""   # x-chj 签名身份 (与 hac_key 绑定的设备)
        self._app_token = str(app_token) if app_token is not None else ""
        self._refresh_token = str(refresh_token) if refresh_token is not None else ""
        self._cli: LixiangDirectLogin | None = None
        if device_id:
            self._device_id = device_id
        else:
            import secrets
            self._device_id = secrets.token_hex(16)
        self._tokens: dict[str, tuple[str, float]] = {}   # name -> (token, expiry_monotonic)

    # ---------- 登录会话 ----------

    def _login(self) -> None:
        """PAKE 密码登录, 建立 sso_token 会话 (cookie 13 天有效)."""
        cli = LixiangDirectLogin(device_id=self._device_id, debug=False)
        tok = cli.login(self._phone, self._password)
        if not tok.get("access_token"):
            raise LiApiError("登录成功但无 access_token")
        self._cli = cli
        self._refresh_token = tok.get("refresh_token", "") or self._refresh_token
        self._tokens.clear()
        _LOGGER.info("li_api PAKE 登录成功 (device_id=%s)", self._device_id)

    def _ensure_session(self) -> LixiangDirectLogin:
        """保证登录会话可用 (尝试换取 token 探测会话有效性)."""
        if self._cli is not None:
            return self._cli
        self._login()
        return self._cli

    def _exchange(self, scope: str, audience: str) -> str:
        """用登录会话 cookie 换 scope token (response_type=token)."""
        cli = self._ensure_session()
        r = cli._sess.post(
            f"{BASE_ID}/api/auth",
            data={
                "prompt": "none", "offline_access": "true",
                "redirect_uri": REDIRECT_URI, "scope": scope,
                "response_type": "token", "device_id": self._device_id,
                "client_id": CLIENT_ID, "audience": audience,
            },
            headers={
                "idaas-data": (
                    f"model_name=OpenHarmony;device_id={self._device_id};"
                    f"app_version={LOGIN_APP_VERSION};client_id={CLIENT_ID};"
                    f"sdk_version={SDK_VERSION};timestamp={int(time.time() * 1000)}"
                ),
                "origin": "https://account.lixiang.com",
                "referer": "https://account.lixiang.com/",
                "x-requested-with": "XMLHttpRequest",
                "User-Agent": f"m01/{LOGIN_APP_VERSION}",
                "content-type": "application/x-www-form-urlencoded",
            },
            allow_redirects=False, timeout=20,
        )
        frag = urllib.parse.urlparse(r.headers.get("location", "")).fragment
        tok = dict(urllib.parse.parse_qsl(frag)).get("access_token", "")
        if not tok:
            raise LiApiError(f"换 token 失败 ({scope}): HTTP {r.status_code} {r.text[:120]}")
        return tok

    def _get_scoped(self, name: str, scope: str, audience: str, ttl: int = 780) -> str:
        """scope token 缓存获取 (默认提前 2 分钟过期; 失效自动重登一次)."""
        ent = self._tokens.get(name)
        if ent and ent[1] > time.monotonic():
            return ent[0]
        try:
            tok = self._exchange(scope, audience)
        except LiApiError:
            if self._password:
                _LOGGER.info("会话失效, 重新登录 (%s)", name)
                self._cli = None
                self._login()
                tok = self._exchange(scope, audience)
            else:
                raise
        self._tokens[name] = (tok, time.monotonic() + ttl)
        return tok

    # ---------- 车控双 token ----------

    def _get_mesh_token(self) -> str:
        """MESH token: cmd/send 的 Authorization 头 (~15min)."""
        return self._get_scoped("mesh", SCOPE_MESH, AUD_MESH, ttl=780)

    def _get_vat_token(self) -> str:
        """VAT token: cmd/send 的 body.token 字段 (JWT, ~20h)。

        scope 必须按 remoteVeh<Cmd>:<VIN> 逐条列出。
        """
        return self._get_scoped("vat", vat_scope(self._vin), AUD_VAT, ttl=19 * 3600)

    def invalidate_tokens(self) -> None:
        """清空 token 缓存 (强制下次重新换取)."""
        self._tokens.clear()

    # ---------- x-chj 签名请求 ----------

    def _signed_call(self, method: str, path: str, body: str, bearer: str) -> dict:
        ts = str(int(time.time() * 1000))
        nonce = str(uuid.uuid4())
        if body:
            md5 = base64.b64encode(hashlib.md5(body.encode()).digest()).decode()
        else:
            md5 = EMPTY_MD5
        data = "\n".join([
            "prod", SIGN_APP_VERSION, self._key_id, self._xdev, method, "*/*",
            "zh-Hans-CN", md5, "application/json", ts, nonce,
        ]) + "\n"
        sig = base64.b64encode(hmac.new(self._hac, data.encode(), hashlib.sha256).digest()).decode()
        headers = {
            "X-CHJ-Env": "prod", "X-CHJ-APP-Version": SIGN_APP_VERSION,
            "X-CHJ-Key": self._key_id, "X-CHJ-Deviceid": self._xdev,
            "X-CHJ-Timestamp": ts, "X-CHJ-Nonce": nonce, "X-CHJ-Sign": sig,
            "Content-MD5": md5, "Content-Type": "application/json",
            "Content-Language": "zh-Hans-CN", "Accept": "*/*",
            "X-CHJ-Version": SIGN_APP_VERSION, "X-CHJ-DeviceType": "2",
            "X-CHJ-ModelName": "IOS", "X-CHJ-Tag": "1",
            "X-CHJ-TOKEN": self._app_token, "X-CHJ-VIN": self._vin,
            "Authorization": f"Bearer {bearer}",
            "User-Agent": f"m01/{SIGN_APP_VERSION} (iPad; iOS 16.7.12; Scale/2.00)",
        }
        req = urllib.request.Request(
            API_APP + path, method=method,
            headers=headers, data=body.encode() if body else None)
        try:
            with urllib.request.urlopen(
                    req, context=_ssl_ctx(), timeout=20) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            raise LiApiError(f"{method} {path}: HTTP {e.code} {e.read().decode()[:200]}")

    # ---------- 业务接口 ----------

    def _invalidate_token(self, name: str) -> None:
        """清除某个 scope token 的缓存（401 时调用，强制下次重新换取）。"""
        self._tokens.pop(name, None)

    def get_vss_state(self, paths: list[str]) -> dict:
        """读取实时 VSS 信号. 返回 {path: {"value":..,"ts":..}}; 未返回的路径不含在内.

        ★ 关键: 服务端对【任一无效 path】返回 400 (invalid_path), 会导致整批失败.
        因此采用: 分批 + 失败降级(逐个重试) + 失败批次二次拆分.
        """
        tok = self._get_scoped("vss", SCOPE_VSS, AUD_VSS)
        out: dict = {}
        B = 50

        def _one_batch(batch: list[str]) -> bool:
            """返回 True 表示成功(无 400)."""
            body = json.dumps({"vin": self._vin, "paths": batch})
            try:
                resp = self._signed_call(
                    "POST", "/ssp-cloud-vss-service/mobile/vss/get-batch", body, tok)
            except LiApiError as err:
                # 400 invalid_path: 整批失败
                if "400" in str(err) or "invalid_path" in str(err):
                    return False
                # ★ 401: token 失效 —— 抛结构化异常，由外层重试
                #   （用 is_token_expired 兜住「结构化」和「旧字符串」两种）
                if is_token_expired(err):
                    raise _TokenExpired(str(err)) from err
                raise
            for it in resp.get("items") or []:
                dp = it.get("dp") or {}
                out[it["path"]] = {"value": dp.get("value"),
                                   "ts": (dp.get("tsFormat") or "")[:19]}
            return True

        def _fetch(batch: list[str], depth: int = 0) -> None:
            """容错抓取: 失败则二分, 直到定位到坏 path 并跳过."""
            if not batch:
                return
            if _one_batch(batch):
                return
            if len(batch) == 1:
                _LOGGER.debug("VSS path 无效, 跳过: %s", batch[0])
                return
            if depth >= 4:
                _LOGGER.warning("VSS 批次(%d)反复失败, 跳过", len(batch))
                return
            mid = len(batch) // 2
            _fetch(batch[:mid], depth + 1)
            _fetch(batch[mid:], depth + 1)
            return

        for i in range(0, len(paths), B):
            _fetch(paths[i:i + B])
        return out

    def poll(self, paths: list[str]) -> dict:
        """coordinator 周期调用: 返回 {"vss": {path: value}, "polled_at": ...}.

        ★ 401 自动重试 (2026-09-23): VSS token 缓存可能因服务端提前失效而 401，
          此时清缓存重新换取 token 并重试一次。
        """
        # ★ 2026-09-23：重试逻辑收敛到 policy.run_with_retry（原先手写 try/except）
        state = run_with_retry(
            lambda: self.get_vss_state(paths),
            on_token_expired=self.invalidate_tokens,
            policy=POLICY_VSS,
        )
        return {"vss": state, "polled_at": time.strftime("%F %T")}

    # ---------- 车控 (2026-09-22 实测打通, pushState=5 / resultCode=0) ----------
    #
    # 完整流程:
    #   ① POST /iot-connect-manager-service/v2/wakeup   远程唤醒车机
    #   ② POST /ssp-vehicle-control-service/.../cmd/send → {"requestId": "..."}
    #   ③ GET  /ssp-vehicle-control-service/.../cmd-result/{requestId}
    #        轮询直到 pushState==5(成功) / ==7(失败)
    #
    # ⚠️ 车控会真实作用于车辆。

    # ---------- 服务器通知（MMS）----------

    def _get_mms_token(self) -> str:
        """MMS token（通知 API 用）。"""
        return self._get_scoped("mms", SCOPE_MMS, AUD_MMS, ttl=780)

    def get_notifications(
        self,
        page: int = 1,
        page_size: int = 20,
        channel_type: int = CHANNEL_NOTICE,
    ) -> list[dict]:
        """拉取服务器通知列表。

        返回通知 dict 列錨，每条含:
            requestId, messageId, title, summary, category,
            tag[], status(0=未读), sendOn(ms), action, pushId, sendBy

        ★ category='vehicle' 为车辆通知（充电完成/电量不足告警等）

        来源: /mms-api/v1-0/message  (2026-09-23 实测: 2165 条)
        """
        tok = self._get_mms_token()
        q = (f"?appId={MMS_APP_ID}&channelType={channel_type}"
             f"&pageSize={page_size}&pageNumber={page}")
        r = self._signed_call("GET", EP_MMS_MESSAGE + q, "", tok)
        data = r.get("data") or {}
        return data.get("elements") or []

    def get_unread_vehicle_notifications(self) -> list[dict]:
        """只看【未读的车辆通知】（用于告警联动）。"""
        out = []
        for m in self.get_notifications(page=1, page_size=20):
            if m.get("status") == 0 and m.get("category") == "vehicle":
                out.append(m)
        return out

    def get_notification_settings(self, user_id: str = "me") -> dict:
        """读取通知设置（含车辆通知开关）。

        返回 {"attention":1,"comment":1,"favour":1,"notice":1,"vehicle":1}
        """
        tok = self._get_mms_token()
        r = self._signed_call(
            "GET", f"{EP_MMS_NOTIFICATION}/{user_id}?appId={MMS_APP_ID}", "", tok)
        return ((r.get("data") or {}).get("categoryStatus") or {})

    def register_push_device(self, push_id: str = "", platform: int = 2) -> dict:
        """注册推送设备（订阅）。push_id 为空则用 deviceId 占位。"""
        tok = self._get_mms_token()
        body = {
            "appId": MMS_APP_ID,
            "deviceId": self._xdev,
            "pushId": push_id or (self._xdev + "_ha"),
            "platform": platform,
            "status": "1",
        }
        return self._signed_call(
            "POST", EP_MMS_DEVICE,
            json.dumps(body, separators=(",", ":")), tok)

    def get_vehicles(self) -> list[dict]:
        """获取账号名下的车辆列表（★ 2026-09-23 实测打通）。

        端点: GET /saos-vehicle-api/v2-0/vehicles/basics
              ?types=owned,transferring,authorized,inviting
              &roleIds=1,10,11,13,15&vehicleInfo=true
        audience: 7gbeHMwBPMZA5SU1b2awIo, scope: login

        返回每辆车的:
            vin, modelName, seriesName, seriesId, modelId,
            vehicleType(owned/authorized/...), vehicleRoleId,
            vehicleInfo{...}

        ★ 为什么不用 /aisp-account-api/v1-0/vehicles？
          那个接口依赖 X-CHJ-TOKEN（App 的短效 token，已过期 → 240225）。
          本接口走 IDaaS scope token，登录后即可用。
        """
        tok = self._get_scoped("saos_vehicle", SCOPE_SAOS_VEHICLE,
                               AUD_SAOS_VEHICLE, ttl=780)
        r = self._signed_call("GET", EP_SAOS_VEHICLES, "", tok)
        data = r.get("data")
        if isinstance(data, list):
            return data
        if isinstance(r, list):
            return r
        return []

    def get_primary_vin(self) -> str:
        """取账号名下第一辆车的 VIN（车主优先）。"""
        cars = self.get_vehicles()
        if not cars:
            return ""
        # 车主（owned）优先
        for c in cars:
            if str(c.get("vehicleType") or "") == "owned":
                vin = str(c.get("vin") or "")
                if vin:
                    return vin
        return str(cars[0].get("vin") or "")

    def wakeup(self) -> dict:
        """远程唤醒车机 (发命令前调用, 提高下发成功率)."""
        return self._signed_call(
            "POST", EP_WAKEUP,
            json.dumps({"source": "0x3B", "bizId": "0"}, separators=(",", ":")),
            self._get_mesh_token(),
        )

    def send_command_raw(self, command_key: str, command_data: dict | None = None) -> dict:
        """仅下发命令, 不轮询结果. 返回 cmd/send 的原始响应.

        结构 (实测 pushState=5 / resultCode=0):
          {"vin":..,"cmdKey":..,"cmdData":{..},"domain":"xcu",
           "jobExpire":30,"expire":30,"expireAt":now+30000,"token":"<VAT>"}
        请求头 Authorization: Bearer <MESH>。
        ★ 易错点:
          - jobExpire 必须 >= 1, 否则 400 "参数错误[jobExpire必须大于等于1]"
            (服务端只校验下界; 填 1 可成功, 但采用源码真实值 30 更保险)
          - token 必须是 VAT(token), 不是 MESH / "0" / 空 (旧代码填 "0" 会 2009)
        """
        now_ms = int(time.time() * 1000)
        # ★ 长命令 (座椅加热/通风/空调) 需更长有效期:
        #   实测 remoteVehACSmartControl 用 jobExpire=30 会 ps=7 rc=空;
        #   改 900 后 [4s] ps=5 rc=0 成功。
        if command_key in LONG_RUNNING_CMD_KEYS:
            je, je_ms = LONG_CMD_EXPIRE, LONG_CMD_EXPIRE_MS
        else:
            je, je_ms = CMD_EXPIRE, CMD_EXPIRE_MS
        body = {
            "vin": self._vin,
            "cmdKey": command_key,
            "cmdData": command_data if command_data is not None else {},
            "domain": CTRL_DOMAIN,
            "jobExpire": je,
            "expire": je,
            "expireAt": now_ms + je_ms,
            "token": self._get_vat_token(),
        }
        # ★ 401 自动重试（2026-09-23）：
        #   MESH / VAT token 缓存可能被服务端提前失效，
        #   旧行为是「点两次才生效」；现在捕获 401 → 清缓存 → 重试一次。
        def _do() -> dict:
            return self._signed_call(
                "POST", EP_CMD_SEND,
                json.dumps(body, separators=(",", ":")),
                self._get_mesh_token(),
            )

        def _refresh_body() -> None:
            """重试前重算 expireAt 与 VAT token（时间已推进）。"""
            body["expireAt"] = int(time.time() * 1000) + je_ms
            body["token"] = self._get_vat_token()

        # ★ 2026-09-23：重试逻辑收敛到 policy.run_with_retry
        return run_with_retry(
            _do,
            on_token_expired=self.invalidate_tokens,
            before_retry=_refresh_body,
            policy=POLICY_COMMAND,
        )

    def get_command_result(self, request_id: str) -> dict:
        """查询单条命令的执行结果（401 自动重试）。"""
        # ★ 2026-09-23：重试逻辑收敛到 policy.run_with_retry
        return run_with_retry(
            lambda: self._signed_call(
                "GET", f"{EP_CMD_RESULT}/{request_id}", "", self._get_mesh_token()),
            on_token_expired=self.invalidate_tokens,
            policy=POLICY_RESULT,
        )

    def send_command(
        self,
        command_key: str,
        command_data: dict | None = None,
        *,
        wake: bool = True,
        poll: bool = True,
        timeout: float = 60.0,
        poll_interval: float = 2.0,
    ) -> dict:
        """下发车控命令并等待执行结果.

        返回 {"requestId","pushState","resultCode","resultMsg","cmdKey","cmdData"}。
        失败抛 LiCommandError (含 resultCode / pushState)。

        参数:
          wake  : 下发前先远程唤醒 (默认 True, 可提高成功率)
          poll  : 是否轮询 cmd-result 直到 pushState 终态
          timeout / poll_interval: 轮询上限 (默认最多 ~60s, 每 2s 一次)
        """
        if wake:
            try:
                self.wakeup()
            except LiApiError as err:  # 唤醒失败不阻断 (车辆可能已在线)
                _LOGGER.debug("唤醒失败(忽略, 继续下发): %s", err)

        resp = self.send_command_raw(command_key, command_data)
        request_id = resp.get("requestId") or resp.get("data", {}).get("requestId") or ""

        # cmd/send 自身可能在响应里直接带业务错误
        rc = resp.get("resultCode")
        if rc not in (None, 0):
            raise LiCommandError(
                f"命令下发被拒 ({command_key}): resultCode={rc} "
                f"msg={resp.get('resultMsg') or resp.get('message')}",
                request_id=request_id, result_code=rc,
            )

        if not request_id:
            raise LiCommandError(
                f"命令下发无 requestId ({command_key}): {json.dumps(resp, ensure_ascii=False)[:200]}")

        if not poll:
            return {"requestId": request_id, "cmdKey": command_key,
                    "cmdData": command_data or {}, "raw": resp}

        result = self._poll_result(request_id, timeout, poll_interval)
        result.update({"requestId": request_id, "cmdKey": command_key,
                       "cmdData": command_data or {}})
        ps = result.get("pushState")
        rc_final = result.get("resultCode")
        if ps == PUSH_STATE_SUCCESS:
            # pushState=5 但 resultCode=-15/-8 表示"倒计时完成", App 视为成功
            if rc_final not in SUCCESS_RESULT_CODES and rc_final is not None:
                _LOGGER.info(
                    "车控完成(非零码) %s %s rc=%s msg=%s",
                    command_key, command_data, rc_final, result.get("resultMsg"))
            else:
                _LOGGER.info("车控成功 %s %s (requestId=%s)",
                             command_key, command_data, request_id)
            return result
        if ps == PUSH_STATE_FAILED:
            # pushState=7 但 resultCode 属于成功集合 → 同样视为成功
            if rc_final in SUCCESS_RESULT_CODES:
                _LOGGER.info(
                    "车控成功(pushState=7 但 rc=%s 属成功码) %s %s",
                    rc_final, command_key, command_data)
                return result
            raise LiCommandError(
                f"命令执行失败 ({command_key}): pushState={ps} "
                f"resultCode={result.get('resultCode')} msg={result.get('resultMsg')}",
                request_id=request_id,
                result_code=result.get("resultCode"), push_state=ps,
            )
        # ★ 超时未终态（2026-09-23 修复）
        #   pushState=1（执行中）时服务端只是没及时置终态，但命令【可能已生效】。
        #   实测：开空调命令超时后，FOffStatus 已变为 1（车确实开了）。
        #   这种情况【不应抛错】——否则 HA 会显示"失败"而实际成功，
        #   用户会重复点击。
        #   改为：记 warning + 返回结果，由实体状态（下一次轮询）反映真实情况。
        _LOGGER.warning(
            "车控命令未在超时内进入终态 %s %s pushState=%s msg=%s "
            "（命令可能已生效，状态以下次轮询为准）",
            command_key, command_data, ps, result.get("resultMsg"))
        return result

    def _poll_result(self, request_id: str, timeout: float, interval: float) -> dict:
        """轮询 cmd-result 直到 pushState 进入终态 (5 成功 / 7 失败) 或超时."""
        deadline = time.monotonic() + timeout
        last: dict = {}
        while time.monotonic() < deadline:
            try:
                last = self.get_command_result(request_id)
            except LiApiError as err:
                _LOGGER.debug("查命令结果失败(重试): %s", err)
                time.sleep(interval)
                continue
            if last.get("pushState") in (PUSH_STATE_SUCCESS, PUSH_STATE_FAILED):
                return last
            time.sleep(interval)
        return last

    def send_command_fire_and_forget(self, command_key: str,
                                    command_data: dict | None = None) -> dict:
        """下发但不等待结果 (用于寻车等不需要确认的命令)."""
        return self.send_command(command_key, command_data, poll=False)


def _hac_key_bytes(hac_key: str) -> bytes:
    """hac_key 归一化: hex(64字符) / base64 / 原始串 → 原始 32 字节.

    ★ 2026-09-24 修复（严重 bug，导致 VIN 取不到 / 所有 API 报
      「缺少必要的请求参数: X-CHJ-Key」）：

      问题：secrets._LazySecret 是 str 子类，构造时内容为空字符串，
            真实值靠 __str__() 延迟求值。
            但 str 子类的 .strip() / len() 走的是【空内容】：
              s = (hac_key or "").strip()   →  ""   （丢了真实值！）
              len(s) == 64                  →  False
              s.encode()                    →  b""  ❌

            表现为：_hac 长度为 0 → 签名错误 → 服务端拒绝。

      修复：先显式 str() 强制求值，再做后续处理。
    """
    # ★ 关键修复（2026-09-24 第二次修正）：
    #   不能用 `hac_key or ""` —— `or` 会触发 _LazySecret.__bool__()，
    #   而它基于【底层空内容】返回 False → 直接走 "" 分支！
    #   必须用 `is not None` 判断，再 str() 强制求值。
    s = str(hac_key).strip() if hac_key is not None else ""
    if len(s) == 64:
        try:
            return bytes.fromhex(s)
        except ValueError:
            pass
    try:
        raw = base64.b64decode(s)
        if len(raw) == 32:
            return raw
    except Exception:  # noqa: BLE001
        pass
    return s.encode()


_SSL_CTX = None

def _ssl_ctx():
    global _SSL_CTX
    if _SSL_CTX is None:
        import ssl
        _SSL_CTX = ssl.create_default_context()
    return _SSL_CTX
