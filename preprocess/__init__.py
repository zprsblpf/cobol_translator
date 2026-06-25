"""
相1「预处理」包（瘦门面）。

对应设计：docs/详细设计/步骤15-相1预处理独立成相设计.md。

对外暴露相1 的两件产物：
  ① 方言列处理原语（停用/注释/调试判定 + 列区清洗）—— 来自 columns（迁自 parser/cobol_columns）；
  ② 「干净行流」CleanSource（带原始行号回溯）—— 来自 line_stream。
唯一入口 `preprocess_file(path)`：读文件 → 构建干净行流（只做编排，不放逻辑）。
"""
from __future__ import annotations

from pathlib import Path

from preprocess.columns import (
    is_deactivated,
    is_comment,
    is_debug,
    indicator,
    clean_line,
    effective,
    clean_block,
)
from preprocess.line_stream import CleanLine, CleanSource, build

__all__ = [
    "is_deactivated", "is_comment", "is_debug", "indicator",
    "clean_line", "effective", "clean_block",
    "CleanLine", "CleanSource", "build", "preprocess_file",
]


def preprocess_file(path: str | Path) -> CleanSource:
    """相1 唯一入口：读源文件 → 构建「干净行流」CleanSource。"""
    with open(Path(path), encoding="utf-8", errors="replace") as f:
        raw_lines = f.readlines()
    return build(raw_lines)
