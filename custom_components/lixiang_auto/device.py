"""设备信息（DeviceInfo）—— 统一构造，名字取自服务端。

原理
----
`get_vehicles()` → `/saos-vehicle-api/v2-0/vehicles/basics` 返回：

    {
      "modelId": "100167931652606785",
      "modelName": "理想L6",              ← 车型名
      "seriesName": "理想L6",
      "vehicleInfo": {
          "vehicleNickname": "理想L6",    ← ★ App 用的「车辆昵称」
          "spu": "理想L6 Pro",            ← 具体版本（Pro/Max/Ultra）
          "seat": "五座",
          "seatCount": 5,
          "plateNumber": "浙CFS3517",     ← 车牌
          "variableModel": "AD PRO+无踏板+...",
          ...
      }
    }

★ App 用 `vehicleNickname` 作为设备/车辆显示名（见 `VehicleInfo.java`
  的 `vehicleNickname` 字段，以及 `I18N Setting` 的「车辆昵称」）。

★ 之前的问题：12 个平台文件里硬编码 `"理想 L6"` / `"Li Auto L6"`，
  导致 L8/L9 用户的设备也显示成 L6。

本模块的解法：
    · 优先用服务端的 `vehicleNickname`
    · 回退到 `spu` → `modelName` → 车型能力表的 `desc` → "Li Auto"
    · 英文名用 `spu`/`modelName` 的英文映射（车型代号 + 版本）

用法
----
    from .device import build_device_info
    device_info = build_device_info(coordinator, entry, li_api)
"""

from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, CONF_VIN, LOGGER_NAME

_LOGGER = logging.getLogger(LOGGER_NAME)


# ---------------------------------------------------------------------------
# 车型代号（用于拼英文名）
# ---------------------------------------------------------------------------
# 中文 spu/modelName → 英文系列名
#   理想L6（带引号会在测试里误报，故省）→ L6
#   理想L6 Pro  → L6 Pro
#   理想 MEGA   → MEGA
_SERIES_RE = re.compile(r"理想\s*(L\d|MEGA|W\d+|M\d+)", re.IGNORECASE)
# 版本后缀（Pro / Max / Ultra / Air）
_TRIM_RE = re.compile(
    r"\b(Pro|Max|U?I?tra|Ultra|Air|Plus|Premium|Standard|Launch|Entry|Livis)\b",
    re.IGNORECASE)


def _split_series_trim(name: str) -> tuple[str, str]:
    """把车型名拆成 (系列, 版本)。

    支持两种格式：
        · 服务端 spu：「理想L6 Pro」 / 「理想L6」 / 「理想 MEGA」
        · 能力表 desc：「L6Pro」 / 「L9Max车型」 （无空格）

    例：
        '理想L6 Pro'   → ('L6', 'Pro')
        'L6Pro'        → ('L6', 'Pro')
        'L9Max车型'     → ('L9', 'Max')
        '理想MEGA'     → ('MEGA', '')
        'W01_25_home'  → ('W01', '')
    """
    if not name:
        return ("", "")

    s = name.strip()
    # ① 规范形式：在「系列」与「版本词」之间插空格
    #    例：'L9Max车型' → 'L9 Max车型'；'L6Pro' → 'L6 Pro'
    s = re.sub(r"(L\d|MEGA|W\d+|M\d+)\s*(?=[A-Za-z])", r"\1 ", s, flags=re.IGNORECASE)
    #    版本词后若有中文，也截断（'Max车型' → 'Max'）
    s = re.sub(r"\b(Pro|Max|Ultra|Air|Plus|Premium|Standard|Launch|Entry|UItra|Livis)"
               r"(?:[\u4e00-\u9fff]+|\d+)?",
               r"\1 ", s, flags=re.IGNORECASE)

    # ② 系列
    series = ""
    m = _SERIES_RE.search(s) or _SERIES_RE.search(f"理想{s}")
    if m:
        series = m.group(1).upper()

    # ③ 版本
    trim = ""
    t = _TRIM_RE.search(s)
    if t:
        trim = t.group(1).title()
        # ★ App 里把 Ultra 写作 "UItra"（I 大写），统一成标准写法
        if trim.lower() in ("uitra", "ultra"):
            trim = "Ultra"

    return (series, trim)


