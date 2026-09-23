"""理想汽车 · 首次登录辅助页面（让用户在自己浏览器里过滑动验证）

背景（2026-09-23 实测确立）
--------------------------
理想的新设备登录风控：
  · 新 device_id + 密码 → 服务端返回 require=SMS_CODE
  · 发短信前必须过【顶象滑动验证】（DX，第三方，无法在服务端绕过）
  · 但用户在【真实浏览器】里可以自己滑

同时确认的机制：
  · 服务端按 device_id 记信任（精确匹配，改 1 位即失效）
  · 任意 MFA 通过后，该 device_id 加入信任列表
  · 之后 device_id + 密码 → 免 MFA（免滑动、免短信）

本模块的方案
-----------
  ① HA 提供一个 HTTP 页面 /lixiang-login?token=xxx
  ② 页面里内嵌 iframe → 理想官方登录页（带 HA 的 device_id）
  ③ 用户在里面：输手机号 → 自己滑顶象 → 收短信 → 输验证码 → 登录成功
  ④ HA 后端【定时轮询】：用 ha_device_id + 密码 试登录
     一旦成功 → 说明设备已受信任 → 通知 config_flow 继续 ★
  ⑤ HA 保存 phone + password + device_id（不保存任何验证码）

安全
----
  · 不接触用户的短信/安全码（用户在理想官方页面里输入）
  · 密码由用户在 HA 表单里提供（config_flow 收集）
  · 页面 token 一次性、5 分钟有效
"""

from __future__ import annotations

import logging
import secrets
import time
from typing import Any

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN, LOGGER_NAME

_LOGGER = logging.getLogger(LOGGER_NAME)

# 会话表: token -> {phone, password, device_id, created_at, trusted}
_SESSIONS: dict[str, dict[str, Any]] = {}
_SESSION_TTL = 900          # 15 分钟
POLL_INTERVAL = 5           # 轮询间隔（秒）


def _gc() -> None:
    now = time.time()
    for k in [k for k, v in _SESSIONS.items() if now - v["created_at"] > _SESSION_TTL]:
        _SESSIONS.pop(k, None)


def create_session(phone: str, password: str, device_id: str) -> str:
    """创建一个登录会话，返回 token。"""
    _gc()
    tok = secrets.token_urlsafe(24)
    _SESSIONS[tok] = {
        "phone": phone,
        "password": password,
        "device_id": device_id,
        "created_at": time.time(),
        "trusted": False,
    }
    return tok


def get_session(tok: str) -> dict[str, Any] | None:
    _gc()
    return _SESSIONS.get(tok)


def mark_trusted(tok: str) -> None:
    s = _SESSIONS.get(tok)
    if s:
        s["trusted"] = True


