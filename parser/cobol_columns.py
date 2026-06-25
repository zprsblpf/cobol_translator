"""
COBOL 定列格式·行级列处理 —— 薄重导出（正本已迁入相1 `preprocess.columns`）。

对应设计：docs/详细设计/步骤06-COBOL解析器列对齐与停用行修复设计.md（列处理逻辑）、
          docs/详细设计/步骤15-相1预处理独立成相设计.md §4（绞杀接线：列处理正本迁入相1）。

步骤15 绞杀分期①把列处理原语迁入 `preprocess/columns.py`（相1 最底层原语）。本模块保留原 import
路径不破，仅从相1 薄重导出全套 API，行为与原实现逐字一致——`cobol_parser` / `grammar_loader`
（延迟导入）/ `decompose/lines.py` 对本模块的现有 import 一字不改。
"""
from __future__ import annotations

from preprocess.columns import (
    is_deactivated,
    is_comment,
    is_debug,
    indicator,
    clean_line,
    effective,
    clean_block,
)

__all__ = [
    "is_deactivated", "is_comment", "is_debug",
    "indicator", "clean_line", "effective", "clean_block",
]
