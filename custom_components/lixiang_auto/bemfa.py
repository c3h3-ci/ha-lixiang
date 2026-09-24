"""巴法云（Bemfa）桥接 — 把 HA 的 cover/switch 同步到巴法主题.

巴法云【不会】自动发现 Home Assistant 实体。设备类型由主题名后三位决定：
  xxx003 → 风扇（离散档 on#1-4）★ 座椅推荐
  xxx009 → 窗帘（百分比 on#N%）
  xxx006 / xxx001 → 开关（仅 on/off）

本模块用巴法 HTTP API：
  · 推送状态  POST https://apis.bemfa.com/va/postJsonMsg
  · 拉取指令  GET  https://apis.bemfa.com/va/getmsg

座椅档位按风扇协议：on / off / on#1 / on#2 / on#3。
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Callable, Awaitable

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN, LOGGER_NAME

_LOGGER = logging.getLogger(LOGGER_NAME)

POST_MSG_URL = "https://apis.bemfa.com/va/postJsonMsg"
GET_MSG_URL = "https://apis.bemfa.com/va/getmsg"
POLL_SECONDS = 4

OPT_UID = "bemfa_uid"
OPT_WIN = "bemfa_topic_window"       # 如 lxcw009
OPT_TRUNK = "bemfa_topic_trunk"      # 如 lxweimen009
OPT_FIND = "bemfa_topic_find"        # 如 lxfind006
# 座椅等：逗号分隔  主题=unique后缀
# 座椅推荐风扇 003：zjzr003=seat_fl_heat,...
OPT_SWITCHES = "bemfa_topic_switches"

# 座椅/开关映射允许的主题后缀
_SWITCH_SUFFIXES = ("003", "006", "001", "009")


def _topic_ok(topic: str, *suffixes: str) -> bool:
    t = (topic or "").strip().lower()
    if not t or not t.isalnum():
        return False
    return any(t.endswith(s) for s in suffixes)


def _parse_switch_map(raw: str) -> list[tuple[str, str]]:
    """解析 `topic=suffix,topic2=suffix2` → [(topic, suffix), ...]。

    主题后缀：
      003 = 风扇（推荐座椅：on#1-3 档）
      006/001 = 开关（仅 on/off）
      009 = 窗帘（on#百分比）
    """
    out: list[tuple[str, str]] = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        topic, suffix = part.split("=", 1)
        topic, suffix = topic.strip().lower(), suffix.strip()
        if not (topic and suffix and topic.isalnum()):
            continue
        if topic.endswith(_SWITCH_SUFFIXES):
            out.append((topic, suffix))
    return out


def _is_fan_topic(topic: str) -> bool:
    return str(topic or "").lower().endswith("003")


class BemfaBridge:
    """单条 config entry 的巴法云双向桥。"""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.hass = hass
        self.entry = entry
        opts = entry.options or {}
        self.uid = str(opts.get(OPT_UID) or "").strip()
        self.topic_win = str(opts.get(OPT_WIN) or "").strip().lower()
        self.topic_trunk = str(opts.get(OPT_TRUNK) or "").strip().lower()
        self.topic_find = str(opts.get(OPT_FIND) or "").strip().lower()
        self.switch_map = _parse_switch_map(str(opts.get(OPT_SWITCHES) or ""))
        self._last_pub: dict[str, str] = {}
        self._last_cmd: dict[str, str] = {}
        self._seen_init: set[str] = set()
        self._unsub = None
        self._busy = False
        # 收到巴法指令后暂停状态回写（避免 /up 覆盖尚未读到的 off/档位）
        self._suppress_status_until: dict[str, float] = {}
        import time as _time
        self._time = _time

    @property
    def enabled(self) -> bool:
        if not self.uid:
            return False
        return bool(
            _topic_ok(self.topic_win, "009")
            or _topic_ok(self.topic_trunk, "009")
            or _topic_ok(self.topic_find, "006", "001")
            or bool(self.switch_map)
        )

    def validate_topics(self) -> list[str]:
        errs: list[str] = []
        if not self.uid:
            errs.append("缺少巴法云 uid（用户私钥）")
        if self.topic_win and not _topic_ok(self.topic_win, "009"):
            errs.append(f"车窗主题须以 009 结尾: {self.topic_win}")
        if self.topic_trunk and not _topic_ok(self.topic_trunk, "009"):
            errs.append(f"尾门主题须以 009 结尾: {self.topic_trunk}")
        if self.topic_find and not _topic_ok(self.topic_find, "006", "001"):
            errs.append(f"寻车主题须以 006 或 001 结尾: {self.topic_find}")
        if str(self.entry.options.get(OPT_SWITCHES) or "").strip() and not self.switch_map:
            errs.append(
                "开关主题格式应为 主题=suffix（如 zjzr003=seat_fl_heat），"
                "主题后缀 003(风扇推荐)/006/001/009"
            )
        return errs

    def _find_entity_id(self, domain: str, unique_frag: str) -> str | None:
        try:
            from homeassistant.helpers import entity_registry as er
        except Exception:  # noqa: BLE001
            return None
        reg = er.async_get(self.hass)
        for ent in reg.entities.values():
            if (
                ent.platform == DOMAIN
                and ent.domain == domain
                and unique_frag in (ent.unique_id or "")
            ):
                return ent.entity_id
        return None

    # ---------- 状态推送 ----------

    async def _post_msg(self, topic: str, msg: str, *, status_only: bool = False) -> None:
        """推送消息。status_only=True 时用 topic/up（只更云端状态，不当指令）。"""
        from homeassistant.helpers import aiohttp_client
        session = aiohttp_client.async_get_clientsession(self.hass)
        pub_topic = f"{topic}/up" if status_only else topic
        payload = {"uid": self.uid, "topic": pub_topic, "type": 1, "msg": msg}
        try:
            async with session.post(
                POST_MSG_URL, json=payload, timeout=aiohttp_client.DEFAULT_TIMEOUT
            ) as resp:
                if resp.status == 200:
                    if status_only:
                        # 状态回写不更新 _last_cmd，避免把自己状态当下一条指令
                        self._last_pub[topic] = msg
                    else:
                        self._last_pub[topic] = msg
                else:
                    body = await resp.text()
                    _LOGGER.debug(
                        "巴法推送失败 %s %s: %s", pub_topic, resp.status, body[:120]
                    )
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("巴法推送异常 %s: %s", pub_topic, err)

    def _window_state_msg(self) -> str | None:
        """物理语义：开→on / 关→off / 中间→on#N（给小爱/巴法 App）。"""
        eid = self._find_entity_id("cover", "cover_window")
        if not eid:
            return None
        st = self.hass.states.get(eid)
        if st is None:
            return None
        phys = st.attributes.get("physical_open_percent")
        if phys is None:
            phys = st.attributes.get("current_position")
            if phys is None:
                # 标准 cover：open=开, closed=关
                phys = 100 if st.state == "open" else 0
        phys = max(0, min(100, int(phys)))
        if phys <= 1:
            return "off"
        if phys >= 99:
            return "on"
        return f"on#{phys}"

    def _trunk_state_msg(self) -> str | None:
        eid = self._find_entity_id("cover", "cover_trunk")
        if not eid:
            return None
        st = self.hass.states.get(eid)
        if st is None:
            return None
        return "off" if st.state == "closed" else "on"

    def _switch_state_msg(self, suffix: str) -> str | None:
        """座椅状态：off / on / on#N（N=1-3 档），兼容 fan 与 switch。"""
        eid = (
            self._find_entity_id("fan", f"fan_{suffix}")
            or self._find_entity_id("switch", f"sw_{suffix}")
        )
        if not eid:
            return None
        st = self.hass.states.get(eid)
        if st is None:
            return None
        # fan: percentage 属性；switch: level 属性
        level = st.attributes.get("level")
        if level is None and eid.startswith("fan."):
            pct = st.attributes.get("percentage")
            try:
                if pct is not None:
                    p = int(pct)
                    level = 0 if p <= 0 else 1 if p <= 33 else 2 if p <= 66 else 3
            except (TypeError, ValueError):
                level = None
        try:
            lvl = int(level) if level is not None else None
        except (TypeError, ValueError):
            lvl = None
        if st.state in ("off", "unavailable") and not lvl:
            # fan off 或 switch off
            if st.state == "off" or (lvl is not None and lvl == 0):
                return "off"
        if lvl is not None and lvl == 0:
            return "off"
        if st.state == "on" or (lvl is not None and lvl > 0):
            if lvl and 1 <= lvl <= 3:
                return f"on#{lvl}"
            return "on"
        return "off"

    def _status_suppressed(self, topic: str) -> bool:
        until = self._suppress_status_until.get(topic, 0)
        return self._time.monotonic() < until

    def _mark_cmd_suppress(self, topic: str, seconds: float = 12) -> None:
        self._suppress_status_until[topic] = self._time.monotonic() + seconds

    async def async_push_states(self) -> None:
        if not self.enabled or self._busy:
            return
        self._busy = True
        try:
            if _topic_ok(self.topic_win, "009"):
                msg = self._window_state_msg()
                if msg and self._last_pub.get(self.topic_win) != msg:
                    if not self._status_suppressed(self.topic_win):
                        await self._post_msg(self.topic_win, msg, status_only=True)
            if _topic_ok(self.topic_trunk, "009"):
                msg = self._trunk_state_msg()
                if msg and self._last_pub.get(self.topic_trunk) != msg:
                    if not self._status_suppressed(self.topic_trunk):
                        await self._post_msg(self.topic_trunk, msg, status_only=True)
            if _topic_ok(self.topic_find, "006", "001"):
                if self._last_pub.get(self.topic_find) != "off":
                    await self._post_msg(self.topic_find, "off", status_only=True)
            for topic, suffix in self.switch_map:
                if self._status_suppressed(topic):
                    continue
                msg = self._switch_state_msg(suffix)
                if msg and self._last_pub.get(topic) != msg:
                    await self._post_msg(topic, msg, status_only=True)
        finally:
            self._busy = False

    # ---------- 指令拉取 ----------

    async def _get_msg(self, topic: str) -> str:
        from homeassistant.helpers import aiohttp_client
        session = aiohttp_client.async_get_clientsession(self.hass)
        params = {"uid": self.uid, "topic": topic, "type": "1", "num": "1"}
        try:
            async with session.get(
                GET_MSG_URL, params=params, timeout=aiohttp_client.DEFAULT_TIMEOUT
            ) as resp:
                if resp.status != 200:
                    return ""
                data = await resp.json(content_type=None)
                items = (data or {}).get("data") or []
                if not items:
                    return ""
                return str(items[0].get("msg") or "")
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("巴法拉取失败 %s: %s", topic, err)
            return ""

    async def _call(self, domain: str, service: str, data: dict) -> None:
        await self.hass.services.async_call(
            domain, service, data, blocking=True
        )

    def _window_entity_obj(self):
        """取 LiCarWindowCover 实例（绕开反向 open/close 服务）。"""
        eid = self._find_entity_id("cover", "cover_window")
        if not eid:
            return None
        try:
            from homeassistant.helpers.entity import async_get
        except Exception:  # noqa: BLE001
            async_get = None
        # 通过 entity component 拿对象
        try:
            comp = self.hass.data.get("entity_components", {}).get("cover")
            if comp is not None and hasattr(comp, "get_entity"):
                return comp.get_entity(eid)
        except Exception:  # noqa: BLE001
            pass
        # 回退：从 cover 平台实体表找
        try:
            from homeassistant.helpers.entity_component import EntityComponent
            for obj in getattr(comp, "entities", {}).values() if comp else []:
                if getattr(obj, "entity_id", None) == eid:
                    return obj
        except Exception:  # noqa: BLE001
            pass
        return None

    async def _apply_window_cmd(self, raw: str) -> None:
        """小爱/巴法窗帘指令 → 物理开/关/开度（经 cover 实体，保留位置能力）。

        语义（巴法 009）：
          on / pause     → 全开
          on#N           → 物理开 N%
          off            → 全关
        """
        raw = (raw or "").strip().lower()
        ent = self._window_entity_obj()
        if ent is not None and hasattr(ent, "async_physical_open"):
            if raw in ("on", "pause"):
                _LOGGER.info("巴法→物理开窗 (on)")
                await ent.async_physical_open(99)
                return
            if raw.startswith("on#"):
                try:
                    pct = int(raw.split("#", 1)[1])
                except ValueError:
                    pct = 100
                pct = max(0, min(100, pct))
                _LOGGER.info("巴法→物理开窗 %s%%", pct)
                if pct <= 0:
                    await ent.async_physical_close()
                else:
                    await ent.async_physical_open(pct)
                return
            if raw == "off":
                _LOGGER.info("巴法→物理关窗 (off)")
                await ent.async_physical_close()
                return
            return

        # 实例找不到时：标准 cover 服务（0关…100开）
        eid = self._find_entity_id("cover", "cover_window")
        if not eid:
            return
        if raw in ("on", "pause"):
            await self._call("cover", "open_cover", {"entity_id": eid})
        elif raw.startswith("on#"):
            try:
                pct = int(raw.split("#", 1)[1])
            except ValueError:
                pct = 100
            pct = max(0, min(100, pct))
            await self._call(
                "cover",
                "set_cover_position",
                {"entity_id": eid, "position": pct},
            )
        elif raw == "off":
            await self._call("cover", "close_cover", {"entity_id": eid})

    async def _apply_trunk_cmd(self, raw: str) -> None:
        eid = self._find_entity_id("cover", "cover_trunk")
        if not eid:
            return
        raw = (raw or "").strip().lower()
        if raw == "on":
            await self._call("cover", "open_cover", {"entity_id": eid})
        elif raw == "off":
            await self._call("cover", "close_cover", {"entity_id": eid})

    async def _apply_find_cmd(self, raw: str) -> None:
        eid = self._find_entity_id("switch", "sw_find_car")
        if not eid:
            return
        if (raw or "").strip().lower() == "on":
            await self._call("switch", "turn_on", {"entity_id": eid})

    def _switch_entity_obj(self, suffix: str):
        """优先 fan（座椅档位 UI），其次 switch。"""
        for domain, frag in (
            ("fan", f"fan_{suffix}"),
            ("switch", f"sw_{suffix}"),
        ):
            eid = self._find_entity_id(domain, frag)
            if not eid:
                continue
            try:
                comp = self.hass.data.get("entity_components", {}).get(domain)
                if comp is not None and hasattr(comp, "get_entity"):
                    obj = comp.get_entity(eid)
                    if obj is not None:
                        return obj
            except Exception:  # noqa: BLE001
                pass
        return None

    def _seat_entity_id(self, suffix: str) -> str | None:
        return (
            self._find_entity_id("fan", f"fan_{suffix}")
            or self._find_entity_id("switch", f"sw_{suffix}")
        )

    def _number_entity_id(self, suffix: str) -> str | None:
        return self._find_entity_id("number", f"num_{suffix}_level")

    async def _apply_switch_cmd(self, raw: str, suffix: str, topic: str = "") -> None:
        """座椅等开关/档位指令（按主题后缀分流）。

        003 风扇（推荐）: on / off / on#1 / on#2 / on#3（on#4 → 3 档）
        006/001 开关: on / off（on#1-3 仍兼容）
        009 窗帘: on / off / on#N（1-3 直接档；4-100 百分比→1-3 档）
        """
        raw = (raw or "").strip().lower()
        fan = _is_fan_topic(topic)
        level: int | None = None
        turning_off = False

        if raw in ("off", "0"):
            turning_off = True
            level = 0
        elif raw in ("on", "pause"):
            level = None  # 默认 3 档 turn_on
        elif raw == "1" and not raw.startswith("on"):
            # 部分语音把档位发成裸 "1"/"2"/"3"
            try:
                n = int(raw)
                level = max(1, min(3, n))
            except ValueError:
                level = None
        elif raw.startswith("on#"):
            try:
                n = int(raw.split("#", 1)[1])
            except ValueError:
                n = 3
            if n <= 0:
                turning_off = True
                level = 0
            elif fan:
                # 风扇协议：离散档，003 只有 0-3（on#4 钳到 3）
                level = max(1, min(3, n))
            elif n <= 3:
                level = n
            else:
                # 窗帘百分比 → 1/2/3 档
                level = 1 if n <= 33 else 2 if n <= 66 else 3
        elif raw in ("2", "3"):
            level = int(raw)
        else:
            _LOGGER.debug("忽略未知座椅指令 %s ← %s", suffix, raw)
            return

        ent = self._switch_entity_obj(suffix)
        eid = self._seat_entity_id(suffix)
        if not ent and not eid:
            _LOGGER.warning("巴法座椅找不到实体 fan_/sw_%s", suffix)
            return

        # fan 与 switch 共用 turn_on/turn_off/set_level 接口
        if turning_off:
            _LOGGER.info("巴法→座椅关闭 %s (topic=%s)", eid or suffix, topic or "-")
            if ent is not None and hasattr(ent, "async_turn_off"):
                await ent.async_turn_off()
            elif eid:
                domain = "fan" if ".fan_" in (ent and getattr(ent, "entity_id", "") or eid) or eid.startswith("fan.") else "switch"
                if eid.startswith("fan."):
                    await self._call("fan", "turn_off", {"entity_id": eid})
                else:
                    await self._call("switch", "turn_off", {"entity_id": eid})
            nid = self._number_entity_id(suffix)
            if nid:
                await self._call(
                    "number", "set_value",
                    {"entity_id": nid, "value": 0},
                )
        elif level is None:
            _LOGGER.info("巴法→座椅打开(默认3档) %s", eid or suffix)
            if ent is not None and hasattr(ent, "async_turn_on"):
                await ent.async_turn_on()
            elif eid and eid.startswith("fan."):
                await self._call("fan", "turn_on", {"entity_id": eid})
            elif eid:
                await self._call("switch", "turn_on", {"entity_id": eid})
        else:
            _LOGGER.info(
                "巴法→座椅档位 %s = %s (fan=%s)",
                eid or suffix, level, fan,
            )
            if ent is not None and hasattr(ent, "async_set_level"):
                await ent.async_set_level(level)
            elif ent is not None and level == 0:
                await ent.async_turn_off()
            elif eid and eid.startswith("fan."):
                # 百分比: 1→33, 2→66, 3→100
                pct = {1: 33, 2: 66, 3: 100}.get(level, 100)
                if level <= 0:
                    await self._call("fan", "turn_off", {"entity_id": eid})
                else:
                    await self._call(
                        "fan", "set_percentage",
                        {"entity_id": eid, "percentage": pct},
                    )
            elif ent is not None:
                await ent.async_turn_on()
            elif eid:
                svc = "turn_off" if level == 0 else "turn_on"
                domain = "fan" if eid.startswith("fan.") else "switch"
                await self._call(domain, svc, {"entity_id": eid})
            nid = self._number_entity_id(suffix)
            if nid:
                await self._call(
                    "number", "set_value",
                    {"entity_id": nid, "value": float(level)},
                )

    async def async_poll_once(self) -> None:
        if not self.enabled:
            return
        checks: list[tuple[str, Any]] = []
        if _topic_ok(self.topic_win, "009"):
            checks.append((self.topic_win, self._apply_window_cmd))
        if _topic_ok(self.topic_trunk, "009"):
            checks.append((self.topic_trunk, self._apply_trunk_cmd))
        if _topic_ok(self.topic_find, "006", "001"):
            checks.append((self.topic_find, self._apply_find_cmd))
        for topic, suffix in self.switch_map:
            checks.append(
                (topic, lambda raw, s=suffix, t=topic: self._apply_switch_cmd(raw, s, t))
            )

        for topic, handler in checks:
            msg = await self._get_msg(topic)
            if not msg:
                continue
            # 指令去重只看「已执行过的指令」last_cmd，不看状态 last_pub
            # （否则状态 off 会吞掉用户刚点的 off）
            if topic not in self._seen_init:
                self._seen_init.add(topic)
                self._last_cmd[topic] = msg
                continue
            if self._last_cmd.get(topic) == msg:
                continue
            self._last_cmd[topic] = msg
            _LOGGER.info("巴法指令 %s ← %s", topic, msg)
            # 执行前先抑制状态回写，避免 /up 把这条指令盖掉后下轮读到旧状态
            self._mark_cmd_suppress(topic, 12)
            try:
                await handler(msg)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("执行巴法指令失败 %s %s: %s", topic, msg, err)

    # ---------- 生命周期 ----------

    async def async_start(self) -> None:
        if not self.enabled:
            errs = self.validate_topics()
            if errs:
                _LOGGER.info("巴法云桥接未启用: %s", "; ".join(errs))
            return
        _LOGGER.info(
            "巴法云桥接已启用: win=%s trunk=%s find=%s switches=%s",
            self.topic_win or "-",
            self.topic_trunk or "-",
            self.topic_find or "-",
            ",".join(f"{t}={s}" for t, s in self.switch_map) or "-",
        )
        init_topics = [t for t in (
            self.topic_win, self.topic_trunk, self.topic_find
        ) if t]
        init_topics.extend(t for t, _ in self.switch_map)
        for topic in init_topics:
            m = await self._get_msg(topic)
            self._seen_init.add(topic)
            if m:
                self._last_cmd[topic] = m
        await self.async_push_states()

        async def _tick(_now=None) -> None:
            try:
                await self.async_poll_once()
                await self.async_push_states()
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("巴法轮询异常（忽略）: %s", err)

        self._unsub = async_track_time_interval(
            self.hass, _tick, timedelta(seconds=POLL_SECONDS)
        )

    async def async_stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None


async def async_setup_bemfa(
    hass: HomeAssistant, entry
) -> BemfaBridge | None:
    """创建并启动桥（配置了 uid 才返回）。"""
    if not (entry.options or {}).get(OPT_UID):
        return None
    bridge = BemfaBridge(hass, entry)
    await bridge.async_start()
    return bridge
