# Li Auto for Home Assistant

理想汽车（Li Auto）Home Assistant 集成 —— 实时车辆状态 + 远程控制。

---

> ## ⚠️ BETA 版本（v1.0.0）
>
> **本项目处于 Beta 阶段，欢迎试用但不建议用于关键场景。**
>
> ### 当前验证范围
>
> | 项 | 状态 |
> |---|---|
> | 车型 | ✅ 理想 L6（一辆，长期运行）<br>❓ L7 / L8 / L9 / MEGA / i 系列**未验证** |
> | 账号 | ✅ 车主账号（单账号）<br>❓ 家人账号 / 多账号**未验证** |
> | 多车 | ❌ **未支持**（一个集成实例 = 一辆车） |
> | 信号语义 | ⚠️ 部分靠 App 源码还原，**未经长期观察**<br>（空调/尾门/充电口盖为 2026-09-23 修正） |
> | 首次登录 | ⚠️ 辅助页面方案**刚验证 1 次**，不同网络/浏览器未测 |
> | 单元测试 | ✅ **200 个**（signals / rendering / policy / coordinator / features）<br>❓ 实车端到端仍需手工验证 |
>
> ### 已知问题
>
> - 部分信号语义仍在核实（`charge_gun_ac` 等）
> - 车控命令下发后，车辆状态可能有几十秒延迟才同步
>   （已用「乐观更新 + TTL」缓解，见下方说明）
> - 多车场景未实现（第二个账号接入同一辆车会被拒绝）
>
> ### ⚠️ 待实车验证的控制项
> 
> 以下 controlType 在 App 反编译中**未找到**，是依据同族命名**推测**的：
> 
> | 实体 | 推测的 controlType | 依据 |
> |---|---|---|
> | 二排中座椅加热 | `secMSeatHeatSw` | 状态信号 `SMSeatHeatState` 存在 |
> | 二排左座椅通风 | `secLSeatVentSw` | 状态信号新鲜（09-23/09-24）|
> | 二排右座椅通风 | `secRSeatVentSw` | 同上 |
> 
> 若点击后日志出现 `resultCode=2009`，说明服务端不认该 controlType，
> 请提 Issue 告知，我们会改为「只显示状态」。
> 
> ### 💡 状态同步机制（乐观更新）
> 
> 车机上报状态有延迟（几秒~几十秒）。为避免"刚点开开关就显示关闭"，
> 集成采用**乐观更新 + TTL**：
> 
> 1. 下发命令后，立即用目标值显示（乐观值）
> 2. 45~150 秒内，若服务端状态还没跟上 → 继续显示乐观值
> 3. 服务端状态追上 或 超过 TTL → 以服务端为准
> 
> 适用：座椅档位 / 空调温度 / 尾门 / 车窗 / 哨兵 / 快冷快热。
> 

