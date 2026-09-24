# 更新日志 — Li Auto (lixiang_auto)

## [0.9.9] — 2026-09-24

### 座椅加热/通风改为风扇（fan）实体

| 变更 | 说明 |
|------|------|
| **新增 `fan.py`** | 主驾/副驾加热、通风改为 HA **fan 域**：关闭 / 低 / 中 / 高（与图中风扇 UI 一致）。 |
| **ImportError 修复** | 本机 HA 的 `homeassistant.components.fan` **没有** `percentage_to_ordered_list_item` / `ordered_list_item_to_percentage`；已去掉这两个导入，改用本地 0/33/66/100 映射。 |
| **去掉座椅 switch + number 档位** | 档位并入 fan；`switch` 仅剩方向盘+寻车，`number` 仅剩空调温度。 |
| **巴法/小爱** | 优先找 `fan.*`；主题仍用 **003**，`on`/`off`/`on#1-3` 映射 fan 开关与档位。 |
| **默认高档** | 打开默认 **3 档（高）**。 |

实体 ID 形如：`fan.主驾座椅加热`、`fan.副驾座椅通风`。

巴法映射示例（选项）：

```text
zjzr003=seat_fl_heat,fzjzr003=seat_fr_heat,zjzt003=seat_fl_vent,fzjzt003=seat_fr_vent
```

涉及：`fan.py`、`switch.py`、`number.py`、`bemfa.py`、`__init__.py` → **0.9.9**

---

## [0.9.8] — 2026-09-24

### 巴法座椅档位 → 风扇协议（003）

| 变更 | 说明 |
|------|------|
| **主题后缀支持 003** | 座椅加热/通风在巴法控制台建 **风扇** 主题（后缀 `003`），可语音「二档」等。 |
| **指令映射** | `on` → 打开（默认 3 档）；`off` → 关闭；`on#1`/`on#2`/`on#3` → 1/2/3 档；`on#4` → 钳到 3 档。裸 `1`/`2`/`3` 兼容。 |
| **状态上报** | 有档时推 `on#N`（与风扇一致），便于小爱/巴法显示档位。 |
| **009 窗帘** | 仍兼容百分比 `on#N`→1/2/3 档；**006 仅开关**。 |

选项映射示例：

```text
zjzr003=seat_fl_heat,fzjzr003=seat_fr_heat,zjzt003=seat_fl_vent,fzjzt003=seat_fr_vent
```

涉及：`bemfa.py`、`config_flow.py`、`strings.json`、`zh-Hans.json`、`manifest.json` → **0.9.8**

---

## [0.9.7] — 2026-09-24

### 座椅默认 3 档 + 巴法关闭/调档

| 变更 | 说明 |
|------|------|
| **默认 3 档** | 主驾/副驾加热、通风「打开」固定发 **LEVEL3**。 |
| **巴法关闭失效** | ① 指令去重改为只看已执行的 `last_cmd`（不再用状态 `last_pub` 吞掉 off）；② 收到指令后 **12 秒暂停状态 /up 回写**，避免状态覆盖未读指令；③ off **直接调实体 `async_turn_off`**，并同步档位 number→0。 |
| **巴法调档** | 支持 `on#1` / `on#2` / `on#3`；009 窗帘式百分比 `on#N`（4-100 映射 1-3 档）。经 `async_set_level` + number 实体下发。主题后缀可为 **006/001/009**。 |

巴法开关主题示例（选项）：

```text
zjzr006=seat_fl_heat,fzjzr006=seat_fr_heat,zjzt006=seat_fl_vent,fzjzt006=seat_fr_vent
```

若要滑条调档，可用 **009** 窗帘主题：`zjzr009=seat_fl_heat,...`

涉及：`switch.py`、`bemfa.py`、`manifest.json` → **0.9.7**

---

## [0.9.6] — 2026-09-24

### 主副驾座椅开关回退

| 变更 | 说明 |
|------|------|
| **回退开关逻辑** | 去掉命令 Lock、强制关窗口、延迟补刷等复杂状态；恢复最初：打开→`LEVEL1`，关闭→`OFF`，状态读 VSS。 |
| **保留三档** | `number` 档位 0–3 仍在，可设 1/2/3 档并显示当前档。 |
| **关闭不生效** | 复杂串行/延迟刷新可能导致关闭命令被挡住或 UI 不更新；回退后关闭直接发 `OFF` 并立刻刷新。 |

