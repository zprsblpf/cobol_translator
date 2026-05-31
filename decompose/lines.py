"""
行级处理（设计文档 §3.1）。

职责：对 COBOL 物理行做停用/注释判定与列区清洗，是结构定位与构块的基础。
被 decompose/structure.py 与 decompose/blocks.py 复用。
"""
from __future__ import annotations

import re

_CHANGE_TAG_RE = re.compile(r"<[A-Za-z0-9]+>\s*$")   # 行尾变更标记 <CSV001> 等


def is_deactivated(raw: str) -> bool:
    """第1–6列是否为 '!!!!!!'（停用旧代码）。"""
    return raw[:6] == "!!!!!!"


def is_comment(raw: str) -> bool:
    """指示列（第7列，0-based 索引6）是否为注释标记 '*' 或 '/'。"""
    return len(raw) > 6 and raw[6] in ("*", "/")


def indicator(raw: str) -> str:
    """返回指示列字符（第7列），不足则空格。"""
    return raw[6] if len(raw) > 6 else " "


def clean_line(raw: str) -> str:
    """取第7–72列（指示列+代码区），去行尾变更标记并 rstrip。

    保留指示列：注释行据此可识别（以 * / 开头）。
    """
    seg = raw[6:72] if len(raw) > 72 else raw[6:]
    seg = seg.rstrip("\n").rstrip("\r")
    seg = _CHANGE_TAG_RE.sub("", seg)
    return seg.rstrip()


def clean_block(raw_lines: list[str], start_idx: int, end_idx: int) -> str:
    """对原文件 [start_idx, end_idx)（0-based 半开区间）逐行清洗，返回块正文。

    - 丢弃 '!!!!!!' 停用行与空行；
    - 保留 '*' 注释行；
    - 其余取代码区。
    """
    out: list[str] = []
    for i in range(start_idx, end_idx):
        raw = raw_lines[i]
        if is_deactivated(raw):
            continue
        line = clean_line(raw)
        if line.strip() == "":
            continue
        out.append(line)
    return "\n".join(out)


def _effective(raw: str) -> str | None:
    """返回该物理行的「有效代码行」（用于结构识别）；停用/注释/空行返回 None。"""
    if is_deactivated(raw):
        return None
    if is_comment(raw):
        return None
    line = clean_line(raw)
    return line if line.strip() else None
