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


class TestDescriptionEquivalence:
    """★ 等价性：从 SIGNALS 生成的 sensor 描述，必须与旧 _mk 表一致。

    这是架构方案 2.4 的关键验证 —— 确保切换零行为变化。
    """

    @staticmethod
    def _old_mk_table():
        """解析 sensor.py 的 _mk 调用。"""
        import re
        from pathlib import Path
        src = (Path(__file__).resolve().parent.parent /
               "custom_components/lixiang_auto/sensor.py").read_text(encoding="utf-8")
        out = {}
        pat = re.compile(r'_mk\(\s*"([^"]+)"\s*,\s*\(([^)]+)\)\s*\)')
        for m in pat.finditer(src):
            key = m.group(1)
            parts = [p.strip().strip("'\"") for p in m.group(2).split(",")]
            parts = [("" if p == "None" else p) for p in parts]
            while len(parts) < 6:
                parts.append("")
            out[key] = dict(name=parts[0], dclass=parts[1], unit=parts[2],
                            sclass=parts[3], icon=parts[4], cat=parts[5])
        return out

    def test_same_key_set(self):
        """★ 新旧表的 key 集合必须一致

        ⚠️ 注意：signals.py 里有几条 platforms 为空（location/ac_on 等），
           它们不是 sensor 实体 —— 但 _mk 表也不需要它们。
           这里比对【会生成实体的】部分。
        """
        import re
        from pathlib import Path
        src = (Path(__file__).resolve().parent.parent /
               "custom_components/lixiang_auto/sensor.py").read_text(encoding="utf-8")
        # _mk 表里被注释掉的（如 window_skylight）不算
        old = set()
        for m in re.finditer(r'_mk\(\s*"([^"]+)"', src):
            # 检查该行是否在注释里
            line_start = src.rfind("\n", 0, m.start()) + 1
            if not src[line_start:m.start()].strip().startswith("#"):
                old.add(m.group(1))
        new = {s.key for s in sg.specs_for("sensor")}
        assert old == new, f"多了: {new - old}\n少了: {old - new}"

    def test_names_match(self):
        old = self._old_mk_table()
        for key, o in old.items():
            s = sg.SIGNALS[key]
            assert o["name"] == s.name, f"{key}: name 旧={o['name']} 新={s.name}"

    def test_icons_match(self):
        old = self._old_mk_table()
        for key, o in old.items():
            s = sg.SIGNALS[key]
            if o["icon"]:
                assert o["icon"] == (s.icon or ""), (
                    f"{key}: icon 旧={o['icon']} 新={s.icon}")

    def test_categories_match(self):
        old = self._old_mk_table()
        for key, o in old.items():
            s = sg.SIGNALS[key]
            if o["cat"]:
                assert o["cat"] == (s.category or ""), (
                    f"{key}: category 旧={o['cat']} 新={s.category}")

    def test_diagnostic_matches(self):
        """★ diagnostic 判定必须一致（影响默认启用与否）

        旧逻辑（sensor.py:98）：
          cat in _DIAGNOSTIC_CATS  OR  key in _DIAGNOSTIC_KEYS
        """
        import re
        from pathlib import Path
        src = (Path(__file__).resolve().parent.parent /
               "custom_components/lixiang_auto/sensor.py").read_text(encoding="utf-8")

        m = re.search(r"_DIAGNOSTIC_KEYS\s*=\s*frozenset\(\{(.*?)\}\)", src, re.S)
        diag_keys = set(re.findall(r'"([^"]+)"', m.group(1))) if m else set()
        m2 = re.search(r"_DIAGNOSTIC_CATS\s*=\s*frozenset\(\{(.*?)\}\)", src, re.S)
        diag_cats = set(re.findall(r'"([^"]+)"', m2.group(1))) if m2 else set()

        assert diag_cats, "未解析到 _DIAGNOSTIC_CATS（测试自身问题）"

        old = self._old_mk_table()
        for key, o in old.items():
            old_diag = (o["cat"] in diag_cats) or (key in diag_keys)
            s = sg.SIGNALS[key]
            assert old_diag == s.diagnostic, (
                f"{key}: diagnostic 旧={old_diag} 新={s.diagnostic}")
