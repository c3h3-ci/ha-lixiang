# 更新日志

本项目遵循[语义化版本](https://semver.org/lang/zh-CN/)。

---

## [Unreleased]

### Added — 🎯 车型能力表（数据驱动，替代手工硬编码）

**背景**：App 能按车型自动匹配功能，我们却在手工一个个找。
根因：App 的能力表来自 **APK 内置的 `assets/{modelId}.json`**。

- **`vehicle_configs/`**（68 个车型，1.1 MB）—— 从官方 APK 8.27.0 提取
  - `temp.config` → 9 种座椅/温控能力（`value`: 1=无硬件，>=2=有）
  - `temp.other` → `vehicleSeat` / `minTemp` / `maxTemp`
  - `version` → 45 种功能开关（`isSupport` + `supportVersion`）
  - `_index.json` / `_names_zh.json` → 索引与中文名
- **`vehicle_ability.py`** —— 完全复刻 App 的 `VehicleDetails` 机制
  - `load_vehicle_config()` = `getVehicleConfig(modelId)`
  - `ability_level()` = `getAbilityLeven(tag)`
  - `vehicle_seat()` = `vehicleSeat()`
  - `is_supported()` = `isSupportCheck(tag, appVer)`
- **`features.py`** —— 能力表接入 + **权威性规则**
  - 优先级：能力表 > variableModel > ConfigCode > VSS 探测
  - 能力表放在最前（VSS 401 时仍可用）

### Fixed
- **L6 被误判为「有三排座椅」** —— VSS 探测无法区分"服务端对不存在硬件
  也返回 value=0 + 有效 ts"，现由能力表权威确定。

### Tests
- 新增 `tests/test_vehicle_ability.py`（35 个）
- 全量 **256** 个测试通过（原 221）

### 实测（L6Pro）
| 项 | 结果 |
|---|---|
| 车型 | L6Pro (L6)，五座，温区 16–28 |
| 有三排座椅 | ❌ |
| 有冰箱 / 侧滑门 / 旋转座椅 / 空气悬架 / 电动尾翼 | ❌ |
| 有座椅加热 / 方向盘加热 / 哨兵 / 远程拍照 / 遮阳帘 | ✅ |

**L8/L9 自动支持三排**（实测 L8Air / L9Max 各生成 2 个三排实体）。

### 收益
- 新车型只需追加 JSON，**无需改代码**
- 不再依赖 VSS 探测猜硬件

## [1.0.0] — 2026-09-25

**首个稳定版。** 从 0.1.0 起的完整功能集：信号读取、车控、首次登录、
错误处理、离线优化，200 个单元测试全绿。

### 新增

- **座椅控制**（`fan` 域，9 个实体）
  主/副驾 + 二排左中右的加热与通风，HA 原生「关闭/低/中/高」档位 UI
- **可开合实体**（`cover` 域，2 个实体）
  尾门 / 全车窗，支持开合 + 位置读回（车窗可拖到任意开度）
- **哨兵开关**（`switch`），带状态读回
- **首次登录：浏览器直连方案**
  HA 配置页直接给出理想官方登录链接（含 `device_id`），
  用户在新窗口完成「滑块 + 短信」验证即可，无需中间页面
- **车控命令**（`button` 5 个）
  寻车 / 授权驾驶 / 闪灯 / 鸣笛 / 远程拍照
- **乐观更新 + TTL**
  下发命令后立即显示目标状态，避免"刚点开就显示关闭"
- **离线跳过**
  车辆离线时只探测 2 个连接字段，跳过全量轮询（省流量、降低风控风险）
- **三档轮询分频**
  HIGH（每轮）/ MID（1 小时）/ LOW（24 小时），可在选项里调主间隔（30~3600 秒）

### 修复

- `_LazySecret` 导致 VIN 获取失败（hac_key/key_id/xdev 被当成空字符串）
- `async_turn_on` 签名与 HA 基类不兼容（`preset_mode` 缺失）→ 座椅完全不可用
- 乐观值被旧 VSS 值立即覆盖 → 切换档位后显示"关闭"
- 二排座椅被误归到 MID 频率（1 小时）→ 控制后长时间显示旧状态
- `maint_engine_level2` 被 `maint_` 前缀逻辑误判为"正常"
- `ota_short` 的 `diagnostic` 与实际注册状态不一致
- 登录页文案含 HTML `<details>` 触发 formatjs `MISSING_VALUE`
- 翻译占位符校验失败（废弃的 sms 步骤残留 `{url}` / `{device}`）
- device_id 为空时未生成随机值 → 首次登录永远"提交不上去"

### 移除

- **充电启停开关**：实测服务端返回 `resultCode=2009`，
  Android 版 App 亦未实现该页面。充电状态仍由 sensor 展示。
- **泊车状态 / 泊车启动进度**：改为诊断类（默认禁用）
  原因：`ParkStatus` 服务端从不返回（永远 unknown）；
  `FSDBootProgress` 值恒为 0 且时间戳停留不动。
  泊车状态在 App 里走【实时事件通道】，VSS 轮询拿不到。
- **冗余按钮 4 个**：开/关尾门、开/关车窗（已由 `cover` 提供）
- **冗余哨兵按钮 2 个**：开启/关闭哨兵（已由 `switch` 提供）
- **重复实体**：`binary_sensor` 哨兵开关（与 `switch` 状态源相同）

### 变更

- `远程启动` → `授权驾驶`（命令 `remoteVehAuth` 的语义更贴切）
- 13 个信号补充中文名与单位（`charge_current_ac` 等）
- 二排中座椅加热补充（`SMSeatHeatState` 存在；无通风信号）

### 已知问题

- 部分信号语义仍在核实（`charge_gun_ac` 等）
- 车控命令下发后车辆状态可能有几十秒延迟（已用乐观更新缓解）
- 多车场景未实现

### ⚠️ 待实车验证

以下 `controlType` 在 App 反编译中未找到，依据同族命名推测：

| 实体 | 推测值 | 依据 |
|---|---|---|
| 二排中座椅加热 | `secMSeatHeatSw` | 状态信号存在 |
| 二排左座椅通风 | `secLSeatVentSw` | 状态信号新鲜 |
| 二排右座椅通风 | `secRSeatVentSw` | 同上 |

---

## [0.11.0] — 2026-09-24

### 新增

- 车型功能探测（15 项能力，按探测结果动态裁剪实体）
- 诊断实体（OTA / 保养 / 激活流程，默认禁用）
- `docs/实体清单.md`、`VERIFY.md`、`ROADMAP.md`

### 修复

- 多平台实体因功能探测失败被全部跳过

---

## [0.10.0] — 2026-09-23

### 新增

- 车窗 `cover`（位置控制）
- 尾门 `cover`
- 座椅 `fan`（主/副驾）

### 修复

- 首次登录流程不再死锁（`require=SMS_CODE` 时进入浏览器辅助）

---

## [0.9.0] — 2026-09-23

### 新增

- 三档轮询分频（HIGH / MID / LOW）
- 信号新鲜度（数据年龄 + 未上报判定）
- 分级错误处理 + HA 持久通知

---

## [0.8.0] — 2026-09-22

### 新增

- 车控通道打通（`x-chj` 签名 + VAT token）
- `button` 平台（寻车 / 远程启动 / 闪灯 / 鸣笛 / 哨兵 / 拍照）

---

## [0.1.0] — 2026-09-21

### 新增

- 初始版本：手机号 + 密码登录、VSS 信号读取、sensor / binary_sensor