涉及：`switch.py`、`number.py`、`manifest.json` → **0.9.6**

---

## [0.9.5] — 2026-09-24

### 座椅实体与状态

| 变更 | 说明 |
|------|------|
| **移除二三排** 加热/通风开关与档位 number | 控制不稳；仅保留方向盘 + 主驾/副驾。二三排 **sensor 状态只读仍保留**。 |
| 主副驾快速点击后刷新状态不符 | ① 命令 **Lock 串行**；② 关闭后 **20 秒强制显示关**（忽略滞后的 VSS=开）；③ 开启 **180 秒乐观档位**；④ **不再命令后立刻刷 VSS**，改为 5s/15s/40s 补拉，避免旧值盖住。 |

涉及：`switch.py`、`number.py`、`manifest.json` → **0.9.5**

---

## [0.9.4] — 2026-09-24

### 座椅状态与二三排

| 问题 | 处理 |
|------|------|
| 打开后不显示 2 档；退出再进变「关」但车仍在开 | **乐观状态 + VSS 滞后**：VSS>0 以车端为准；VSS 仍为 0 时在 **3 分钟内**保留刚设置的档位/开状态。命令后按 4s/12s/30s **补拉 VSS**。 |
| 二三排加热/通风不可用 | ① 二三排座椅信号改为 **HIGH 每轮轮询**（原先 MID 1 小时）；② 开关/档位 **不再被功能探测过滤**（`feature=None` 始终创建）。 |
| 打开默认档 | 仍为 **2 档**；可用 number 调 1/2/3。 |

涉及：`switch.py`、`number.py`、`signals.py`、`coordinator.py`、`manifest.json` → **0.9.4**

---

## [0.9.3] — 2026-09-24

### 座椅加热/通风

| 问题 | 处理 |
|------|------|
| 开/关只能 1 档 | 开关「打开」默认改为 **2 档**；新增 **number 档位实体 0–3**（主副驾、二排左右、三排左右的加热/通风均可调 1/2/3 档）。 |
| 巴法关闭座椅无效 | ① 巴法桥增加 **通用开关映射** `bemfa_topic_switches`（`主题=suffix` 逗号分隔）；`off` → `switch.turn_off`（发 LEVEL0/OFF）。② 若你用的是 BeHome **从巴法云拉进 HA** 的虚拟开关，那不控车——请改用本集成 `switch.*` + 上述映射。 |
| 缺二排/三排实体 | `switch` 补齐：二排左/右 加热+通风；三排左/右 加热+通风（按功能探测/VSS 创建）。传感器侧原本已有状态显示。 |

**巴法座椅配置示例（选项 → 巴法开关主题）：**

```text
zjzr006=seat_fl_heat,fzjzr006=seat_fr_heat,zjzt006=seat_fl_vent,fzjzt006=seat_fr_vent
```

（主题名自定，后缀必须 `006` 或 `001`；`=` 后为 unique 后缀，见实体 `unique_id` 中 `sw_` 后一段。）

涉及：`switch.py`、`number.py`、`bemfa.py`、`features.py`、`config_flow.py`、`manifest.json` → **0.9.3**

---

## [0.9.2] — 2026-09-24

本次会话内的修复与功能变更汇总。安装到 HA 后请**重启 Home Assistant**。

---

### 一、首次登录辅助页（浏览器过滑动/短信验证）

| 问题 | 处理 |
|------|------|
| 首次配置时 `/lixiang-login` 404 | 纯 config_flow 在尚无 config entry 时不会走 `async_setup`，视图未注册。已在 `async_step_user` / `password_login` / `browser` 进入时**立即注册** HTTP 视图。 |
| 默认链接是 `127.0.0.1`，其它设备打不开 | 改进 `_base_url()`：优先 `external_url` / `internal_url`、历史可用地址；回环地址时表单文案明确要求改成实际 IP。用户填过的「HA 访问地址」会记入 identity store，下次默认复用。 |
| 打开理想登录页一直转圈 | ① 会话/配置流强制生成**非空 `device_id`**（空值会让 `account.lixiang.com/app-auth` 卡住）；② 登录链接增加 **`mode=h5`**，避免跳到 App WebView 桥接页 `/login/app`；③ `audience`/`scope` 改为与 pake 登录一致的实测值；④ 辅助页增加**备用 H5 登录链接**。 |
| 状态轮询偶发 404 | `login_page.html` 改为绝对路径 `fetch("/lixiang-login/status?...")`。 |
| 无 token / token 失效提示不清 | 无 token 返回诊断页（证明路由已通）；失效时文案区分「链接已失效」与服务器 404。 |

