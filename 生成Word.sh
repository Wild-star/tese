#!/usr/bin/env bash
# 一键生成符合征稿格式的 Word，输出到 output/ 目录。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
python3 -m pip install -q -r requirements.txt
python3 scripts/build_formatted_docx.py "$@"
if [[ -f output/paper.docx ]]; then
  cp -f output/paper.docx "$ROOT/paper.docx"
  for f in output/paper_v*.docx; do
    [[ -f "$f" ]] || continue
    cp -f "$f" "$ROOT/$(basename "$f")"
  done
  echo "请下载：$ROOT/paper.docx"
  latest="$(ls -1 "$ROOT"/paper_v*.docx 2>/dev/null | sort -V | tail -n 1 || true)"
  [[ -n "${latest}" ]] && echo "最新轮次：${latest}"
fi
