"""
相3 叶子翻译公用底座 —— 算术类叶子动词（ADD / SUBTRACT / MULTIPLY / DIVIDE / COMPUTE）。

对应设计：docs/详细设计/步骤22-绞杀项3⑤算术赋值动词迁visitor设计.md §2[文件]、§3。
设计思路：5 个算术译器 + 私有助手 _arith_val 自 translator/rules.py **原样迁址**（逻辑零改，
仅把 ctx 注解由 rules.Ctx 改为 LeafCtx），下沉为公用底座——rules 委托（再导入 5 译器，
_dispatch_leaf 调用点零改）、相3 visit_Leaf 经 translate_arith 共调 → 两路产物逐字符一致。
分派器 translate_arith 复刻旧 _dispatch_leaf 的 try/except (ValueError, IndexError) 兜底同形。

本文件另持**赋值+算术统一入口** translate_arith_assign（host 于此、import assign.translate_assign）：
依次试 translate_assign → translate_arith；两译器 verb 集互斥（{INITIALIZE,SET}∩{ADD…COMPUTE}=∅），
任一 token 串至多一路命中、另一路即 ([],False)，与旧 _dispatch_leaf 按 verb 单路路由产物逐字符一致。
供相3 visit_Leaf / 比对脚本单点调用（绞杀项3⑤）。

复用 leaf.expr 的 operand/lvalue/判型/bd 底座；ctx 仅读 field_type_map（在 LeafCtx 契约）。
依赖单向：rules → leaf.arith → leaf.assign / leaf.expr，无环。
"""
from __future__ import annotations

import re

from translator.leaf.assign import translate_assign
from translator.leaf.context import LeafCtx
from translator.leaf.expr import _bd, _is_bigdecimal, _lvalue, _operand


def _arith_val(name: str, expr: str, ctx: LeafCtx) -> str:
    return _bd(expr) if _is_bigdecimal(name, ctx) and re.fullmatch(r"[+-]?\d+(\.\d+)?", expr) else expr


def _t_add(toks: list[str], ctx: LeafCtx) -> tuple[list[str], bool]:
    # ADD a TO b [GIVING c]
    u = [t.upper() for t in toks]
    if "TO" not in u:
        return [], False
    ti = u.index("TO")
    a_toks = toks[1:ti]
    if len(a_toks) != 1:
        return [], False
    a = a_toks[0]
    rest = toks[ti + 1:]
    ru = [t.upper() for t in rest]
    if "GIVING" in ru:
        gi = ru.index("GIVING")
        b = rest[gi - 1]
        c = rest[gi + 1]
        if _is_bigdecimal(c, ctx):
            return [f"{_lvalue(c, ctx)} = {_operand(b, ctx)}.add({_arith_val(c, _operand(a, ctx), ctx)});"], True
        return [f"{_lvalue(c, ctx)} = {_operand(b, ctx)} + {_operand(a, ctx)};"], True
    b = rest[0]
    if _is_bigdecimal(b, ctx):
        return [f"{_lvalue(b, ctx)} = {_operand(b, ctx)}.add({_arith_val(b, _operand(a, ctx), ctx)});"], True
    return [f"{_lvalue(b, ctx)} += {_operand(a, ctx)};"], True


def _t_subtract(toks: list[str], ctx: LeafCtx) -> tuple[list[str], bool]:
    # SUBTRACT a FROM b [GIVING c]
    u = [t.upper() for t in toks]
    if "FROM" not in u:
        return [], False
    fi = u.index("FROM")
    a_toks = toks[1:fi]
    if len(a_toks) != 1:
        return [], False
    a = a_toks[0]
    rest = toks[fi + 1:]
    ru = [t.upper() for t in rest]
    if "GIVING" in ru:
        gi = ru.index("GIVING")
        b = rest[gi - 1]
        c = rest[gi + 1]
        if _is_bigdecimal(c, ctx):
            return [f"{_lvalue(c, ctx)} = {_operand(b, ctx)}.subtract({_arith_val(c, _operand(a, ctx), ctx)});"], True
        return [f"{_lvalue(c, ctx)} = {_operand(b, ctx)} - {_operand(a, ctx)};"], True
    b = rest[0]
    if _is_bigdecimal(b, ctx):
        return [f"{_lvalue(b, ctx)} = {_operand(b, ctx)}.subtract({_arith_val(b, _operand(a, ctx), ctx)});"], True
    return [f"{_lvalue(b, ctx)} -= {_operand(a, ctx)};"], True


