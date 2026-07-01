from __future__ import annotations

from translator.leaf.context import LeafCtx
from translator.leaf.expr import _assign, _operand
from translator.unsupported import unsupported_comment


_COMPLEX_RULES = {
    "WITH": ("LEAF.UNSTRING.POINTER.001", "WITH POINTER is not yet deterministic"),
    "POINTER": ("LEAF.UNSTRING.POINTER.001", "WITH POINTER is not yet deterministic"),
    "TALLYING": ("LEAF.UNSTRING.COUNT.001", "TALLYING IN is not yet deterministic"),
    "COUNT": ("LEAF.UNSTRING.COUNT.001", "COUNT IN is not yet deterministic"),
    "DELIMITER": ("LEAF.UNSTRING.DELIMITER.001", "DELIMITER IN is not yet deterministic"),
    "ON": ("LEAF.UNSTRING.OVERFLOW.001", "ON OVERFLOW is not yet deterministic"),
    "NOT": ("LEAF.UNSTRING.OVERFLOW.001", "NOT ON OVERFLOW is not yet deterministic"),
    "OR": ("LEAF.UNSTRING.DELIMITER.002", "multiple delimiters are not yet deterministic"),
    "ALL": ("LEAF.UNSTRING.DELIMITER.002", "ALL/multiple delimiters are not yet deterministic"),
}


def _delimiter_expr(tok: str, ctx: LeafCtx) -> str:
    if tok.upper() == "SPACE":
        return '" "'
    return _operand(tok, ctx)


def translate_unstring(tokens: list[str], ctx: LeafCtx) -> tuple[list[str], bool]:
    """Translate supported COBOL UNSTRING leaf statements."""
    if not tokens or tokens[0].upper() != "UNSTRING":
        return [], False

    u = [t.upper() for t in tokens]
    for token, (rule_id, reason) in _COMPLEX_RULES.items():
        if token in u:
            return [unsupported_comment(rule_id, "leaf", " ".join(tokens), reason)], True

    if len(tokens) < 7 or u[2] != "DELIMITED" or u[3] != "BY":
        return [], False
    if "INTO" not in u:
        return [], False

    into_i = u.index("INTO")
    if into_i != 5 or into_i + 1 >= len(tokens):
        return [], False

    delimiter = tokens[4]
    if delimiter.upper() == "SIZE":
        return [], False

    targets = tokens[into_i + 1:]
    if not targets:
        return [], False

    limit = max(2, len(targets))
    split_line = (
        f"String[] __unstringParts = String.valueOf({_operand(tokens[1], ctx)})."
        f"split(java.util.regex.Pattern.quote({_delimiter_expr(delimiter, ctx)}), {limit});"
    )
    lines = ["{", f"    {split_line}"]
    for i, target in enumerate(targets):
        value = f'__unstringParts.length > {i} ? __unstringParts[{i}] : ""'
        lines.append(f"    {_assign(target, value, ctx)}")
    lines.append("}")
    return lines, True
