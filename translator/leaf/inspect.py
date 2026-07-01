from __future__ import annotations

from translator.leaf.context import LeafCtx
from translator.leaf.expr import _lvalue, _operand


def _literal_operand(tok: str, ctx: LeafCtx) -> str | None:
    if tok.startswith("'") or tok.startswith('"'):
        return _operand(tok, ctx)
    if tok.upper() == "SPACE":
        return '" "'
    return None


def translate_inspect(tokens: list[str], ctx: LeafCtx) -> tuple[list[str], bool]:
    """Translate conservative INSPECT REPLACING/TALLYING leaf statements."""
    if not tokens or tokens[0].upper() != "INSPECT":
        return [], False
    u = [t.upper() for t in tokens]
    if len(tokens) == 7 and u[2:4] == ["REPLACING", "ALL"] and u[5] == "BY":
        src = _lvalue(tokens[1], ctx)
        old = _literal_operand(tokens[4], ctx)
        new = _literal_operand(tokens[6], ctx)
        if old is None or new is None:
            return [], False
        return [f"{src} = String.valueOf({src}).replace({old}, {new});"], True

    if len(tokens) == 7 and u[2] == "TALLYING" and u[4:6] == ["FOR", "ALL"]:
        source = _operand(tokens[1], ctx)
        counter = _lvalue(tokens[3], ctx)
        needle = _literal_operand(tokens[6], ctx)
        if needle is None:
            return [], False
        return [
            f"{counter} += (String.valueOf({source}).length() - "
            f"String.valueOf({source}).replace({needle}, \"\").length()) / {needle}.length();"
        ], True

    return [], False
