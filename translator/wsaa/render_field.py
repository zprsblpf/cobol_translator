"""
叶子数据项 → Java 字段声明（含 VALUE 初值、一/二维数组）。

对应设计：docs/详细设计/步骤03-WSAA块翻译设计.md。

设计思路（固化用户 WORKING-STORAGE 规范）：
- 标量：`private <类型> 驼峰名 = <初值>;`，初值取 VALUE 子句或类型默认值；
- 数组：OCCURS 维度由祖先链累计（dims），渲染 `T[]…`、`new T[d1][d2]…`；
- 名字 = cob名驼峰（复用 parser.variable_resolver._cobol_to_java_name，规范：cob名+wsaa）。
"""
from __future__ import annotations

from parser.variable_resolver import _cobol_to_java_name
from parser.ws.model import WsNode
from parser.ws import value as _value

_DEFAULTS = {"String": '""', "int": "0", "long": "0",
             "BigDecimal": "BigDecimal.ZERO", "boolean": "false"}


def java_name(cobol: str) -> str:
    return _cobol_to_java_name(cobol)


def _short(raw: str, n: int = 64) -> str:
    return raw if len(raw) <= n else raw[:n] + "…"


def render_field(node: WsNode, dims: list[int]) -> list[str]:
    """渲染一个叶子字段（dims=祖先+自身 OCCURS 维度列表）。"""
    jn = java_name(node.name)
    jt = node.java_type
    cm = f"  // COBOL: {_short(node.raw)}"
    if dims:
        atype = jt + "[]" * len(dims)
        init = "new " + jt + "".join(f"[{d}]" for d in dims)
        return [f"    private {atype} {jn} = {init};{cm}"]
    if node.has_value and node.value_raw:
        init = _value.java_init(node.value_raw, jt)
    else:
        init = _DEFAULTS.get(jt, '""')
    return [f"    private {jt} {jn} = {init};{cm}"]
