"""
parser.ws —— WORKING-STORAGE 块结构解析（确定性，无 LLM）。

对应设计：docs/详细设计/步骤03-WSAA块翻译设计.md。
对外暴露 parse_ws(cob_file) -> list[WsNode]（01 级森林，已回填类型/宽度/88 条件）。
内部分工：lines（清洗合并）→ entry/conditions（逐条解析）→ tree（建树+回填）。
"""
from __future__ import annotations

from pathlib import Path

from parser.ws.lines import merge_entries
from parser.ws.tree import build
from parser.ws.model import WsNode, Condition

__all__ = ["parse_ws", "WsNode", "Condition"]


def parse_ws(cob_file: str | Path) -> list[WsNode]:
    """解析 WORKING-STORAGE 拆解块，返回 WsNode 森林。"""
    return build(merge_entries(cob_file))
