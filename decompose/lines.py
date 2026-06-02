"""
行级处理（设计文档 §3.1）。

职责：对 COBOL 物理行做停用/注释判定与列区清洗，是结构定位与构块的基础。
被 decompose/structure.py 与 decompose/blocks.py 复用。

实现已下沉至单一正本 parser/cobol_columns.py（步骤06）；本模块仅薄重导出，保持原有 API
（`is_deactivated`/`is_comment`/`indicator`/`clean_line`/`clean_block`/`_effective`）不变，
行为与原实现一致。详见 docs/详细设计/步骤06-COBOL解析器列对齐与停用行修复设计.md。
"""
from __future__ import annotations

from parser.cobol_columns import (
    is_deactivated,
    is_comment,
    indicator,
    clean_line,
    clean_block,
    effective as _effective,
)

__all__ = ["is_deactivated", "is_comment", "indicator", "clean_line", "clean_block", "_effective"]