def vehicle_names(li_api: Any, ability: Any = None,
                 cached: dict | None = None) -> dict[str, str]:
    """从服务端取车辆显示名。

    ★ 2026-09-26：优先用 `cached`（coordinator.data 里已取好的），
      避免在事件循环里发 HTTP（会触发 HA 的 blocking call 告警）。

    返回 {"zh": 中文名, "en": 英文名, "model": DeviceInfo 的 model 字段, "spu": ...}
    """
    # ⓪ 已有缓存 → 直接用（零网络）
    if cached and cached.get("zh"):
        return {
            "zh": cached.get("zh", ""),
            "en": cached.get("en", ""),
            "model": cached.get("model") or cached.get("zh", ""),
            "spu": cached.get("spu", ""),
        }

    zh = en = model = spu = ""

    # ① 优先：服务端 vehicleNickname
    try:
        veh = (li_api.get_vehicles() or []) if li_api is not None else []
        if veh:
            v = veh[0]
            info = v.get("vehicleInfo") or {}
            spu = info.get("spu") or ""
            zh = (info.get("vehicleNickname")
                  or v.get("modelName")
                  or v.get("seriesName")
                  or "")
            # ② 更具体的版本名（spu 通常含 Pro/Max）
            if spu:
                zh = spu
            model = v.get("modelName") or zh
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("读车辆名失败（将回退）: %s", err)

    # ③ 回退：车型能力表的 desc（如 "L6Pro"）
    if not zh and ability is not None and getattr(ability, "available", False):
        zh = getattr(ability, "desc", "") or ""
        if zh:
            _LOGGER.debug("车辆名回退到能力表 desc: %s", zh)

    # ④ 英文名：从中文名解析系列 + 版本
    if zh:
        series, trim = _split_series_trim(zh)
        if series:
            en = f"{series} {trim}".strip() if trim else series
        else:
            # spu 形如 "L6Pro"（能力表 desc）→ 也尝试拆
            series, trim = _split_series_trim(f"理想{zh}")
            en = f"{series} {trim}".strip() if series else ""

    return {
        "zh": zh or "理想汽车",
        "en": en or "",
        "model": model or zh or "理想汽车",
        "spu": spu,
    }


def build_device_info(coordinator: Any, entry: Any, li_api: Any,
                      ability: Any = None) -> DeviceInfo:
    """构造 DeviceInfo（名字取自服务端，不硬编码车型）。

    参数:
        coordinator: 用于缓存（可选，允许 None）
        entry:       config entry（取 VIN）
        li_api:      LiApiClient（取 vehicleNickname）
        ability:     VehicleAbility（回退用 desc）

    返回:
        DeviceInfo，name = 服务端昵称（如「理想L6 Pro」），
        model = 车型名，sw_version = App 版本（若有）。
    """
    vin = (entry.data.get(CONF_VIN) if entry is not None else "") or ""

    # ★ 优先用 coordinator.data 里缓存的名字（__init__ 已在 executor 里取好）
    cached = cached_vehicle_name(coordinator)
    names = vehicle_names(li_api, ability, cached=cached)
    # ★ 名字策略（与 App 一致）：
    #   name  = 服务端昵称（vehicleNickname / spu）
    #   model = 车型（modelName）
    #   ★ 不再硬编码 "Li Auto L6"
    display = names["zh"]

    identifiers = {(DOMAIN, vin)} if vin else {(DOMAIN, entry.entry_id)}
    dev = DeviceInfo(
        identifiers=identifiers,
        manufacturer="理想汽车",
        model=names["model"],
        name=display,
        # 车牌号作为附加标识（服务端有就给）
        serial_number=vin or None,
    )
    _LOGGER.debug("DeviceInfo: name=%s model=%s vin=%s",
                  display, names["model"], vin)
    return dev


def cached_vehicle_name(coordinator: Any) -> dict | None:
    """从 coordinator 缓存里取车辆名（避免每平台都发请求）。

    由 `coordinator._async_vehicle_name()` 在 executor 里写入
    `data["vehicle_name_info"] = {zh, en, model, spu}`。
    """
    try:
        data = getattr(coordinator, "data", None) or {}
        info = data.get("vehicle_name_info")
        if isinstance(info, dict) and info.get("zh"):
            return info
    except Exception:  # noqa: BLE001
        pass
    return None
