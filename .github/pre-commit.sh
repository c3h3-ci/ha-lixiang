#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  ha-lixiang pre-commit hook
#  提交前自动检查：语法 / JSON / 敏感信息 / manifest 一致性
#
#  安装：cp pre-commit.sh ha-lixiang/.git/hooks/pre-commit && chmod +x
# ═══════════════════════════════════════════════════════════════════════════

set -uo pipefail

RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; RST=$'\033[0m'
FAIL=0

echo "${YEL}▸ pre-commit 检查${RST}"

# 只检查 staged 的文件
STAGED=$(git diff --cached --name-only --diff-filter=ACM)
[[ -z "$STAGED" ]] && { echo "  无 staged 文件"; exit 0; }

# ── 1. Python 语法 ─────────────────────────────────────────────────────
echo "  [1/4] Python 语法"
for f in $(echo "$STAGED" | grep '\.py$' || true); do
  if ! python3 -m py_compile "$f" 2>/dev/null; then
    echo "${RED}    ✗ 语法错误: $f${RST}"
    python3 -m py_compile "$f" 2>&1 | head -5 | sed 's/^/        /'
    FAIL=1
  fi
done
[[ $FAIL -eq 0 ]] && echo "${GRN}    ✓ 通过${RST}"

# ── 2. JSON 有效性 ─────────────────────────────────────────────────────
echo "  [2/4] JSON 有效性"
JFAIL=0
for f in $(echo "$STAGED" | grep '\.json$' || true); do
  if ! python3 -c "import json,sys; json.load(open('$f',encoding='utf-8'))" 2>/dev/null; then
    echo "${RED}    ✗ JSON 无效: $f${RST}"
    JFAIL=1; FAIL=1
  fi
done
[[ $JFAIL -eq 0 ]] && echo "${GRN}    ✓ 通过${RST}"

# ── 3. 敏感信息（真实个人数据不应进公开仓库）────────────────────────────
echo "  [3/4] 敏感信息"
# 注意：const.py 的 hac_key/key_id/xdev/app_token 是 API 签名必需，属允许项
SENSITIVE=(
  "13736776363:手机号"
  "19285871820:手机号"
  "cdd633723:密码"
  "180909:安全码"
  "HLX32B14XR1361015:VIN"
  "dfb44c4fd7d64d1e924d29e6340b8694:设备ID"
  "192\.168\.3\.206:内网IP"
  "homediy:内网域名"
)
SFAIL=0
# 排除检查脚本自身 / CI 配置（它们含检测模式字符串）
SCAN_FILES=$(echo "$STAGED" | grep -vE '^\.github/(pre-commit\.sh|workflows/validate\.yml)$' || true)
for p in "${SENSITIVE[@]}"; do
  kw="${p%%:*}"; name="${p##*:}"
  [[ -z "$SCAN_FILES" ]] && break
  hits=$(echo "$SCAN_FILES" | xargs grep -l "$kw" 2>/dev/null || true)
  if [[ -n "$hits" ]]; then
    echo "${RED}    ✗ 发现 $name:${RST}"
    echo "$hits" | sed 's/^/        /'
    SFAIL=1; FAIL=1
  fi
done
if [[ $SFAIL -eq 0 ]]; then
  echo "${GRN}    ✓ 通过${RST}"
else
  echo "${YEL}    如确需提交，用 git commit --no-verify 跳过${RST}"
fi

# ── 4. manifest / strings 一致性 ────────────────────────────────────────
echo "  [4/4] manifest 与 strings 一致性"
if [[ -f custom_components/lixiang_auto/manifest.json ]]; then
  MVER=$(python3 -c "import json;print(json.load(open('custom_components/lixiang_auto/manifest.json'))['version'])" 2>/dev/null || echo "?")
  echo "    manifest version: $MVER"
  # 检查 strings.json 与 translations 是否同步
  if [[ -f custom_components/lixiang_auto/strings.json && \
        -f custom_components/lixiang_auto/translations/zh-Hans.json ]]; then
    if ! diff -q custom_components/lixiang_auto/strings.json \
                 custom_components/lixiang_auto/translations/zh-Hans.json >/dev/null 2>&1; then
      echo "${YEL}    ! strings.json 与 translations/zh-Hans.json 不同步${RST}"
      echo "${YEL}      建议: cp strings.json translations/zh-Hans.json${RST}"
    else
      echo "${GRN}    ✓ 翻译文件同步${RST}"
    fi
  fi
fi

echo
if [[ $FAIL -ne 0 ]]; then
  echo "${RED}✗ 检查未通过，提交已阻止${RST}"
  echo "  修复后重试，或 git commit --no-verify 强制提交"
  exit 1
fi
echo "${GRN}✓ 全部检查通过${RST}"
exit 0
