"""
单条数据项定义行 → WsNode（字段抽取）。

对应设计：docs/详细设计/步骤03-WSAA块翻译设计.md。

设计思路：合并后的一条逻辑定义行（已去注释/续行），抽取 level/name/pic/comp/
occurs/redefines/value/indicator/filler。复用翻译线的正则风格，PIC 用宽松单 token
抓取以兼容数字编辑 PIC（Z(14)9.99 等）。88 不在此处理（见 conditions）。
"""
from __future__ import annotations

import re

from parser.ws.model import WsNode
from parser.ws import value as _value

_LEVEL = re.compile(r"^\s*(\d{2})\s+(\S+)")
_PIC = re.compile(r"\bPIC(?:TURE)?\s+(\S+)", re.IGNORECASE)
_OCCURS = re.compile(r"\bOCCURS\s+(\d+)", re.IGNORECASE)
_REDEF = re.compile(r"\bREDEFINES\s+(\S+)", re.IGNORECASE)
# COMP 必须是独立子句（前为空白），避免误匹配名字里的 COMP（如 WSAA-SKIP-COMP）
_COMP = re.compile(r"(?<=\s)(COMP-3|COMP)\b", re.IGNORECASE)
_INDIC = re.compile(r"\bINDICATOR\b", re.IGNORECASE)


def parse_entry(entry: str) -> WsNode | None:
    """解析一条非 88 数据项定义行。无法识别层级 → None。"""
    m = _LEVEL.match(entry)
    if not m:
        return None
    level = int(m.group(1))
    name = m.group(2).rstrip(".")
    is_filler = name.upper() == "FILLER"

    pm = _PIC.search(entry)
    pic = pm.group(1).rstrip(".") if pm else ""

    om = _OCCURS.search(entry)
    occurs = int(om.group(1)) if om else 0

    rm = _REDEF.search(entry)
    redefines = rm.group(1).rstrip(".") if rm else ""

    cm = _COMP.search(entry)
    comp = cm.group(1).upper() if cm else ""

    has_value, value_raw = _value.extract_value_raw(entry)

    return WsNode(
        level=level, name=name, pic=pic, comp=comp, occurs=occurs,
        redefines=redefines, value_raw=value_raw, has_value=has_value,
        is_filler=is_filler, is_indicator=bool(_INDIC.search(entry)),
        raw=entry,
    )
