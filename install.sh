#!/usr/bin/env bash
# 把 footage-to-jianying 装进 Codex 和/或 WorkBuddy 的 skills 目录。
#
#   ./install.sh                      # 自动装到已存在的 ~/.codex 与 ~/.workbuddy
#   ./install.sh --codex              # 只装 Codex
#   ./install.sh --workbuddy          # 只装 WorkBuddy
#   ./install.sh --link               # 用软链接（改仓库即时生效，适合开发）
#   ./install.sh --venv               # 顺便建 .venv 并装 requests
#   ./install.sh --target /tmp/skills # 装到指定 skills 目录（调试用）
set -euo pipefail

SKILL_NAME="footage-to-jianying"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGETS=()
LINK=0
MAKE_VENV=0

while [ $# -gt 0 ]; do
  case "$1" in
    --codex)    TARGETS+=("$HOME/.codex/skills") ;;
    --workbuddy) TARGETS+=("$HOME/.workbuddy/skills") ;;
    --target)   TARGETS+=("$2"); shift ;;
    --link)     LINK=1 ;;
    --venv)     MAKE_VENV=1 ;;
    -h|--help)  sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
  shift
done

if [ ${#TARGETS[@]} -eq 0 ]; then
  [ -d "$HOME/.codex/skills" ] && TARGETS+=("$HOME/.codex/skills")
  [ -d "$HOME/.workbuddy/skills" ] && TARGETS+=("$HOME/.workbuddy/skills")
  [ ${#TARGETS[@]} -eq 0 ] && { echo "既没找到 ~/.codex/skills 也没找到 ~/.workbuddy/skills，请用 --target 指定。" >&2; exit 1; }
fi

echo "源目录：$REPO_DIR"
for skills_dir in "${TARGETS[@]}"; do
  dest="$skills_dir/$SKILL_NAME"
  mkdir -p "$skills_dir"
  if [ "$LINK" = "1" ]; then
    rm -rf "$dest"
    ln -s "$REPO_DIR" "$dest"
    echo "✅ 软链：$dest -> $REPO_DIR"
  else
    rm -rf "$dest"
    mkdir -p "$dest"
    for item in SKILL.md scripts references assets agents; do
      [ -e "$REPO_DIR/$item" ] && cp -R "$REPO_DIR/$item" "$dest/"
    done
    echo "✅ 已复制：$dest"
  fi

  editor_dir="$skills_dir/jianying-editor"
  if [ -f "$editor_dir/scripts/jy_wrapper.py" ]; then
    echo "   ↳ 运行时依赖 jianying-editor：已找到（$editor_dir）"
  else
    echo "   ↳ ⚠️ 没找到 $editor_dir，写草稿会失败，见 README「安装运行时依赖」"
  fi
done

# 环境自检
command -v ffmpeg  >/dev/null || echo "⚠️ 没找到 ffmpeg（抽帧/切点/合成都需要）"
command -v ffprobe >/dev/null || echo "⚠️ 没找到 ffprobe"
[ -n "${OPENAI_API_KEY:-}" ] || echo "ℹ️ 没设 OPENAI_API_KEY：配音步骤要跳过时，把 plan.voice.mode 设为 \"none\""

if [ "$MAKE_VENV" = "1" ]; then
  venv="$REPO_DIR/.venv"
  [ -d "$venv" ] || python3 -m venv "$venv"
  "$venv/bin/python" -m pip install -q --upgrade pip
  "$venv/bin/python" -m pip install -q -r "$REPO_DIR/requirements.txt"
  echo "✅ venv：$venv"
  echo "   跑脚本用：$venv/bin/python scripts/xxx.py ..."
fi

echo
echo "装完了。下一步："
echo "  cd $REPO_DIR && python3 scripts/jianying_import.py --check   # 看剪映草稿目录是否就绪"
