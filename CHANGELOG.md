# Changelog

## 2026-09-26

### fan（座椅加热/通风）
- 列表开关与详情页状态同步：写入 `_attr_percentage` / `_attr_preset_mode`，清理 HA 缓存，详情开/关与列表开关一致
- 特性位对齐 `xiaomi_home`：`__init__` 中 `|=` 写入 `TURN_ON`/`TURN_OFF`，恢复 HA 兼容补位
- `async_turn_on(percentage, preset_mode, **kwargs)` 双位置参数签名
- 未知 preset 不再静默忽略（按 1 档兜底）
- 座椅 fan 按座位分组排序：主驾 → 副驾 → 二排左/中/右

### switch（实体）
- **方向盘加热**：`feature=None`，不再被车型功能探测过滤而丢失
- 开关排序：空调快捷 → 方向盘 → 哨兵

### button
- 按钮排序：寻车/闪灯/鸣笛 → 远程授权 → 远程拍照

### 配置类实体
- `select` 空调控制类型、`number` 空调设定温度 → `EntityCategory.CONFIG`（设备页归入「配置」区）

---

## 2026-09-24 ~ 09-25（已在 PR #2 前序提交）
- 座椅 fan/cover 实体、登录修复、Bemfa 桥接、远端 bugfix 同步等（见 git history）
