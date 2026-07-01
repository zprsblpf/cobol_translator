from __future__ import annotations

from translator.leaf.context import LeafCtx
from translator.leaf.expr import _lvalue, _operand


_BLOCKED = {"BEFORE", "AFTER", "CONVERTING"}
_REPLACING_MODES = {"ALL", "FIRST", "LEADING"}


def _string_operand(tok: str, ctx: LeafCtx) -> str | None:
    u = tok.upper()
    if u in {"SPACE", "SPACES"}:
        return '" "'
    if u in {"ZERO", "ZEROS", "ZEROES"}:
        return '"0"'
    if u in {"LOW-VALUE", "LOW-VALUES", "HIGH-VALUE", "HIGH-VALUES"}:
        return None
    return _operand(tok, ctx)


def _count_all(source: str, needle: str) -> str:
    return (
        f"({needle}.isEmpty() ? 0 : "
        f"({source}.length() - {source}.replace({needle}, \"\").length()) / {needle}.length())"
    )


def _replace_first(source: str, needle: str, repl: str) -> str:
    return (
        f"{source}.replaceFirst(java.util.regex.Pattern.quote({needle}), "
        f"java.util.regex.Matcher.quoteReplacement({repl}))"
    )


def _replace_leading(source: str, needle: str, repl: str) -> str:
    return (
        f"{source}.replaceFirst(\"^(?:\" + java.util.regex.Pattern.quote({needle}) + \")+\", "
        f"java.util.regex.Matcher.quoteReplacement({repl}))"
    )


def translate_inspect(tokens: list[str], ctx: LeafCtx) -> tuple[list[str], bool]:
    """Translate supported COBOL INSPECT leaf statements."""
    if not tokens or tokens[0].upper() != "INSPECT":
        return [], False

    u = [t.upper() for t in tokens]
    if len(tokens) < 4 or any(t in _BLOCKED for t in u):
        return [], False

    source = f"String.valueOf({_operand(tokens[1], ctx)})"
    target = _lvalue(tokens[1], ctx)

    if u[2] == "TALLYING":
        if len(tokens) == 6 and u[4] == "FOR" and u[5] == "CHARACTERS":
            return [f"{_lvalue(tokens[3], ctx)} += {source}.length();"], True
        if len(tokens) == 7 and u[4] == "FOR" and u[5] == "ALL":
            needle = _string_operand(tokens[6], ctx)
            if needle is None:
                return [], False
            return [f"{_lvalue(tokens[3], ctx)} += {_count_all(source, needle)};"], True
        return [], False

    if u[2] == "REPLACING":
        if len(tokens) != 7 or u[3] not in _REPLACING_MODES or u[5] != "BY":
            return [], False
        needle = _string_operand(tokens[4], ctx)
        repl = _string_operand(tokens[6], ctx)
        if needle is None or repl is None:
            return [], False
        if u[3] == "ALL":
            expr = f"{source}.replace({needle}, {repl})"
        elif u[3] == "FIRST":
            expr = _replace_first(source, needle, repl)
        else:
            expr = _replace_leading(source, needle, repl)
        return [f"{target} = {expr};"], True

    return [], False
