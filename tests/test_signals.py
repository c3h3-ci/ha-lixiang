"""signals.py 测试：声明式信号表

★ 架构方案阶段 2.1/2.2 的验证：
  确保 SIGNALS 与旧的分散定义（const/sensor/binary_sensor/coordinator）一致。
"""

from __future__ import annotations

import pytest

import signals as sg


class TestSignalTable:
    def test_not_empty(self):
        assert len(sg.SIGNALS) > 100, "信号表应有 100+ 条"

    def test_all_have_key_path_name(self):
        for key, spec in sg.SIGNALS.items():
            assert spec.key == key, f"{key}: key 字段与字典键不一致"
            assert spec.path.startswith("Vehicle."), f"{key}: path 格式错误 {spec.path}"
            assert spec.name, f"{key}: 缺 name"

    def test_paths_unique(self):
        """同一 VSS 路径不应被两个 key 复用（除兼容项）"""
        seen: dict[str, str] = {}
        dups = []
        for key, spec in sg.SIGNALS.items():
            if spec.path in seen and "old" not in key:
                dups.append((key, seen[spec.path], spec.path))
            seen[spec.path] = key
        assert not dups, f"重复路径: {dups}"

    def test_platforms_valid(self):
        valid = {"sensor", "binary_sensor", "switch", "number", "select",
                 "button", "climate", "lock", "device_tracker", "notify"}
        for key, spec in sg.SIGNALS.items():
            bad = spec.platforms - valid
            assert not bad, f"{key}: 非法平台 {bad}"


class TestQueries:
    def test_specs_for_sensor(self):
        ss = sg.specs_for("sensor")
        assert len(ss) > 50
        assert all("sensor" in s.platforms for s in ss)

    def test_specs_for_binary(self):
        bs = sg.specs_for("binary_sensor")
        assert len(bs) > 20
        assert all("binary_sensor" in s.platforms for s in bs)

    def test_specs_for_unknown_platform(self):
        assert sg.specs_for("nonexistent") == []

    def test_by_freq(self):
        hi = sg.by_freq(sg.Freq.HIGH)
        mid = sg.by_freq(sg.Freq.MID)
        low = sg.by_freq(sg.Freq.LOW)
        assert len(hi) + len(mid) + len(low) == len(sg.SIGNALS)

    def test_paths_for(self):
        all_paths = sg.paths_for()
        hi_paths = sg.paths_for(sg.Freq.HIGH)
        assert len(all_paths) == len(sg.SIGNALS)
        assert len(hi_paths) < len(all_paths)

    def test_path_of(self):
        assert sg.path_of("battery_level") == "Vehicle.Powertrain.Battery.ResidueBattery"

    def test_path_of_unknown(self):
        assert sg.path_of("nonexistent_key") == ""

    def test_compat_vss_paths(self):
        """兼容字典应与 SIGNALS 一致"""
        assert len(sg.VSS_PATHS_COMPAT) == len(sg.SIGNALS)
        assert sg.VSS_PATHS_COMPAT["battery_level"] == sg.path_of("battery_level")


class TestKnownSignals:
    """关键信号的语义应正确（这些是踩过坑的）"""

    def test_battery_level(self):
        s = sg.SIGNALS["battery_level"]
        assert s.path == "Vehicle.Powertrain.Battery.ResidueBattery"
        assert s.unit == "PERCENTAGE"
        assert s.device_class == "BATTERY"

    def test_door_trunk_semantics(self):
        """★ 尾门：==1 才开（曾用 n!=0 导致 2 被误判）"""
        s = sg.SIGNALS["door_trunk"]
        assert s.semantics == sg.Semantics.DOOR_OPEN
        assert "binary_sensor" in s.platforms

    def test_charge_port_lid_uses_v2(self):
        """★ 充电口盖用 V2（旧版恒为 1，无效）"""
        s = sg.SIGNALS["charge_port_lid"]
        assert s.path.endswith("ChrgPorLidStsV2")
        assert s.semantics == sg.Semantics.CHARGE_LID

    def test_ac_on_uses_foofstatus(self):
        """★ 空调开关用 FOffStatus（ExSpeedStatus 是快冷快热）"""
        s = sg.SIGNALS["ac_on"]
        assert s.path.endswith("FOffStatus")

    def test_low_freq_signals(self):
        """OTA/配置类应是低频"""
        assert sg.SIGNALS["config_code"].freq == sg.Freq.LOW
        assert sg.SIGNALS["ota_version"].freq == sg.Freq.LOW


class TestFreqEquivalence:
    """★ 等价性验证：spec.freq 的分组必须与旧的前缀规则一致。

    这是架构方案建议的关键测试 —— 确保 coordinator 切换零行为变化。
    """

    @staticmethod
    def _old_grouping(vss_paths, mid_prefixes, low_prefixes):
        hi, mid, lo = set(), set(), set()
        for k, p in vss_paths.items():
            if any(k.startswith(pre) for pre in low_prefixes):
                lo.add(p)
            elif any(k.startswith(pre) for pre in mid_prefixes):
                mid.add(p)
            else:
                hi.add(p)
        return hi, mid, lo

    def test_grouping_matches_prefix_rules(self):
        """用真实的旧前缀规则验证分组一致"""
        import re
        from pathlib import Path

        # 从 coordinator.py 读真实前缀（若文件不可用则跳过）
        coord = Path(__file__).resolve().parent.parent / (
            "custom_components/lixiang_auto/coordinator.py")
        if not coord.exists():
            pytest.skip("coordinator.py 不可用")

        src = coord.read_text(encoding="utf-8")
        MID = tuple(re.findall(r'"([^"]+)"', re.search(
            r"MID_FREQ_PREFIXES\s*=\s*\((.*?)\)", src, re.S).group(1)))
        LOW = tuple(re.findall(r'"([^"]+)"', re.search(
            r"LOW_FREQ_PREFIXES\s*=\s*\((.*?)\)", src, re.S).group(1)))

        # 从 const.py 读 VSS_PATHS（旧的主键表）
        const = Path(__file__).resolve().parent.parent / (
            "custom_components/lixiang_auto/const.py")
        import ast
        tree = ast.parse(const.read_text(encoding="utf-8"))
        vss = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == "VSS_PATHS":
                        vss = ast.literal_eval(node.value)

        hi_old, mid_old, lo_old = self._old_grouping(vss, MID, LOW)
        hi_new = {s.path for s in sg.by_freq(sg.Freq.HIGH)}
        mid_new = {s.path for s in sg.by_freq(sg.Freq.MID)}
        lo_new = {s.path for s in sg.by_freq(sg.Freq.LOW)}

        assert hi_new == hi_old, f"HIGH 分组不一致: {hi_new ^ hi_old}"
        assert mid_new == mid_old, f"MID 分组不一致: {mid_new ^ mid_old}"
        assert lo_new == lo_old, f"LOW 分组不一致: {lo_new ^ lo_old}"

    def test_all_vss_paths_covered(self):
        """★ signals.py 必须覆盖 const.py 的所有路径（否则轮询会漏）"""
        import ast
        from pathlib import Path

        const = Path(__file__).resolve().parent.parent / (
            "custom_components/lixiang_auto/const.py")
        tree = ast.parse(const.read_text(encoding="utf-8"))
        vss = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == "VSS_PATHS":
                        vss = ast.literal_eval(node.value)

        covered = {s.path for s in sg.SIGNALS.values()}
        missing = set(vss.values()) - covered
        assert not missing, f"signals.py 未覆盖 {len(missing)} 条路径: {list(missing)[:5]}"
