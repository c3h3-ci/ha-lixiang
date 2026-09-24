"""fan.py 测试：座椅加热/通风实体

★ 背景（2026-09-24 用户报告"加热出错"）：
  HA 的 FanEntity 内部调用约定是【位置参数】：
    homeassistant/components/fan/__init__.py:315
      await self.async_turn_on(percentage, preset_mode, **kwargs)

  原实现只有 (percentage, **kwargs) → TypeError:
    "LiCarSeatFan.async_turn_on() takes from 1 to 2 positional
     arguments but 3 were given"

  本测试确保签名与 HA 基类一致，避免再次踩坑。
"""

from __future__ import annotations

import ast
import inspect
import re
import sys
import types
from pathlib import Path

import pytest

INTEG = Path(__file__).resolve().parent.parent / "custom_components" / "lixiang_auto"


def _src(filename: str) -> str:
    return (INTEG / filename).read_text(encoding="utf-8")


class TestFanSignatures:
    """★ fan 实体的方法签名必须与 HA 基类兼容"""

    def test_async_turn_on_has_preset_mode_positional(self):
        """★ async_turn_on 必须有 preset_mode 位置参数

        HA 内部调用：async_turn_on(percentage, preset_mode, **kwargs)
        缺少 preset_mode → TypeError（线上踩过的坑）
        """
        src = _src("fan.py")
        m = re.search(
            r"async def async_turn_on\s*\((.*?)\)\s*->", src, re.S)
        assert m, "未找到 async_turn_on"
        params = m.group(1)
        assert "percentage" in params, "缺少 percentage 参数"
        assert "preset_mode" in params, (
            "★ async_turn_on 缺少 preset_mode 位置参数 —— "
            "HA 会传 (percentage, preset_mode) 两个位置参数，会 TypeError！")

    def test_async_turn_off_accepts_kwargs(self):
        """async_turn_off 必须接受 **kwargs"""
        src = _src("fan.py")
        m = re.search(r"async def async_turn_off\s*\((.*?)\)\s*->", src, re.S)
        assert m, "未找到 async_turn_off"
        assert "kwargs" in m.group(1), "async_turn_off 应接受 **kwargs"

    def test_async_set_percentage_exists(self):
        """set_percentage 必须存在（HA 依赖它）"""
        src = _src("fan.py")
        assert re.search(r"async def async_set_percentage\s*\(", src), \
            "缺少 async_set_percentage"

    def test_signature_matches_ha_base(self):
        """★ 与 HA 基类签名对比（模拟 HA 的调用方式）

        HA 基类（fan/__init__.py:318）：
          async def async_turn_on(self, percentage=None, preset_mode=None, **kwargs)
        """
        src = _src("fan.py")
        m = re.search(
            r"async def async_turn_on\s*\((.*?)\)\s*->", src, re.S)
        params = m.group(1)
        # 模拟 HA 调用：func(self, 100, "high")
        # 两个位置参数必须都能接收
        positional = [
            p.strip().split(":")[0].split("=")[0].strip()
            for p in params.split(",")
            if p.strip() and "**" not in p
        ]
        assert len(positional) >= 3, (
            f"async_turn_on 至少需要 3 个位置参数（self + 2），实际 {positional}")


class TestFanEntityTable:
    """SEAT_FANS 表完整性"""

    @staticmethod
    def _fans() -> list[tuple]:
        src = _src("fan.py")
        m = re.search(r"SEAT_FANS = \((.*?)\n\)", src, re.S)
        assert m, "未找到 SEAT_FANS"
        return re.findall(
            r'\("([^"]+)",\s*"([^"]+)",\s*"([^"]+)",\s*"([^"]+)",\s*"([^"]+)"',
            m.group(1))

    def test_has_nine_seats(self):
        """★ L6 应有 9 个座椅 fan（主副驾 + 二排左中右）"""
        fans = self._fans()
        assert len(fans) == 9, f"应有 9 个，实际 {len(fans)}: {[f[0] for f in fans]}"

    def test_second_row_has_middle_heat(self):
        """★ 二排中座椅加热（用户实测确认存在）"""
        keys = {f[0] for f in self._fans()}
        assert "seat_sm_heat" in keys, "缺少二排中座椅加热"

    def test_no_second_row_middle_vent(self):
        """★ 二排中【无】通风（SMSeatVentilationState 信号不存在）"""
        keys = {f[0] for f in self._fans()}
        assert "seat_sm_vent" not in keys, (
            "不该有 SMSeatVentilationState —— 该信号不存在")

    def test_control_types_match_app(self):
        """controlType 命名规则"""
        fans = self._fans()
        known = {
            "seat_fl_heat": "flSeatHeatSw",
            "seat_fr_heat": "frSeatHeatSw",
            "seat_fl_vent": "flSeatVentSw",
            "seat_fr_vent": "frSeatVentSw",
            "seat_sl_heat": "secLSeatHeatSw",
            "seat_sr_heat": "secRSeatHeatSw",
        }
        by_key = {f[0]: f[4] for f in fans}
        for key, ctrl in known.items():
            assert by_key.get(key) == ctrl, (
                f"{key} 的 controlType 应为 {ctrl}，实际 {by_key.get(key)}")
