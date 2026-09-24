"""乐观更新（optimistic state）测试

★ 背景（2026-09-24 用户报告）：
  "座椅加热开关状态显示有问题，比如打开开关默认3档，
   在其他地方切换成1档就显示关闭了。"

根因：原逻辑是【VSS 优先】，但车机上报状态有延迟：
  发命令 → 乐观值=3 → 立刻拉 VSS（还是旧值 0）→ 显示「关闭」

修复：乐观更新带 TTL（OPTIMISTIC_TTL = 45 秒）：
  ① TTL 内且 VSS 与乐观值不一致 → 用乐观值（保持显示）
  ② VSS 追上乐观值 → 清除乐观值，用 VSS
  ③ 超过 TTL → 无条件用 VSS（以服务端为准）

本测试确保各平台都实现了该机制，避免回归。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

INTEG = Path(__file__).resolve().parent.parent / "custom_components" / "lixiang_auto"

# 需要 TTL 乐观机制的平台
PLATFORMS = ["fan", "switch", "number", "cover", "climate"]


def _src(name: str) -> str:
    return (INTEG / f"{name}.py").read_text(encoding="utf-8")


class TestOptimisticTTL:
    """★ 各平台的乐观更新必须带 TTL"""

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_has_ttl_constant(self, platform: str):
        """必须有 OPTIMISTIC_TTL 常量"""
        src = _src(platform)
        assert "OPTIMISTIC_TTL" in src, (
            f"{platform}.py 缺少 OPTIMISTIC_TTL 常量 —— "
            "乐观更新会立刻被旧 VSS 值覆盖")

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_has_optimistic_until_field(self, platform: str):
        """必须有 _optimistic_until 时间戳字段"""
        src = _src(platform)
        assert "_optimistic_until" in src, (
            f"{platform}.py 缺少 _optimistic_until 字段")

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_checks_ttl_before_using_vss(self, platform: str):
        """必须在用 VSS 之前检查 TTL"""
        src = _src(platform)
        assert re.search(r"monotonic\(\)\s*<\s*self\._optimistic_until", src), (
            f"{platform}.py 没有 TTL 检查逻辑（`monotonic() < "
            "self._optimistic_until`）")

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_sets_timestamp_on_send(self, platform: str):
        """发命令时必须记录时间戳"""
        src = _src(platform)
        # 至少有一处 _optimistic_until = ... + OPTIMISTIC_TTL
        assert re.search(
            r"self\._optimistic_until\s*=\s*\w+\.monotonic\(\)\s*\+\s*OPTIMISTIC_TTL",
            src), f"{platform}.py 发命令时没有记录乐观值时间戳"


class TestFanLevelLogic:
    """★ 座椅 fan 的档位逻辑（用户报告的场景）"""

    def test_current_level_prefers_optimistic_in_ttl(self):
        """★ TTL 内，VSS 与乐观值不一致时应用乐观值

        场景：打开开关设 3 档 → VSS 还是 0
              → 应显示 3 档（不是"关闭"）
        """
        src = _src("fan")
        m = re.search(r"def current_level.*?(?=@property)", src, re.S)
        assert m, "未找到 current_level"
        body = m.group(0)
        # 必须包含 TTL 检查 + 不一致时返回乐观值
        assert "monotonic() < self._optimistic_until" in body, \
            "current_level 缺少 TTL 检查"
        assert "return self._optimistic_level" in body, \
            "current_level 未返回乐观值"

    def test_is_on_derived_from_level(self):
        """is_on 必须由 current_level 派生（>0 为开）"""
        src = _src("fan")
        m = re.search(r"def is_on.*?(?=@property|\Z)", src, re.S)
        assert m, "未找到 is_on"
        assert "current_level" in m.group(0), \
            "fan.is_on 应基于 current_level（档位>0 才算开）"

    def test_percentage_maps_level(self):
        """percentage 必须是 level 的映射"""
        src = _src("fan")
        assert "_level_to_percent(self.current_level)" in src, \
            "percentage 应基于 current_level 映射"


class TestSwitchOptimistic:
    """★ switch 的乐观状态"""

    def test_is_on_uses_ttl(self):
        src = _src("switch")
        m = re.search(r"def is_on.*?(?=@property|\Z)", src, re.S)
        assert m, "未找到 is_on"
        body = m.group(0)
        assert "monotonic() < self._optimistic_until" in body, \
            "switch.is_on 缺少 TTL 检查"
        assert "return self._optimistic_on" in body, \
            "switch.is_on 未返回乐观值"


class TestCoverOptimistic:
    """★ cover 的乐观状态（尾门 + 车窗）"""

    def test_trunk_uses_ttl(self):
        src = _src("cover")
        # 尾门的 is_closed（用行首 class 定位，避免注释里的 "class " 干扰）
        m = re.search(r"^class LiCarTrunkCover\b.*?(?=^class )", src,
                      re.S | re.M)
        assert m, "未找到 LiCarTrunkCover"
        assert "monotonic() < self._optimistic_until" in m.group(0), \
            "尾门 is_closed 缺少 TTL 检查"

    def test_window_uses_ttl(self):
        src = _src("cover")
        m = re.search(r"^class LiCarWindowCover\b.*", src, re.S | re.M)
        assert m, "未找到 LiCarWindowCover"
        assert "monotonic() < self._optimistic_until" in m.group(0), \
            "车窗 current_cover_position 缺少 TTL 检查"


class TestTtlValue:
    """TTL 值合理"""

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_ttl_reasonable(self, platform: str):
        """TTL 应在 20~120 秒之间

        太短：VSS 还没追上就失效 → 显示回退
        太长：服务端真实状态被掩盖过久
        """
        src = _src(platform)
        m = re.search(r"OPTIMISTIC_TTL\s*=\s*([\d.]+)", src)
        assert m, f"{platform}.py 未找到 OPTIMISTIC_TTL 定义"
        val = float(m.group(1))
        assert 20 <= val <= 120, (
            f"{platform}.py 的 OPTIMISTIC_TTL={val} 不合理（建议 30~60）")
