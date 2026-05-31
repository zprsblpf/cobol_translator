"""
88 条件项解析。

对应设计：docs/详细设计/步骤03-WSAA块翻译设计.md。

88 行形如：`88 IS-6PWB VALUES '6PWB' '2DWE' …`，描述「前一个数据项取这些值时为真」。
设计思路：把 88 解析成 Condition（名 + 取值列表 / 布尔），由 parser.ws.tree 挂到
它所修饰的兄弟数据项上；渲染期 translator.wsaa.render_condition 生成 isXxx() 布尔方法。
"""
from __future__ import annotations

import re

from parser.ws.model import Condition
from parser.ws import value as _value

_88_RE = re.compile(r"^\s*88\s+(\S+)", re.IGNORECASE)


def is_condition(entry: str) -> bool:
    return bool(_88_RE.match(entry))


def parse_condition(entry: str) -> Condition:
    """把一条 88 定义行解析为 Condition。"""
    name = _88_RE.match(entry).group(1).rstrip(".")
    _has, raw = _value.extract_value_raw(entry)
    lits = _value.literals(raw)
    # INDICATOR 布尔：VALUE B'0' / B'1'
    m = re.fullmatch(r"B'([01]+)'", raw.strip())
    if m:
        return Condition(name=name, values=[], is_boolean=True,
                         bool_value=("1" in m.group(1)))
    return Condition(name=name, values=lits)