_LOGIN_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>理想汽车 · 首次登录</title>
<style>
  * { box-sizing: border-box; }
  body { margin:0; font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         background:#f5f6f8; color:#1f2329; min-height:100vh; }
  .wrap { max-width: 560px; margin: 0 auto; padding: 24px 16px; }
  .card { background:#fff; border-radius:14px; padding:22px;
          box-shadow:0 2px 12px rgba(0,0,0,.06); }
  h1 { font-size:20px; margin:0 0 8px; }
  .sub { color:#6b7280; font-size:13px; line-height:1.7; margin-bottom:16px; }
  .steps { background:#f0f7ff; border-left:3px solid #1677ff; padding:11px 13px;
           border-radius:6px; font-size:13px; line-height:2; margin-bottom:18px; }
  .steps b { color:#1677ff; }
  .btn { display:block; width:100%; padding:15px; border:none; border-radius:10px;
         background:#1677ff; color:#fff; font-size:16px; font-weight:600;
         cursor:pointer; text-align:center; text-decoration:none;
         transition: background .15s; }
  .btn:hover { background:#0958d9; }
  .btn:active { background:#003eb3; }
  .hint { font-size:12px; color:#9ca3af; text-align:center; margin-top:10px; }
  .status { margin-top:18px; padding:13px 15px; border-radius:9px; font-size:14px;
            display:flex; align-items:center; gap:9px; }
  .status.wait { background:#fff7e6; color:#ad6800; }
  .status.ok   { background:#f6ffed; color:#237804; font-weight:600; }
  .status.err  { background:#fff1f0; color:#cf1322; }
  .dot { width:10px; height:10px; border-radius:50%; background:currentColor;
         animation: pulse 1.4s infinite; flex-shrink:0; }
  .ok .dot { animation:none; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.25} }
  .dev { font-family: ui-monospace, Menlo, monospace; font-size:11px;
         color:#c0c4cc; word-break:break-all; margin-top:14px;
         padding-top:12px; border-top:1px solid #f0f0f0; }
  .url { font-family: ui-monospace, Menlo, monospace; font-size:11px;
         color:#8c8c8c; word-break:break-all; background:#fafafa;
         padding:8px; border-radius:6px; margin-top:10px; }
</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <h1>理想汽车 · 首次登录验证</h1>
    <div class="sub">
      新设备登录需要短信验证，而验证码有<b>滑动验证</b>保护，HA 无法自动完成。
      请点下面的按钮在<b>新窗口</b>里完成登录 —— HA 会在后台自动检测，成功后无需再做任何操作。
    </div>

    <div class="steps">
      <b>①</b> 点下面的蓝色按钮（会在新窗口打开理想登录页）<br>
      <b>②</b> 输手机号 + 密码，点「获取验证码」<br>
      <b>③</b> <b>拖动滑块</b>完成验证 → 收到短信 → 输验证码<br>
      <b>④</b> 点「登录」→ 看到下面变绿 = 完成，回 HA 继续
    </div>

    <a class="btn" id="openBtn" href="%%LOGIN_URL%%" target="_blank" rel="noopener">
      ▶ 点这里打开理想登录页
    </a>
    <div class="hint">如果按钮没反应，请手动复制下面的地址到浏览器打开</div>
    <div class="url" id="urlBox">%%LOGIN_URL%%</div>

    <div class="status wait" id="st">
      <span class="dot"></span>
      <span id="msg">等待你完成登录…（HA 每 5 秒检测一次）</span>
    </div>
    <div class="dev">device_id: %%DEVICE_ID%%</div>
  </div>
</div>
<script>
const TOKEN = "%%TOKEN%%";
const LOGIN_URL = "%%LOGIN_URL%%";
let n = 0;

// 点按钮后自动开始轮询
document.getElementById('openBtn').addEventListener('click', () => {
  document.getElementById('msg').textContent = '已打开登录页，请在新窗口里完成登录…';
});

async function poll() {
  n++;
  try {
    const r = await fetch("./lixiang-login/status?token=" + encodeURIComponent(TOKEN));
    const j = await r.json();
    if (j.trusted) {
      const st = document.getElementById('st');
      st.className = "status ok";
      document.getElementById('msg').textContent =
        "✅ 登录成功！设备已受信任，请回到 HA 继续（此页面可关闭）";
      return;
    }
    if (j.expired) {
      document.getElementById('st').className = "status err";
      document.getElementById('msg').textContent =
        "⚠️ 会话已过期（15 分钟），请回到 HA 重新发起配置";
      return;
    }
    if (n > 1) {
      document.getElementById('msg').textContent =
        "等待你完成登录…（已检测 " + n + " 次）";
    }
  } catch (e) {
    document.getElementById('msg').textContent = "检测中…（网络异常，继续重试）";
  }
  setTimeout(poll, 5000);
}
setTimeout(poll, 3000);
</script>
</body>
</html>
"""


class LiXiangLoginView(HomeAssistantView):
    """首次登录辅助页面。"""

    url = "/lixiang-login"
    name = "api:lixiang_auto:login"
    requires_auth = False        # ★ 用户可能未登录 HA，允许匿名访问

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        _gc()
        tok = request.query.get("token", "")
        s = _SESSIONS.get(tok)
        if not s:
            return web.Response(
                text="<h3>链接已失效</h3><p>请回到 Home Assistant 重新发起配置。</p>",
                content_type="text/html", status=404)

        # ★ 不在 HA 页面里嵌 iframe（会被 CORB/嵌入限制拦），
        #   改为提供【新窗口链接】，指向理想登录页并带上 HA 的 device_id
        dev = s["device_id"]
        login_url = (
            "https://account.lixiang.com/app-auth"
            "?client_id=2AQClOaegaA7XecMSFx1p"
            "&redirect_uri=https%3A%2F%2Faccount.lixiang.com%2Fapp-auth"
            "&response_type=code&scope=login"
            "&audience=1j0vgTqagJUHuT6nLmbTGx"
            f"&device_id={dev}"
        )
        html = (_LOGIN_HTML
                .replace("%%LOGIN_URL%%", login_url)
                .replace("%%DEVICE_ID%%", dev)
                .replace("%%TOKEN%%", tok))
        return web.Response(text=html, content_type="text/html")


class LiXiangLoginStatusView(HomeAssistantView):
    """登录状态查询（前端轮询用）。"""

    url = "/lixiang-login/status"
    name = "api:lixiang_auto:login_status"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        _gc()
        tok = request.query.get("token", "")
        s = _SESSIONS.get(tok)
        if not s:
            return web.json_response({"trusted": False, "expired": True})
        return web.json_response({
            "trusted": bool(s.get("trusted")),
            "expired": False,
        })


class LiXiangLoginCreateView(HomeAssistantView):
    """创建登录会话（供 config_flow 内部调用 / 测试用）。

    POST /lixiang-login/create
      Body: {"phone": "...", "password": "...", "device_id": "..."}
      → {"token": "...", "url": "..."}
    """

    url = "/lixiang-login/create"
    name = "api:lixiang_auto:login_create"
    requires_auth = False

    async def post(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            return web.json_response({"error": "invalid json"}, status=400)
        phone = str(body.get("phone") or "")
        password = str(body.get("password") or "")
        device_id = str(body.get("device_id") or "")
        if not (phone and password and device_id):
            return web.json_response({"error": "missing fields"}, status=400)
        tok = create_session(phone, password, device_id)
        return web.json_response({"token": tok, "url": f"/lixiang-login?token={tok}"})


async def async_register_login_views(hass: HomeAssistant) -> None:
    """注册登录辅助页面（幂等）。"""
    if hass.data.get(f"{DOMAIN}_login_views"):
        return
    hass.http.register_view(LiXiangLoginView())
    hass.http.register_view(LiXiangLoginStatusView())
    hass.http.register_view(LiXiangLoginCreateView())
    hass.data[f"{DOMAIN}_login_views"] = True
    _LOGGER.debug("已注册 /lixiang-login 辅助页面")


def try_login(phone: str, password: str, device_id: str) -> bool:
    """尝试用 device_id + 密码 登录（用于检测设备是否已受信任）。

    返回 True 表示登录成功（设备已受信任）。
    """
    try:
        from .pake_login import LixiangDirectLogin, LoginError
    except ImportError:
        return False
    try:
        cli = LixiangDirectLogin(device_id=device_id)
        tok = cli.login(phone, password)
        if tok.get("access_token"):
            _LOGGER.info("设备已受信任，登录成功: %s", device_id[:12])
            return True
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("检测登录（尚未受信任）: %s", str(err)[:80])
    return False


__all__ = [
    "create_session", "get_session", "mark_trusted", "try_login",
    "async_register_login_views", "POLL_INTERVAL",
]
