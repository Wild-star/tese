#!/usr/bin/env bash
# 一键生成符合征稿格式的 Word，输出到 output/ 目录。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
python3 -m pip install -q -r requirements.txt
python3 scripts/build_formatted_docx.py "$@"
if [[ -f output/paper.docx ]]; then
  cp -f output/paper.docx "$ROOT/paper.docx"
  cp -f output/paper_v2.docx "$ROOT/paper_v2.docx" 2>/dev/null || true
  echo "请下载：$ROOT/paper.docx"
  echo "本轮版本：$ROOT/paper_v3.docx"
fi
