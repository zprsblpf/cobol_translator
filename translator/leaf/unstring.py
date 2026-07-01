from __future__ import annotations

from translator.leaf.context import LeafCtx
from translator.leaf.expr import _java, _lvalue, _operand
from translator.leaf.string import _delimiter_expr


_UNSUPPORTED = {"WITH", "ON", "NOT", "COUNT", "DELIMITER", "POINTER", "OVERFLOW"}


def _temp_name(target: str) -> str:
    name = _java(target)
    return "__unstring" + name[:1].upper() + name[1:]


def translate_unstring(tokens: list[str], ctx: LeafCtx) -> tuple[list[str], bool]:
    """Translate conservative UNSTRING ... DELIMITED BY ... INTO ... statements."""
    if not tokens or tokens[0].upper() != "UNSTRING":
        return [], False
    u = [t.upper() for t in tokens]
    if any(t in _UNSUPPORTED for t in u):
        return [], False
    if len(tokens) < 7 or u[2:4] != ["DELIMITED", "BY"] or "INTO" not in u:
        return [], False
    into_i = u.index("INTO")
    if into_i != 5 or into_i + 1 >= len(tokens):
        return [], False

    source = _operand(tokens[1], ctx)
    delimiter = _delimiter_expr(tokens[4], ctx)
    targets = tokens[into_i + 1:]
    temp = _temp_name(targets[0])

    lines = [
        "{",
        f"    String[] {temp} = String.valueOf({source}).split(java.util.regex.Pattern.quote({delimiter}), -1);",
    ]
    for i, target in enumerate(targets):
        lines.append(f'    {_lvalue(target, ctx)} = {temp}.length > {i} ? {temp}[{i}] : "";')
    lines.append("}")
    return lines, True
