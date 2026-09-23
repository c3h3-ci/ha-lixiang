# 签名凭据提取指南

理想 API 的请求需要 x-chj 签名。签名需要 4 个凭据，**每台设备独有**，
本仓库不内置，需要你从自己的设备上提取一次。

---

## 为什么必须自己提取

```
服务端校验逻辑：
  1. 收到请求 → 读 X-CHJ-Key（keyId）和 X-CHJ-Deviceid
  2. 用该 keyId 对应的 hac_key 验签
  3. 校验 deviceId 是否与 keyId 绑定

★ keyId 和 deviceId 是 App 安装时【客户端生成并绑定】的
★ hac_key 是登录后【服务端下发】的
★ 所以换了设备就必须重新提取

如果内置了别人设备的凭据：
  ✗ 签名校验会失败（服务端发现 keyId/deviceId 不匹配）
  ✗ 或者所有用户被识别为同一台设备（风控风险）
```

---

## 凭据存储位置

### Android

| 凭据 | 位置 |
|---|---|
| `hac_key` | SharedPreferences `k_c_1_4_1_2` → key `k11` |
| `key_id` | 同上 → key `k22` |
| `x_chj_deviceid` | SharedPreferences `d1` |
| `app_token` | 运行期获取（可留空）|

> 注：新版本用 MMKV 存储，文件在 `shared_prefs/` 或 `files/mmkv/` 下。

### iOS

| 凭据 | 位置 |
|---|---|
| `hac_key` | Keychain（受访问组密钥加密，需 Hook `CCHmac` 捕获）|
| `x_chj_deviceid` | Keychain: `com.chehejia.m01.fingerprint` / `chehejia_fingerprintId` |
| `app_token` | 运行期获取 |

---

## 提取方法

### 方法 1：抓包（最简单，但只能拿 3 个）

用 mitmproxy 抓 App 的 HTTPS 请求：

```
X-CHJ-Key:      <key_id>
X-CHJ-Deviceid: <x_chj_deviceid>
X-CHJ-TOKEN:    <app_token>
```

**问题**：`hac_key` 不在请求头里，抓不到。

### 方法 2：Android root（推荐）

```bash
# 1. 找到存储文件
adb shell su -c "ls -la /data/data/com.chehejia.oc.m01/shared_prefs/"

# 2. 导出（注意 MMKV 需要专用解析工具）
adb shell su -c "cat /data/data/com.chehejia.oc.m01/shared_prefs/k_c_1_4_1_2.xml" > mmkv.xml

# 3. 解密
#    MMKV 的值是加密的（AES），需要 InternalStub 解密
#    参考：tools/decrypt_mmkv.py（本仓库不含，可参考 lixiang-reverse 项目）
```

### 方法 3：Frida Hook（最可靠）

```javascript
// Hook CommonCrypto 的 CCHmac，捕获签名 key
var CCHmac = Module.findExportByName(null, "CCHmac");
Interceptor.attach(CCHmac, {
    onEnter: function(args) {
        var keyLen = args[1].toInt32();
        var keyData = Memory.readByteArray(args[2], keyLen);
        console.log("hac_key:", Array.from(new Uint8Array(keyData))
                    .map(b => b.toString(16).padStart(2,'0')).join(''));
    }
});
```

---

## 配置到 HA

HA → 添加集成 → **手动填写凭据** → 填入：

| 字段 | 示例（格式）|
|---|---|
| `hac_key` | 64 个 hex 字符 |
| `key_id` | 32 个字符 |
| `x_chj_deviceid` | 32 个字符 |
| `app_token` | `APP-` 开头（可留空）|
| `phone` | 手机号（用于自动续期登录）|
| `password` | 密码 |
| `vin` | 车辆 VIN（可留空，自动获取）|

---

## 安全提醒

⚠️ 这些凭据等同于你的设备身份，请勿公开分享
⚠️ 抓包日志、诊断文件请勿上传
⚠️ 用完后建议清理抓包工具的日志
