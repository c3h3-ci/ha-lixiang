# Li Auto for Home Assistant

理想汽车（Li Auto）Home Assistant 集成 —— 实时车辆状态 + 远程控制。

> ⚠️ **免责声明**
> 本项目为个人学习/研究用途，非理想汽车官方项目，未获官方授权。
> 使用可能违反理想汽车的服务条款，所有风险由使用者自行承担。
> 请勿用于商业用途。请勿公开你的账号、车辆、位置等敏感信息。

---

## 功能

- **实时状态**（110 个信号）：电量、续航、门锁、车窗、胎压、温度、
  充电状态、位置、座椅加热、空调、哨兵模式等
- **远程控制**：锁车/解锁、空调（开关/温度/风速）、车窗、尾门、
  寻车、远程启动、授权、座椅加热、方向盘加热
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

约 100+ 个实体，按平台分类：

| 平台 | 数量 | 说明 |
|---|---|---|
| sensor | ~60 | 电量、续航、温度、胎压、充电… |
| binary_sensor | ~30 | 门锁、车窗、充电枪、告警… |
| button | 6 | 寻车、开/关尾门、远程启动… |
| switch | 5 | 空调、除霜、座椅加热… |
| climate | 1 | 空调（温度/模式）|
| lock | 1 | 车锁 |
| number | 1 | 空调温度 |
| select | 1 | 空调控制类型 |
| device_tracker | 1 | 车辆位置 |
| notify | 1 | 通知事件 |

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