涉及文件：`config_flow.py`、`auth_web.py`、`login_page.html`、`identity.py`、`strings.json`、`translations/zh-Hans.json`

---

### 二、巴法云（Bemfa）可识别实体

**背景：** 巴法云不识别 HA 的 `button` 域；设备类型只认主题名后三位（`009`=窗帘/cover，`006`/`001`=开关）。

| 变更 | 说明 |
|------|------|
| 新增 `cover.py` | **尾门**、**车窗** 收敛为 `cover`（开/关/位置）。 |
| 新增 `bemfa.py` | HTTP 桥接：状态上报 + 指令拉取；选项里填 uid 与主题后启用。 |
| `switch` 增加「寻车」 | momentary 开关，打开即触发 `remoteVehSearch`（巴法可识别）。 |
| `button.py` 精简 | 去掉与 cover 重复的开/关尾门、开/关窗；保留寻车、远程启动。 |
| 注册 `Platform.COVER` | `__init__.py`。 |
| 选项表单 | 轮询间隔、车控开关之外，增加巴法 uid / 车窗主题 / 尾门主题 / 寻车主题。 |
| 新增服务 | `lixiang_auto.open_windows`、`lixiang_auto.close_windows`（物理开/关，供自动化/调试）。 |

**巴法配置步骤：**

1. 控制台创建主题：车窗/尾门 → 后缀 `009`；寻车 → 后缀 `006`  
2. HA → 理想汽车 → **选项** → 填 uid 与主题名 → 保存  
3. 重载或重启集成；日志出现「巴法云桥接已启用」即成功  

涉及文件：`cover.py`、`bemfa.py`、`switch.py`、`button.py`、`__init__.py`、`config_flow.py`、`services.yaml`、`manifest.json`（版本 → 0.9.2）

---

### 三、车窗方向与小爱/巴法开合

| 问题 | 处理 |
|------|------|
| 小爱「关闭」变开窗、「打开」变关窗 | ① 巴法指令改为调用实体 **`async_physical_open` / `async_physical_close`**（物理语义），不再经反向 cover 服务二次映射；② 状态用 **`topic/up`** 上报，避免 `getmsg` 把状态当下发指令；③ 忽略与 `_last_pub` 相同的回声消息。 |
| 车窗 UI 方向反复调整 | 最终采用**标准 cover 语义**以支持开部分窗（见下）。 |
| 需要开部分车窗 | 保留 `cover` + **SET_POSITION**：`position` = 物理开度 0–100%；滑条 N% → 车端开约 N%（全开映射为 99）。 |

**当前车窗语义（最终）：**

| 入口 | 行为 |
|------|------|
| HA 打开 | 物理全开 |
| HA 关闭 | 物理全关 |
| HA 位置 N% | 物理开约 N% |
| 小爱/巴法 `on` | 物理全开 |
| 小爱/巴法 `off` | 物理全关 |
| 小爱/巴法 `on#N` | 物理开 N% |

涉及文件：`cover.py`、`bemfa.py`

---

### 四、版本

- `manifest.json`：`0.9.1` → **`0.9.2`**

---

### 升级检查清单

1. 将本目录同步到 HA 的 `custom_components/lixiang_auto/`  
2. **重启 Home Assistant**  
3. 首次登录：HA 访问地址填成 `http://<实际IP>:8123`，确认辅助页 device_id 非空、登录页可出表单  
4. 实体：应出现 `cover.尾门`、`cover.车窗`、`switch.寻车`  
5. 巴法：选项填好 uid/主题后，日志有「巴法云桥接已启用」  
6. 小爱：打开/关闭与物理开/关一致；HA 滑条可调部分开度  

---

### 已知限制

- 车端若只认 `0` / `99` 两档，中间开度可能被收成全开或全关。  
- 巴法 HTTP 轮询约 4 秒一次，语音有轻微延迟。  
- `127.0.0.1` 仅当浏览器与 HA 同机可用；跨设备请改 HA 访问地址。  
