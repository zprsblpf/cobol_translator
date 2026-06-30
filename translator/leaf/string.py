from __future__ import annotations

from translator.leaf.context import LeafCtx
from translator.leaf.expr import _lvalue, _operand


_UNSUPPORTED = {"WITH", "ON", "NOT"}


def _before_delimiter(source: str, delimiter: str) -> str:
    return f"String.valueOf({source}).split(java.util.regex.Pattern.quote({delimiter}), 2)[0]"


def _delimiter_expr(tok: str, ctx: LeafCtx) -> str:
    if tok.upper() == "SPACE":
        return '" "'
    return _operand(tok, ctx)


def translate_string(tokens: list[str], ctx: LeafCtx) -> tuple[list[str], bool]:
    """Translate supported COBOL STRING leaf statements."""
    if not tokens or tokens[0].upper() != "STRING":
        return [], False
    u = [t.upper() for t in tokens]
    if any(t in _UNSUPPORTED for t in u):
        return [], False
    if "INTO" not in u:
        return [], False
    into_i = u.index("INTO")
    if into_i <= 1 or into_i + 2 != len(tokens):
        return [], False

    target = tokens[into_i + 1]
    parts: list[str] = []
    i = 1
    while i < into_i:
        if i + 3 >= into_i:
            return [], False
        source = tokens[i]
        if u[i + 1] != "DELIMITED" or u[i + 2] != "BY":
            return [], False
        delimiter = tokens[i + 3]
        source_expr = _operand(source, ctx)
        if delimiter.upper() == "SIZE":
            parts.append(source_expr)
        else:
            parts.append(_before_delimiter(source_expr, _delimiter_expr(delimiter, ctx)))
        i += 4

    if not parts:
        return [], False
    return [f"{_lvalue(target, ctx)} = {' + '.join(parts)};"], True