def _t_multiply(toks: list[str], ctx: LeafCtx) -> tuple[list[str], bool]:
    # MULTIPLY a BY b [GIVING c]
    u = [t.upper() for t in toks]
    if "BY" not in u:
        return [], False
    bi = u.index("BY")
    a = toks[1:bi]
    if len(a) != 1:
        return [], False
    a = a[0]
    rest = toks[bi + 1:]
    ru = [t.upper() for t in rest]
    if "GIVING" in ru:
        gi = ru.index("GIVING")
        b = rest[gi - 1]
        c = rest[gi + 1]
    else:
        b = c = rest[0]
    if _is_bigdecimal(c, ctx):
        return [f"{_lvalue(c, ctx)} = {_operand(b, ctx)}.multiply({_arith_val(c, _operand(a, ctx), ctx)});"], True
    return [f"{_lvalue(c, ctx)} = {_operand(b, ctx)} * {_operand(a, ctx)};"], True


def _t_divide(toks: list[str], ctx: LeafCtx) -> tuple[list[str], bool]:
    # DIVIDE a INTO b [GIVING c] | DIVIDE a BY b GIVING c [ROUNDED]
    u = [t.upper() for t in toks]
    rounded = "ROUNDED" in u
    if "INTO" in u:
        ki = u.index("INTO")
        divisor = toks[1]          # a INTO b: a 是除数
        rest = toks[ki + 1:]
    elif "BY" in u:
        ki = u.index("BY")
        dividend_pre = toks[1:ki]
        rest = toks[ki + 1:]
        if len(dividend_pre) != 1:
            return [], False
        # a BY b: a/b
        dividend = dividend_pre[0]
        ru = [t.upper() for t in rest]
        divisor = rest[0]
        if "GIVING" in ru:
            c = rest[ru.index("GIVING") + 1]
        else:
            c = dividend
        if _is_bigdecimal(c, ctx):
            scale = "2" if rounded else "2"
            return [f"{_lvalue(c, ctx)} = {_operand(dividend, ctx)}.divide({_operand(divisor, ctx)}, {scale}, RoundingMode.HALF_UP);"], True
        return [f"{_lvalue(c, ctx)} = {_operand(dividend, ctx)} / {_operand(divisor, ctx)};"], True
    else:
        return [], False
    # INTO 形式
    ru = [t.upper() for t in rest]
    b = rest[0]
    c = rest[ru.index("GIVING") + 1] if "GIVING" in ru else b
    if _is_bigdecimal(c, ctx):
        return [f"{_lvalue(c, ctx)} = {_operand(b, ctx)}.divide({_operand(divisor, ctx)}, 2, RoundingMode.HALF_UP);"], True
    return [f"{_lvalue(c, ctx)} = {_operand(b, ctx)} / {_operand(divisor, ctx)};"], True


def _t_compute(toks: list[str], ctx: LeafCtx) -> tuple[list[str], bool]:
    # COMPUTE dst [ROUNDED] = expr  （仅固化整型；BigDecimal 表达式交 LLM）
    u = [t.upper() for t in toks]
    if "=" not in u:
        return [], False
    eq = u.index("=")
    dst_toks = [t for t in toks[1:eq] if t.upper() != "ROUNDED"]
    if len(dst_toks) != 1:
        return [], False
    dst = dst_toks[0]
    if _is_bigdecimal(dst, ctx):
        return [], False  # BigDecimal 中缀转链式不可靠 → LLM
    expr_toks = toks[eq + 1:]
    parts = []
    for t in expr_toks:
        if t in ("+", "-", "*", "/", "(", ")"):
            parts.append(t)
        else:
            parts.append(_operand(t, ctx))
    return [f"{_lvalue(dst, ctx)} = {' '.join(parts)};"], True


_ARITH = {"ADD": _t_add, "SUBTRACT": _t_subtract, "MULTIPLY": _t_multiply,
          "DIVIDE": _t_divide, "COMPUTE": _t_compute}


def translate_arith(tokens: list[str], ctx: LeafCtx) -> tuple[list[str], bool]:
    """算术类叶子动词单点分派：按 tokens[0] 路由 5 算术译器，非此五类 → ([], False)。

    复刻旧 rules._dispatch_leaf 的 try/except (ValueError, IndexError) 兜底 → 与旧路同形。
    """
    if not tokens:
        return [], False
    fn = _ARITH.get(tokens[0].upper())
    if not fn:
        return [], False
    try:
        return fn(tokens, ctx)
    except (ValueError, IndexError):
        return [], False


def translate_arith_assign(tokens: list[str], ctx: LeafCtx) -> tuple[list[str], bool]:
    """赋值+算术统一入口（步骤22 绞杀项3⑤）：相3 visit_Leaf / 比对脚本单点调用。

    依次试 translate_assign（INITIALIZE/SET）→ translate_arith（ADD/SUBTRACT/MULTIPLY/DIVIDE/COMPUTE）。
    两译器 verb 集互斥 → 任一 token 串至多一路命中、另一路即 ([],False)，
    与旧 rules._dispatch_leaf 按 verb 单路路由的产物**逐字符一致**（含 ([],False) 兜底）。
    """
    lines, ok = translate_assign(tokens, ctx)
    return (lines, ok) if ok else translate_arith(tokens, ctx)
