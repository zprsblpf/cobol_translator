"""
叶子数据项 → Java 字段声明（含 VALUE 初值、一/二维数组）。

对应设计：docs/详细设计/步骤03-WSAA块翻译设计.md。

设计思路（规范驱动，步骤05 §6.3）：
- 标量：`private <类型> 驼峰名 = <初值>;`，类型/初值/命名/样式串均经 config.spec_loader 取；
- 数组：OCCURS 维度由祖先链累计（dims），渲染 `T[]…`、`new T[d1][d2]…`（算法型，留在引擎）；
- 名字、初值、字段样式串：spec_loader.field_name / init_of / FIELD_DECL（删除原硬编码）。
"""
from __future__ import annotations

from parser.ws.model import WsNode
from config import spec_loader


def java_name(cobol: str) -> str:
    return spec_loader.field_name(cobol)


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
    else:
        atype = jt
        init = spec_loader.init_of(node)
    return [spec_loader.FIELD_DECL.format(type=atype, name=jn, init=init, comment=cm)]
