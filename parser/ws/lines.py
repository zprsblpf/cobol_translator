"""
WORKING-STORAGE 行级清洗与续行合并（拆解产物专用）。

对应设计：docs/详细设计/步骤03-WSAA块翻译设计.md。

输入是拆解器产出的 .cob 块（已去行号列 1–6，首列=原第 7 列指示符）：
- 指示列（每行首字符）= '*' 或 '/' → 注释行，丢弃；
- 新数据项以「两位层级号」开头（01/03/05/07/09/88/66/77）；
- 不以层级号开头的行 = 续行（如跨行 VALUE 列表、ASCENDING KEY 子句），并入上一条；
- 到 COPY 拷贝簿块 / SECTION. / DIVISION 残行即止（这些不属于变量定义）。

设计思路：纯行级、与具体 PIC 语法解耦；只负责把物理多行合并成「一条逻辑定义」，
具体字段解析交 parser.ws（_parse_entry）。
"""
from __future__ import annotations

import re
from pathlib import Path

_LEVEL_HEAD = re.compile(r"^\s*(\d{2})\s+")     # 新数据项：两位层级号开头
_SKIP_HEADER = re.compile(r"^(WORKING-STORAGE|LINKAGE)\s+SECTION", re.IGNORECASE)
_STOP = re.compile(r"^(COPY\b|.*\bSECTION\s*\.|.*\bDIVISION\b)", re.IGNORECASE)


def _is_comment(line: str) -> bool:
    """指示列（首字符）为 * 或 / → 注释。"""
    return line[:1] in ("*", "/")


def merge_entries(cob_file: str | Path) -> list[str]:
    """读取 WS 块，返回合并后的逻辑定义行列表（每条以层级号开头）。"""
    with open(cob_file, encoding="utf-8", errors="replace") as f:
        raw_lines = f.readlines()

    entries: list[str] = []
    current = ""
    for raw in raw_lines:
        line = raw.rstrip("\n").rstrip()
        if not line.strip():
            continue
        if _is_comment(line):
            continue
        s = line.strip()
        # WORKING-STORAGE / LINKAGE SECTION 头：跳过但不停止
        if _SKIP_HEADER.match(s):
            continue
        # 到拷贝簿块 / SECTION / DIVISION 残行：收尾并停止（这些不是变量定义）
        if _LEVEL_HEAD.match(line) is None and _STOP.match(s):
            break
        if _LEVEL_HEAD.match(line):
            if current:
                entries.append(current)
            current = line.strip()
        else:
            # 续行：并入上一条（保留一个空格分隔）
            if current:
                current += " " + line.strip()
    if current:
        entries.append(current)
    return entries
