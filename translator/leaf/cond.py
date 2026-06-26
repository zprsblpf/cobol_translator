"""
相3 叶子翻译公用底座 —— 条件翻译（translate_condition / 比较式 / 数值取反）。

对应设计：docs/详细设计/步骤19-绞杀项3②IF迁visitor设计.md §3。
来源：原 translator/rules.py `_try_condition` / `_try_comparison` / `_negate_numeric`
      **原样迁址**（逻辑零改，仅把 ctx 注解由 rules.Ctx 改为 LeafCtx）。
被 IF（asg.visitor.visit_IfStmt）、rules（_sk_if / PERFORM-UNTIL / WHEN / BEGN-foreach 过滤）共用同一份
 → 条件产物逐字符一致（绞杀项3 比对闸基础）。依赖单向 leaf.cond → leaf.expr，不反向依赖 rules。
"""
from __future__ import annotations

import re

from translator.leaf.context import LeafCtx
from translator.leaf.expr import (
    _FIGURATIVE_BLANK, _FIGURATIVE_ZERO, _bd, _is_bigdecimal,
    _is_numeric_field, _is_string_field, _operand,
)


def translate_condition(tokens: list[str], ctx: LeafCtx) -> str | None:
    """翻译 IF / UNTIL / WHEN 条件为 Java 布尔表达式；失败返回 None。"""
    if not tokens:
        return None
    # 按 AND/OR 切分（保留连接符）
    parts: list[str] = []
    cur: list[str] = []
    for t in tokens:
        if t.upper() in ("AND", "OR"):
            parts.append(cur)
            parts.append([t.upper()])
            cur = []
        else:
            cur.append(t)
    parts.append(cur)

    out: list[str] = []
    for seg in parts:
        if len(seg) == 1 and seg[0] in ("AND", "OR"):
            out.append("&&" if seg[0] == "AND" else "||")
            continue
        expr = _try_comparison(seg, ctx)
        if expr is None:
            return None
        out.append(expr)
    return " ".join(out)


def _try_comparison(seg: list[str], ctx: LeafCtx) -> str | None:
    if not seg:
        return None
    # 定位关系运算符
    negate = False
    op_idx = -1
    op = ""
    for i, t in enumerate(seg):
        u = t.upper()
        if u == "NOT":
            negate = True
            continue
        if u in ("=", "EQUAL"):
            op, op_idx = "=", i
            break
        if u in (">", "GREATER"):
            op, op_idx = ">", i
            break
        if u in ("<", "LESS"):
            op, op_idx = "<", i
            break
        if u in (">=",):
            op, op_idx = ">=", i
            break
        if u in ("<=",):
            op, op_idx = "<=", i
            break
    if op_idx < 0:
        return None  # 88 条件名 / 复杂条件 → 交 LLM
    left = [t for t in seg[:op_idx] if t.upper() != "NOT"]
    right = seg[op_idx + 1:]
    if len(left) != 1 or len(right) < 1:
        return None
    lname = left[0]
    ljava = _operand(lname, ctx)
    rtok = right[0]
    ru = rtok.upper()

    # = SPACES / NOT = SPACES
    if ru in _FIGURATIVE_BLANK:
        base = f"StringUtils.isBlank({ljava})"
        if op != "=":
            return None
        return f"!{base}" if negate else base

    rjava = _operand(rtok, ctx)
    # 数值比较判定：左/右任一为已知数值字段，或右为数字字面量/figurative ZERO。
    # 右操作数为数值字段时，左侧若是「已知字符串字段」则不强转数值（防 String 与 long 误比）；
    # 左侧类型未知（如 IO 结构体 getter）则随右侧按数值处理（修 field>field 漏判 → 整块掉 LLM）。
    numeric = (
        _is_numeric_field(lname, ctx)
        or ru in _FIGURATIVE_ZERO
        or re.fullmatch(r"[+-]?\d+(\.\d+)?", rtok)
        or (_is_numeric_field(rtok, ctx) and not _is_string_field(lname, ctx))
    )
    if numeric:
        if _is_bigdecimal(lname, ctx) or _is_bigdecimal(rtok, ctx):
            j = f"{ljava}.compareTo({_bd(rjava)})"
            cmp = {"=": "== 0", ">": "> 0", "<": "< 0", ">=": ">= 0", "<=": "<= 0"}[op]
            base = f"{j} {cmp}"
            if negate:
                base = _negate_numeric(j, op)
            return f"({base})"
        jop = {"=": "==", ">": ">", "<": "<", ">=": ">=", "<=": "<="}[op]
        if negate:
            jop = {"==": "!=", ">": "<=", "<": ">=", ">=": "<", "<=": ">"}[jop]
        return f"{ljava} {jop} {rjava}"
    # 字符串比较
    if op != "=":
        return None
    base = f"{rjava}.equals({ljava})"
    return f"!{base}" if negate else base


def _negate_numeric(cmp_expr: str, op: str) -> str:
    inv = {"=": "!= 0", ">": "<= 0", "<": ">= 0", ">=": "< 0", "<=": "> 0"}[op]
    return f"{cmp_expr} {inv}"
