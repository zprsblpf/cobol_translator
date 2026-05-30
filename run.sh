#!/bin/bash
# COBOL → Java 翻译器启动脚本
# 使用包含 torch + sentence-transformers 的 Python 环境

cd "$(dirname "$0")"
PYTHON=/data/models/llm-fa312/bin/python

case "$1" in
  "--parse")
    shift
    $PYTHON main.py "$@" --parse-only
    ;;
  "--section")
    shift
    SECTION="$1"; shift
    $PYTHON main.py "$@" --section "$SECTION"
    ;;
  "--test")
    # 翻译前5个 SECTION 做快速测试
    shift
    $PYTHON main.py "$@" --sections 5
    ;;
  *)
    $PYTHON main.py "$@"
    ;;
esac
