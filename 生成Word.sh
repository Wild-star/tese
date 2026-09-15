#!/usr/bin/env bash
# 一键生成符合征稿格式的 Word，输出到 output/ 目录。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
python3 -m pip install -q -r requirements.txt
python3 scripts/build_formatted_docx.py "$@"
# 同步一份到仓库根目录，便于在 PR / 工作区直接下载
GEN="$(ls -1t output/*.docx | head -n 1)"
if [[ -n "${GEN}" ]]; then
  cp -f "$GEN" "$ROOT/$(basename "$GEN")"
  echo "同步副本：$ROOT/$(basename "$GEN")"
fi
