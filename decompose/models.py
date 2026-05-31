"""
拆解数据结构。

对应设计文档：docs/详细设计/步骤02-…设计.md（§2b 包结构）。
唯一数据结构 Block：表示一个拆解出来的代码块（META / WORKING-STORAGE / SECTION）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Block:
    """一个拆解出来的代码块（META / WORKING-STORAGE / SECTION）。"""
    program: str
    source_file: str
    block_index: int
    block_name: str
    block_type: str          # "META" | "WORKING-STORAGE" | "SECTION"
    start_line: int          # 原文件物理行号(1-based)，META 为 0
    end_line: int
    raw_text: str            # 清洗后的块正文（= 切片文件内容）
    # 预留字段（本步留空，后续步骤回填）
    params_in: Any = None
    params_out: Any = None
    calls: Any = None
    logic: Any = None
    java_code: Any = None
    # META 专用扩展（仅 META 块使用）
    extra: dict = field(default_factory=dict)
