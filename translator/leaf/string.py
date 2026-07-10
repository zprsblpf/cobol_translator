from __future__ import annotations

from translator.leaf.context import LeafCtx
from translator.leaf.expr import _lvalue, _operand
from translator.unsupported import unsupported_comment


_COMPLEX_RULES = {
    "WITH": ("LEAF.STRING.POINTER.001", "WITH POINTER is not yet deterministic"),
    "ON": ("LEAF.STRING.OVERFLOW.001", "ON OVERFLOW is not yet deterministic"),
    "NOT": ("LEAF.STRING.OVERFLOW.001", "NOT ON OVERFLOW is not yet deterministic"),
}


def _before_delimiter(source: str, delimiter: str) -> str:
    return f"String.valueOf({source}).split(java.util.regex.Pattern.quote({delimiter}), 2)[0]"


def _delimiter_expr(tok: str, ctx: LeafCtx) -> str:
    if tok.upper() == "SPACE":
        return '" "'
    return _operand(tok, ctx)


def translate_string(tokens: list[str], ctx: LeafCtx) -> tuple[list[str], bool]:
    """Translate supported COBOL STRING leaf statements.

    支持：DELIMITED BY SIZE/BY 字面量/BY 变量、逗号分隔、单 INTO。
    不支持：多 INTO、WITH/ON/NOT 等子句。
    """
    if not tokens or tokens[0].upper() != "STRING":
        return [], False
    u = [t.upper() for t in tokens]
    for token, (rule_id, reason) in _COMPLEX_RULES.items():
        if token in u:
            return [unsupported_comment(rule_id, "leaf", " ".join(tokens), reason)], True
    if "INTO" not in u:
        return [], False
    into_i = u.index("INTO")

    target = tokens[into_i + 1]
    # 检查 INTO 后是否有多余 token（多目标 INTO 不支持）
    remaining = tokens[into_i + 2:]
    if remaining and remaining != [","]:
        return [], False
    parts: list[str] = []
    i = 1
    while i < into_i:
        # 跳过逗号（COBOL 可选分隔符）
        if tokens[i] == ",":
            i += 1
            continue
        # 跳过 DELIMITED BY 前的逗号（如 'A', DELIMITED BY SIZE）
        if i + 1 < into_i and tokens[i] == ",":
            i += 1
            continue
        source = tokens[i]
        # 如果下一个 token 不是 DELIMITED，假定默认为 DELIMITED BY SIZE
        if i + 1 < into_i and u[i + 1] == "DELIMITED":
            if i + 2 >= into_i or u[i + 2] != "BY":
                return [], False
            delimiter = tokens[i + 3] if i + 3 < into_i else ""
            source_expr = _operand(source, ctx)
            if delimiter and delimiter.upper() == "SIZE":
                parts.append(source_expr)
            elif delimiter:
                parts.append(_before_delimiter(source_expr, _delimiter_expr(delimiter, ctx)))
            else:
                parts.append(source_expr)
            i += 4
        else:
            # 无 DELIMITED BY → 默认为 DELIMITED BY SIZE
            parts.append(_operand(source, ctx))
            i += 1

    if not parts:
        return [], False
    return [f"{_lvalue(target, ctx)} = {' + '.join(parts)};"], True
