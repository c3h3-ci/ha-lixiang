"""render_value() 纯函数测试

★ 这是架构方案 T0 的核心：
  把 sensor.py 的 29 处 `if key ==` 分支变成可验证的纯函数。

覆盖：
  1. 无数据场景（None / 缺失）
  2. 各特殊信号的渲染
  3. 门/窗/锁的语义（历史踩坑点）
  4. 通用兜底（长 JSON 截断 / 类型直返）
"""

from __future__ import annotations

import json

import pytest

from rendering import STATE_UNKNOWN, render_value


# ───────────────────────────────────────────────────────────────────────────
# 1. 基础：无数据
# ───────────────────────────────────────────────────────────────────────────
class TestEmpty:
    @pytest.mark.parametrize("key", [
        "battery_level", "charge_status", "door_main", "window_main",
        "ac_set_temp", "tire_fl_pressure", "location", "sentry",
    ])
    def test_none_value_returns_none(self, key):
        """值为 None → 返回 None（让 sticky 包装器回退上次有效值）"""
        assert render_value(key, None, None, {}) is None

    def test_missing_sig_returns_none(self):
        assert render_value("battery_level", None, None, None) is None


# ───────────────────────────────────────────────────────────────────────────
# 2. online_status（非 VSS 来源，读 data["vehicle_status"]）
# ───────────────────────────────────────────────────────────────────────────
class TestOnlineStatus:
    def test_online(self):
        assert render_value("online_status", None, None, {"vehicle_status": 1}) == "在线"

    def test_offline(self):
        assert render_value("online_status", None, None, {"vehicle_status": 0}) == "离线"

    def test_missing(self):
        assert render_value("online_status", None, None, {}) == STATE_UNKNOWN


# ───────────────────────────────────────────────────────────────────────────
# 3. location（JSON → "lat,lon"）
# ───────────────────────────────────────────────────────────────────────────
class TestLocation:
    def test_valid_json(self):
        raw = json.dumps({"lat": 28.014583, "lon": 120.678253})
        assert render_value("location", raw, {"value": raw}, {}) == "28.01458,120.67825"

    def test_invalid_json(self):
        assert render_value("location", "not-json", {"value": "not-json"}, {}) == STATE_UNKNOWN


# ───────────────────────────────────────────────────────────────────────────
# 4. 空调设定温度（数值直返）
# ───────────────────────────────────────────────────────────────────────────
class TestAcSetTemp:
    @pytest.mark.parametrize("val,expected", [
        (22.5, 22.5),
        (26, 26),
        (0, 0),          # 0 是合法温度下限边界（不过滤）
    ])
    def test_numeric(self, val, expected):
        assert render_value("ac_set_temp", val, {"value": val}, {}) == expected


# ───────────────────────────────────────────────────────────────────────────
# 5. 通用兜底
# ───────────────────────────────────────────────────────────────────────────
class TestGeneric:
    def test_short_string_passthrough(self):
        assert render_value("some_key", "abc", {"value": "abc"}, {}) == "abc"

    def test_long_string_truncated(self):
        long = "x" * 300
        r = render_value("some_key", long, {"value": long}, {})
        assert len(r) == 250
        assert r.endswith("...")

    def test_dict_serialized(self):
        v = {"a": 1, "b": 2}
        r = render_value("some_key", v, {"value": v}, {})
        assert json.loads(r) == v

    def test_int_passthrough(self):
        assert render_value("some_key", 42, {"value": 42}, {}) == 42

    def test_zero_not_treated_as_none(self):
        """★ 0 是合法值，不能被当成缺失"""
        assert render_value("some_key", 0, {"value": 0}, {}) == 0


# ───────────────────────────────────────────────────────────────────────────
# 6. ChargeStatus（复刻 App 归一化函数）
# ───────────────────────────────────────────────────────────────────────────
class TestChargeStatus:
    def _data(self, **kw):
        """构造带 vss 的 coordinator.data。"""
        return {"vss": {k: {"value": v} for k, v in kw.items()}}

    @pytest.mark.parametrize("cs,expected", [
        (3, "充电中"),
        (2, "电池加热"),
        (4, "电池保温"),
        (7, "充电告警"),
    ])
    def test_simple_states(self, cs, expected):
        d = self._data(charge_status=cs)
        assert render_value("charge_status", cs, {"value": cs}, d) == expected

    def test_charge_complete(self):
        d = self._data(charge_status=5, charge_complete=1)
        assert render_value("charge_status", 5, {"value": 5}, d) == "充电完成"

    def test_charge_stopped(self):
        d = self._data(charge_status=5, charge_complete=0)
        assert render_value("charge_status", 5, {"value": 5}, d) == "已停止"

    def test_charge_alarm(self):
        d = self._data(charge_status=5, charge_complete=0, charge_fault=1)
        assert render_value("charge_status", 5, {"value": 5}, d) == "充电告警"

    def test_appointed_charge(self):
        """预约充电：三条件同时满足"""
        d = self._data(scheduled_charge_switch=1,
                       charge_gun_ac=2,
                       scheduled_charge_state=1,
                       charge_status=0)
        assert render_value("charge_status", 0, {"value": 0}, d) == "预约充电"

    def test_unknown_code_falls_back(self):
        """App 分支外的值 → DEFAULT"""
        d = self._data(charge_status=15)
        assert render_value("charge_status", 15, {"value": 15}, d) == "—"


# ───────────────────────────────────────────────────────────────────────────
# 7. 回归测试：记录已知的语义决定
# ───────────────────────────────────────────────────────────────────────────
class TestRegressions:
    def test_door_semantics_documented(self):
        """★ 门语义：1=打开（源码依据 XDoorDataHandle.smali:310）

        这个测试不测 render_value（门由 binary_sensor 处理），
        而是作为【文档化断言】提醒后来者：
          - DoorSwitchStatus.*  用 == 1 判打开
          - DoorLockStatus.*    用 != 0 判未落锁
        """
        opened, closed = 1, 2
        assert (opened == 1) is True, "1 表示打开"
        assert (closed == 1) is False, "2 表示关闭（历史 bug：曾用 n != 0）"

    def test_zero_is_valid_value(self):
        """★ 0 不等于缺失（历史 bug：曾把 0 当 None）"""
        assert render_value("charge_limit", 0, {"value": 0}, {}) == 0


# ───────────────────────────────────────────────────────────────────────────
# 8. 回归：确保 translate() 被真正调用
# ───────────────────────────────────────────────────────────────────────────
class TestTranslateWired:
    """★ 2026-09-23 bug：抽 rendering.py 时漏了 import，
    导致 translate() 从未被调用，值永远是裸数字。

    这组测试确保「翻译管线是接通的」。
    """

    def test_vss_paths_imported(self):
        """VSS_PATHS 必须可用（否则不会触发翻译）"""
        import rendering
        assert hasattr(rendering, "VSS_PATHS")
        assert len(rendering.VSS_PATHS) > 50, "VSS_PATHS 应包含全部信号路径"

    def test_translate_imported(self):
        import rendering
        assert hasattr(rendering, "translate")
        assert callable(rendering.translate)

    def test_raw_number_is_translated(self):
        """有翻译映射的信号，裸数字应变成中文"""
        # LowVolPwrMdSts: {0: "正常", 1: "低压模式"}
        d = {}
        r = render_value("low_vol_status", 0, {"value": 0}, d)
        assert r == "正常", f"应翻译为「正常」，实际 {r!r}"

    def test_untranslated_passthrough(self):
        """无翻译映射的信号，原值透传"""
        r = render_value("battery_level", 55, {"value": 55}, {})
        assert r == 55
