# 更新日志

本项目遵循[语义化版本](https://semver.org/lang/zh-CN/)。

---

## [1.1.0] — 2026-09-26

### Added — 🎯 车型能力表 / 配置表 / 多车支持（2026-09-26 大批量改进）

#### 车型能力表（数据驱动）
- **`vehicle_configs/`**（68 个车型 JSON）—— 从官方 APK 提取
  - `temp.config` → 9 种座椅/温控能力（`value`: 1=无，>=2=有）
  - `version` → 45 种功能开关（`isSupport` + `supportVersion`）
- **`vehicle_ability.py`** —— 复刻 App 的 `VehicleDetails` 机制
  - `ability_level()` / `vehicle_seat()` / `is_supported()` / `app_name()`
- **L8/L9 三排座椅自动支持**（L6 五座自动不建三排）

#### App 配置表（权威来源）
- **`app_config/sub_token_data.json`**（40 个 token 配置）
  - 每个接口的 type/audience/scope/urls
- **`app_config.py`** —— `audience_for(path)` 等反查 API

#### 多车账号支持
- **config entry title** = 账号级（`Li Auto (1820)`）
- **device name** = 车辆级（`理想L6 Pro`）
  - 用户自定义昵称优先
  - 同款多辆时加车牌 / VIN 尾号区分
- **按 VIN 精确匹配**（不再盲取第一辆）

#### 诊断
- **`lixiang_auto.dump_ability`** 服务（导出车型能力表 JSON）

### Fixed
- **设备名硬编码「理想 L6」** —— L8/L9 用户会看到错误车型（严重）
- **低频信号首次不拉取** —— 23 个实体长期 unknown
  （`need_low = (now - 0.0) > 24h` 在进程启动 <24h 时恒 False）
- **VAT scope 多请求导致整批降级** —— 14 个自拼 → 只给 8 个
  （改为 App 的精确 12 个 → 全给）
- **L6 被误判为「有三排座椅」** —— VSS 探测无法区分，改由能力表权威确定
- **充电控制静默失败** —— 现在给出明确提示（LiNdn 通道限制）
- **实体名对齐 App** —— 「车门锁」→「车锁」

### Tests
- 从 **221** 增至 **461** 个测试
- 新增：`test_vehicle_ability.py` / `test_device_names.py` /
  `test_app_config.py` / `test_charge_channel.py` /
  `test_no_hardcoded.py` / `test_freq_first_poll.py`

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
