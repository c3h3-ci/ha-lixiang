"""设备名生成测试（device.py）—— 2026-09-26 新增

背景 bug：
    12 个平台文件里硬编码 `model="理想 L6"` / `name="Li Auto L6"`，
    导致 L8/L9/MEGA 用户的设备显示成 L6。

修法：
    · 新增 device.py，名字全取自服务端
      （vehicleInfo.spu → vehicleNickname → modelName → 能力表 desc → 兜底）
    · 12 个平台统一调用 build_device_info()
"""
from __future__ import annotations

import types
from pathlib import Path

import pytest

_INTEG = Path(__file__).resolve().parent.parent / "custom_components" / "lixiang_auto"


def _load_device():
    """加载 device.py（绕过 HA 依赖）。"""
    src = (_INTEG / "device.py").read_text(encoding="utf-8")
    src = src.replace(
        "from homeassistant.helpers.device_registry import DeviceInfo",
        "class DeviceInfo(dict):\n"
        "    def __init__(self, **kw):\n"
        "        super().__init__(kw)")
    src = src.replace("from .const import DOMAIN, CONF_VIN, LOGGER_NAME",
                      'DOMAIN = "lixiang_auto"\nCONF_VIN = "vin"\nLOGGER_NAME = "test"')
    mod = types.ModuleType("dev_test")
    exec(compile(src, "device.py", "exec"), mod.__dict__)
    return mod


dev = _load_device()


class TestSeriesTrimSplit:
    """车型名 → (系列, 版本)。"""

    @pytest.mark.parametrize(("raw", "expect"), [
        ("理想L6", "L6"),
        ("理想L6 Pro", "L6 Pro"),
        ("L6Pro", "L6 Pro"),
        ("L9Max车型", "L9 Max"),
        ("L8Air车型", "L8 Air"),
        ("L6Livis26", "L6 Livis"),
        ("W02UItra车型", "W02 Ultra"),
        ("L9UItra26", "L9 Ultra"),
        ("理想MEGA", "MEGA"),
        ("W01_25_home", "W01"),
        ("L9Premium26", "L9 Premium"),
    ])
    def test_split(self, raw, expect):
        s, t = dev._split_series_trim(raw)
        assert f"{s} {t}".strip() == expect

    def test_empty(self):
        assert dev._split_series_trim("") == ("", "")
        assert dev._split_series_trim(None) == ("", "")


class TestVehicleNames:
    """vehicle_names() 的优先级与兜底。"""

    class _Api:
        def __init__(self, payload):
            self._p = payload

        def get_vehicles(self):
            return self._p

    def test_prefers_spu(self):
        api = self._Api([{
            "modelName": "理想L6",
            "vehicleInfo": {"spu": "理想L6 Pro", "vehicleNickname": "理想L6"},
        }])
        n = dev.vehicle_names(api)
        assert n["zh"] == "理想L6 Pro"
        assert n["model"] == "理想L6"

    def test_falls_back_to_nickname(self):
        api = self._Api([{
            "modelName": "理想L9",
            "vehicleInfo": {"vehicleNickname": "我的大九"},
        }])
        n = dev.vehicle_names(api)
        assert n["zh"] == "我的大九"

    def test_falls_back_to_model_name(self):
        api = self._Api([{"modelName": "理想L8", "vehicleInfo": {}}])
        assert dev.vehicle_names(api)["zh"] == "理想L8"

    def test_cached_short_circuits(self):
        """有缓存时不请求网络。"""
        class Boom:
            def get_vehicles(self):
                raise AssertionError("不该请求网络")
        n = dev.vehicle_names(Boom(), cached={"zh": "理想L7 Max", "en": "L7 Max",
                                              "model": "理想L7", "spu": ""})
        assert n["zh"] == "理想L7 Max"

    def test_api_error_falls_back(self):
        class Bad:
            def get_vehicles(self):
                raise RuntimeError("network down")
        n = dev.vehicle_names(Bad())
        assert n["zh"] == "理想汽车"        # 兜底

    def test_none_api(self):
        assert dev.vehicle_names(None)["zh"] == "理想汽车"


class TestNoHardcodedModelName:
    """★ 守卫：不得再硬编码车型名。"""

    PLATFORMS = ['binary_sensor', 'button', 'climate', 'cover', 'fan', 'lock',
                 'notify', 'number', 'select', 'sensor', 'switch', 'time']

    @staticmethod
    def _code_lines(path: Path) -> str:
        """只保留代码行（去掉注释与 docstring 里的示例文本）。"""
        out = []
        in_doc = False
        for line in path.read_text(encoding="utf-8").split("\n"):
            st = line.strip()
            # 三引号 docstring 开关
            n3 = st.count('"""')
            if n3 == 1:
                in_doc = not in_doc
                continue
            if in_doc or st.startswith("#"):
                continue
            # 行内注释
            if "#" in line and not line.lstrip().startswith(("'", '"')):
                line = line.split("#", 1)[0]
            out.append(line)
        return "\n".join(out)

    @pytest.mark.parametrize("name", PLATFORMS)
    def test_platform_has_no_hardcoded_model(self, name):
        code = self._code_lines(_INTEG / f"{name}.py")
        for bad in ('model="理想 L6"', 'name="Li Auto L6"',
                    '"理想 L6"', '"Li Auto L6"', 'model="理想L6"'):
            assert bad not in code, f"{name}.py 代码里仍硬编码 {bad}"

    @pytest.mark.parametrize("name", PLATFORMS)
    def test_platform_uses_build_device_info(self, name):
        s = (_INTEG / f"{name}.py").read_text(encoding="utf-8")
        assert "build_device_info(" in s, f"{name}.py 未用统一构造"
        # ★ 不得使用未定义的裸 coordinator（曾导致 9 个平台 setup 失败）
        assert "        coordinator, config_entry," not in s or (
            "coordinator = hass.data" in s or "coordinator = data.get" in s
        ), f"{name}.py 可能引用了未定义的 coordinator"

    def test_device_module_has_no_hardcoded_brand_model(self):
        """device.py 代码里不得出现具体车型（注释示例不算）。"""
        code = self._code_lines(_INTEG / "device.py")
        for bad in ('"理想 L6"', '"理想L6"', '"Li Auto L6"'):
            assert bad not in code, f"device.py 代码里硬编码了 {bad}"
        # 兜底值只能是品牌名
        assert '"理想汽车"' in code, "device.py 应有品牌兜底值"


class TestBuildDeviceInfo:
    def test_builds_with_vin(self):
        class Api:
            def get_vehicles(self):
                return [{"modelName": "理想L6",
                         "vehicleInfo": {"spu": "理想L6 Pro"}}]

        class Entry:
            entry_id = "e1"
            data = {"vin": "TESTVIN0000000001"}

        di = dev.build_device_info(None, Entry(), Api())
        assert di["name"] == "理想L6 Pro"
        assert di["model"] == "理想L6"
        assert di["manufacturer"] == "理想汽车"

    def test_builds_without_vin(self):
        class Entry:
            entry_id = "e1"
            data = {}

        di = dev.build_device_info(None, Entry(), None)
        assert di["name"] == "理想汽车"
