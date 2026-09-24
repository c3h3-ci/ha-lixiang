# 贡献指南

> 本项目所有改动**必须通过 Pull Request**，`main` 分支已开启保护。

---

## 工作流

```
① 从 main 建分支
     ./li-pr.sh start <类型> <简述>
     
② 改代码（在 HA 测试机）
     /media/duola/devdata/AI-workspace/home-assistant-nas/ha-test/config/custom_components/lixiang_auto/
     
③ ★ 验证（改完必跑，7 项检查）
     ./li-verify.sh
     
     ⚠️ 这步不能省 —— 2026-09-24 曾因跳过它导致 4 次
        HA 实体大面积不可用（详见 VERIFY.md）
     
④ 提交 + 开 PR（内置验证拦截）
     ./li-pr.sh submit
     
⑤ 人在 GitHub 上 review + 合并
     https://github.com/c3h3-ci/ha-lixiang/pulls
```

---

## 分支命名

| 类型 | 用途 | 例子 |
|---|---|---|
| `feat/` | 新功能 | `feat/optimize-login-flow` |
| `fix/` | Bug 修复 | `fix/trunk-door-semantics` |
| `refactor/` | 重构（不改行为）| `refactor/merge-route-id` |
| `docs/` | 文档 | `docs/add-contributing` |
| `ci/` | CI/构建 | `ci/add-hassfest` |
| `chore/` | 杂项 | `chore/bump-version` |

---

## PR 要求

### 必须

- [ ] **已在测试机验证**（HA 重启无错误、实体正常）
- [ ] **敏感信息扫描通过**（`./li-pr.sh submit` 会自动跑）
- [ ] **CI 通过**（hassfest + HACS + lint）

### 建议

- [ ] 附上变更原因的说明（尤其是"为什么这样改"）
- [ ] 涉及信号语义的改动，**必须附 App 源码依据**（文件:行号）
- [ ] 涉及行为变更的，附验证方法

---

## ⚠️ PR 合并后的规则

**PR 合并后，不要继续在同一个分支上提交！**

```
❌ 错误做法：
   ① ./li-pr.sh start feat xxx      → 建分支
   ② 改代码 + 提交 + 开 PR #11
   ③ 人合并 PR #11
   ④ 又在同一分支上提交修复         → ★ 推不进 main！
      （PR 已关闭，新 commit 无处可去）

✅ 正确做法：
   ① PR 合并后，立刻切回 main 并 pull
   ② 从 main 建【新分支】做后续改动
   ③ 开新 PR
```

**2026-09-24 实际踩坑**：PR #11 合并后又在原分支提交了 2 个修复，
导致 main 上是有 bug 的版本（缺 `to_binary_descriptions` 等），
需要 PR #12 补救。

### 检查方法

```bash
# 提 PR 前确认：当前分支是否已合并到 main？
git log --oneline origin/main..HEAD    # 有输出 = 有新 commit（正常）
git branch -r --merged origin/main | grep "$(git branch --show-current)"
#   ↑ 有输出 = 该分支已合并 → ★ 应改用新分支！
```

---

## 禁止

- ❌ 直接推 `main`（已被 GitHub 拒绝）
- ❌ 提交真实个人数据（手机号/密码/VIN/设备ID）
- ❌ 未经验证的信号语义猜测（必须读 App 源码）

---

## 双副本同步

集成在 HA 测试机运行时是两份代码：

```
测试机（HA 运行）                     仓库（发布）
config/custom_components/     ←→    ha-lixiang/
      lixiang_auto/                    custom_components/lixiang_auto/
```

`./li-pr.sh submit` 会自动同步 + 检查。

> ⚠️ HA 无法从软链接加载 custom_component，所以必须双副本。

---

## 版本发布

```bash
./bump.sh patch     # 0.11.0 → 0.11.1（修 bug）
./bump.sh minor     # 0.11.0 → 0.12.0（加功能）
./bump.sh major     # 0.11.0 → 1.0.0（稳定版）
```

发布后创建 GitHub Release（标记 prerelease，直到 1.0）。

---

## 相关脚本

| 脚本 | 位置 | 作用 |
|---|---|---|
| `li-pr.sh` | `AI-workspace/` | PR 工作流（建分支/提交/开 PR）|
| `li-sync.sh` | `AI-workspace/` | 双副本同步 + 敏感扫描 |
| `bump.sh` | `ha-lixiang/` | 版本号递增 |
