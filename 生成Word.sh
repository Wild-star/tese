#!/usr/bin/env bash
# 一键生成符合征稿格式的 Word，输出到 output/ 目录。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
python3 -m pip install -q -r requirements.txt
python3 scripts/build_formatted_docx.py "$@"
# 固定英文文件名，避免中文路径导致无法下载
if [[ -f output/paper.docx ]]; then
  cp -f output/paper.docx "$ROOT/paper.docx"
  echo "请下载：$ROOT/paper.docx"
fi
