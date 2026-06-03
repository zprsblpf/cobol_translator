"""
COBOL 定列格式·行级列处理（单一正本）。

对应设计：docs/详细设计/步骤06-COBOL解析器列对齐与停用行修复设计.md。

职责：对 COBOL 物理行做停用/注释/调试判定与列区清洗，是结构定位与构块/解析的共同基础。
被 parser/cobol_parser.py 与 decompose/lines.py（薄重导出）复用，消除两套不一致的列处理。

列约定（AS/400 固定格式）：第1–6列序号区、第7列指示符、第8–72列代码区，第73+列行尾变更标记。
`clean_line` 取第7列起（含指示符列），使代码异常起于第7列的行不丢首字母；正常行（代码起于第8列）
多带的第7列空格会被下游 `^\\s*` / `.strip()` 吸收，无影响。
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


def is_debug(raw: str) -> bool:
    """指示列是否为 'D'（DEBUG 行，解析侧跳过）。"""
    return len(raw) > 6 and raw[6] == "D"


def indicator(raw: str) -> str:
    """返回指示列字符（第7列），不足则空格。"""
    return raw[6] if len(raw) > 6 else " "


def clean_line(raw: str) -> str:
    """取 clean_slice 列段（指示列+代码区），去行尾变更标记并 rstrip。

    列区取自切分文法正本 column_model.clean_slice（步骤08 去 6/72 魔数；默认 7–72 列）。
    保留指示列：注释行据此可识别（以 * / 开头）；代码异常起于第7列时首字母不丢。
    """
    from config import grammar_loader   # 延迟导入，避免 parser 加载期任何环依赖
    cs = grammar_loader.column_model()["clean_slice"]
    lo, hi = cs["start"] - 1, cs["end"]          # 1-based 列号 → 0-based 切片
    seg = raw[lo:hi] if len(raw) > hi else raw[lo:]
    seg = seg.rstrip("\n").rstrip("\r")
    seg = _CHANGE_TAG_RE.sub("", seg)
    return seg.rstrip()


def effective(raw: str) -> str | None:
    """该物理行的「有效代码行」（用于结构识别）；停用/注释/空行返回 None。

    注：不跳过 'D' 调试行（保持 decompose 既有行为）；调试行的跳过由 cobol_parser 自行处理。
    """
    if is_deactivated(raw) or is_comment(raw):
        return None
    line = clean_line(raw)
    return line if line.strip() else None


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
