from __future__ import annotations

from translator.leaf.cond import translate_condition
from translator.leaf.context import LeafCtx
from translator.leaf.expr import _field_base, _lvalue, _operand
from translator.unsupported import unsupported_comment


RULE_ID = "LEAF.SEARCH.001"


def _unsupported(tokens: list[str], reason: str) -> tuple[list[str], bool]:
    raw = " ".join(tokens)
    return [unsupported_comment(RULE_ID, "leaf", raw, reason)], True


def _is_known_array(name: str, ctx: LeafCtx) -> bool:
    info = ctx.field_type_map.get(_field_base(name))
    return bool(info) and bool(info.get("is_array") or info.get("array_size"))


def translate_search(tokens: list[str], ctx: LeafCtx) -> tuple[list[str], bool]:
    """Translate the conservative SEARCH subset into a linear Java scan."""
    if not tokens or tokens[0].upper() != "SEARCH":
        return [], False

    u = [t.upper() for t in tokens]
    if len(tokens) < 6:
        return _unsupported(tokens, "SEARCH requires array, VARYING index, and WHEN condition")
    if u[1] == "ALL" or "AT" in u or "END-SEARCH" in u or u.count("WHEN") != 1:
        return _unsupported(tokens, "SEARCH form is outside the supported linear subset")
    if "VARYING" not in u:
        return _unsupported(tokens, "SEARCH without explicit VARYING index is unsupported")

    try:
        varying_i = u.index("VARYING")
        when_i = u.index("WHEN")
        table = tokens[1]
        index_name = tokens[varying_i + 1]
    except (ValueError, IndexError):
        return _unsupported(tokens, "SEARCH VARYING/WHEN clause is malformed")

    if varying_i != 2 or when_i <= varying_i + 1:
        return _unsupported(tokens, "SEARCH VARYING/WHEN clause is malformed")
    if not _is_known_array(table, ctx):
        return _unsupported(tokens, "SEARCH target is not a known array")

    cond = translate_condition(tokens[when_i + 1:], ctx)
    if cond is None:
        return _unsupported(tokens, "SEARCH WHEN condition is unsupported")

    index = _lvalue(index_name, ctx)
    array_expr = _operand(table, ctx)
    return [
        f"for ({index} = 1; {index} <= {array_expr}.length; {index}++) {{",
        f"    if ({cond}) {{",
        "        break;",
        "    }",
        "}",
    ], True