> ### ❌ 不可用（需 LiNdn 长连接）
> 
> 反编译 8.27.0 后确认：以下功能走 **LiNdn（NDN 长连接）**通道，
> 而非 HTTP `cmd/send`。我们的 HTTP 实现无法触达。
> 
> | 功能 | 状态 |
> |---|---|
> | 充电启停 / 预约充电 / 充电模式 / 充电上限 / 电池保温 / 充电时间 | ❌ 控制不可用（**状态读取正常**）|
> | 按时出发 | ❌ 控制不可用 |
> | 场景模式 / 冰箱预约 | ❌ 未实现 |
> | 宠物模式 / 洗车模式（App 8.25.3+）| ❌ 未实现 |
> 
> **技术细节**：详见 [docs/LiNdn长连接发现_20260925.md](docs/LiNdn长连接发现_20260925.md)。
> LiNdn 是 Rust 实现的 NDN 协议栈（`liblivenet.so`，9.4 MB），
> 需要 JOB_PORT token + GFM forwarding hint + HTTP-over-NDN 封装。
> 
> **✅ 这些功能的 sensor 全部正常**，可以只看不用改。
> 
> #### 🔍 为什么走不了 HTTP（2026-09-26 精确逆向）
> 
> App 的路由规则（`LiveNetControlRouter.resolveRoute()`）：
> 
> ```kotlin
> if (key.contains("mob.vehCtrlService.vehCtrlJobList"))
>     VEH_CONTROL     // ← 走 HTTP cmd/send（我们能实现）
> else
>     JOB             // ← 走 LiNdn（NDN），HTTP 不执行
> ```
> 
> 充电的 `destParams = "mob.metaJobService.remoteChargingControl"`
> 不含 `vehCtrlJobList` → **走 JOB → HTTP 发不出去**（服务端返回
> `pushState=7 resultCode=2009`）。
> 
> **我们已确认参数全对**（cmdKey / cmdData / expire / jobExpire / token），
> 只是**通道不对**。所以不是"没逆向好"，是 HTTP 通道根本不支持。
> 
> ★ **现在点充电开关会得到明确提示**（不再静默失败）：
> > 「remote_charge_control」走的是理想 App 的 LiNdn（JOB）通道，
> > HTTP 车控接口不支持。这是已知限制，充电相关控制暂不可用。
> 
> **完整分析**：[docs/充电控制完整破解_20260926.md](docs/充电控制完整破解_20260926.md)
> 
> ### 反馈
>
> 遇到问题请提 [Issue](https://github.com/c3h3-ci/ha-lixiang/issues)，
> 并附上「设备 → 下载诊断」导出的 JSON（已脱敏）。
>
> ### 版本路线
>
> - `0.x` —— Beta（当前）：功能可用，边界场景未覆盖
> - `1.0` —— 稳定版（条件：多车型验证 + 单元测试 + 长期观察）

---

> ⚠️ **免责声明**
> 本项目为个人学习/研究用途，非理想汽车官方项目，未获官方授权。
> 使用可能违反理想汽车的服务条款，所有风险由使用者自行承担。
> 请勿用于商业用途。请勿公开你的账号、车辆、位置等敏感信息。

---

## 功能

- **实时状态**（145 个信号）：电量、续航、门锁、车窗、胎压、温度、
  充电状态、位置、座椅加热、空调、哨兵模式等
- **远程控制**：锁车/解锁、空调（开关/温度/快热快冷/除霜）、车窗、尾门、
  寻车（含闪灯/鸣笛）、远程启动、哨兵开关、远程拍照、充电启停、
  座椅加热/通风（8 个位置，含档位）、方向盘加热
- **车辆定位**：GPS 轨迹（可显示在地图上）
- **服务器通知**：拉取理想服务器的车辆预警通知（充电完成、电量不足等）
- **车型自适应**：自动探测车辆支持的功能，不同的车显示不同的实体
- **多车支持**：一个账号多辆车（每辆车独立接入）

---

## 安装

### 方式一：HACS（推荐）

1. HACS → 集成 → 右上角菜单 → 自定义存储库
2. 添加本仓库地址，类别选「Integration」
3. 搜索 "Li Auto" 安装
4. 重启 Home Assistant

### 方式二：手动

把 `custom_components/lixiang_auto` 复制到你的 HA 配置目录：

```bash
cp -r custom_components/lixiang_auto /path/to/homeassistant/config/custom_components/
```

然后重启 Home Assistant。

---

## 配置

1. HA → **设置 → 设备与服务 → 添加集成**
2. 搜索 **Li Auto**
3. 输入理想账号的**手机号 + 密码**

### 首次登录需要验证

理想对新设备有风控：首次登录需要**短信验证码**，而验证码有
**滑动验证**保护（第三方，无法自动完成）。

集成会引导你：

```
① 添加集成 → 输手机号 + 密码
② 集成显示一个「辅助页面」链接
③ 打开链接 → 点【▶ 点这里打开理想登录页】
④ 在新窗口里：输手机号+密码 → 点获取验证码 → 拖动滑块 → 收短信 → 输验证码 → 登录
⑤ 回到辅助页面，看到绿色提示 = 成功
⑥ 回 HA 点【提交】继续
```

**验证成功后，这个设备会被理想标记为受信任，以后都不用再验证。**

> 💡 **关于 API 签名凭据**
> 集成已内置签名所需的凭据（`hac_key` / `keyId` / `deviceId`）。
> 它们来自理想 App 登录后 `GET /keySuite` 服务端下发的密钥套件，
> 经 App 内嵌常量 RSA 解密 + AES-256-CTR 派生而来 —— **开箱即用**。
> 若遇到 `100005 签名错误`（密钥套件约 120 天轮换一次），
> 可在集成选项里手动更新。

### 轮询间隔

默认 60 秒（可在集成选项里改，30~3600 秒）。

---

---

## 实体

**127 个实体**（L6 实测；其他车型按功能探测自动增减），按平台分类：

| 平台 | 数量 | 说明 |
|---|---|---|
| sensor | 66 | 电量、续航、温度、胎压、充电… |
| binary_sensor | 34 | 门锁、车窗、充电枪、告警… |
| **fan** | **9** | **座椅加热/通风（关闭·低·中·高，含二排左中右）** |
| **switch** | **5** | **方向盘加热、快热、快冷、除霜、哨兵** |
| button | 5 | 寻车、授权驾驶、闪灯、鸣笛、远程拍照 |
| **cover** | **2** | **尾门 / 全车窗** |
| climate | 1 | 空调（温度/模式）|
| lock | 1 | 车锁 |
| number | 1 | 空调设定温度 |
| select | 1 | 空调控制类型 |
| device_tracker | 1 | 车辆位置 |
| notify | 1 | 通知事件 |

> 💡 **域选择说明**：
> · 座椅加热/通风 → `fan`（HA 原生「关闭/低/中/高」档位 UI）
> · 尾门/车窗 → `cover`（支持 open/close + 位置读回，无需单独开/关按钮）
> · 哨兵/快冷/快热/除霜/充电 → `switch`（带状态读回，一眼可见开关状态）

诊断类实体（OTA、保养、版本等）默认隐藏，需要时可在设备页面启用。

---

## 服务

| 服务 | 说明 |
|---|---|
| `lixiang_auto.refresh` | 立即刷新一次数据 |
| `lixiang_auto.wakeup` | 唤醒休眠的车辆 |

---

## 通知事件

集成会监听理想服务器的车辆通知，并以 HA 事件形式抛出：

```yaml
automation:
  - alias: 理想车辆告警
    trigger:
      - platform: event
        event_type: lixiang_auto_notification
        event_data:
          category: vehicle      # 只监听车辆通知（过滤广告）
    action:
      - service: notify.mobile_app_xxx
        data:
          title: "🚗 {{ trigger.event.data.title }}"
          message: "{{ trigger.event.data.summary }}"
```

---

## 故障排查

### 帮助 → 下载诊断

设备页面有「下载诊断」按钮，会导出脱敏的 JSON（不含密码/密钥/位置）。

### 常见问题

**Q: 提示"需要短信验证"**
A: 正常流程，按上面「首次登录需要验证」操作。

**Q: 实体显示未知（unknown）**
A: 车辆离线时部分信号可能无数据。集成会保留最后一次有效值。

**Q: 无法控制车辆**
A: 检查集成选项里「允许远程控制」是否开启。

**Q: 数据不更新**
A: 车辆可能离线（集成会自动跳过轮询以省流量）。
   可用 `lixiang_auto.wakeup` 服务唤醒。

---

## 技术说明

- 通信方式：HTTPS（理想 App 的 API），非 MQTT
- 登录：PAKE 协议（手机号 + 密码）
- 状态读取：VSS 实时信号通道
- 车辆控制：车控 API（需要 VAT token）

---

## 更新日志

见 [CHANGELOG.md](CHANGELOG.md)。

---


## 许可

MIT License

第三方商标（理想汽车、Li Auto 等）归其各自权利人所有。
# 测试

---

## 开发

### 本地检查

```bash
# 安装 pre-commit hook（提交前自动检查语法/JSON/敏感信息）
cp .github/pre-commit.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
```

### 版本发布

```bash
./bump.sh patch     # 1.0.0 → 1.0.1（修 bug）
./bump.sh minor     # 1.0.0 → 1.1.0（加功能）
./bump.sh major     # 1.0.0 → 2.0.0（不兼容变更）
git tag v1.0.1 && git push --tags
```

### CI

推送到 `main` 或提 PR 时自动运行：

| 检查 | 说明 |
|---|---|
| **hassfest** | HA 官方集成结构校验 |
| **HACS validate** | HACS 规范校验 |
| **lint** | Python 语法 + JSON + 敏感信息 + manifest 字段 |

### 双副本同步

集成在测试机运行时，代码与仓库是两份。使用同步脚本：

```bash
./li-sync.sh status            # 查看差异
./li-sync.sh push-repo         # 测试机 → 仓库
./li-sync.sh commit "说明"     # 同步 + 提交 + 推送
```

> 注：HA 无法从软链接加载 custom_component，所以必须双副本。
