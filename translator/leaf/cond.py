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
    """翻译 IF / UNTIL / WHEN 条件为 Java 布尔表达式；失败返回 None。

    支持 COBOL 隐式操作数简写：`IF A = 'X' OR 'Y'` → `IF A = 'X' OR A = 'Y'`。
    """
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
    last_left: str | None = None    # 上一个比较的左操作数（支持隐式复用）
    last_op: str | None = None      # 上一个比较的操作符

    for seg in parts:
        if len(seg) == 1 and seg[0] in ("AND", "OR"):
            out.append("&&" if seg[0] == "AND" else "||")
            continue
        # 去除首尾括号（括号包裹的 OR 列表：(... OR ... )）
        while seg and seg[0] == "(":
            seg = seg[1:]
        while seg and seg[-1] == ")":
            seg = seg[:-1]
        if not seg:
            continue
        # 尝试完整解析
        expr = _try_comparison(seg, ctx)
        if expr is not None:
            out.append(expr)
            # 记录左操作数和操作符供后续隐式复用
            _left, _op = _extract_comparison_info(seg)
            if _left:
                last_left = _left
                last_op = _op
            continue
        # 完整解析失败 → 尝试隐式操作数（COBOL 简写：A = 'X' OR 'Y'）
        if last_left is not None and last_op is not None and len(seg) >= 1:
            # 在 seg 前补上左操作数和操作符重试
            augmented = [last_left, last_op] + seg
            expr = _try_comparison(augmented, ctx)
            if expr is not None:
                out.append(expr)
                continue
        return None
    return " ".join(out)


def _extract_comparison_info(seg: list[str]) -> tuple[str | None, str | None]:
    """从比较分段中提取左操作数和操作符（用于隐式复用）。"""
    for i, t in enumerate(seg):
        u = t.upper()
        if u == "NOT":
            continue
        if u in ("=", ">", "<", ">=", "<=", "EQUAL", "GREATER", "LESS"):
            left_tokens = [x for x in seg[:i] if x.upper() != "NOT"]
            if left_tokens:
                return left_tokens[0], u
    return None, None


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
        # 尝试 88 条件名展开
        eighty_eights = getattr(ctx, 'eighty_eights', None) or {}
        cond_name = None
        negated = False
        if len(seg) == 1:
            cond_name = seg[0].upper()
        elif len(seg) == 2 and seg[0].upper() == "NOT":
            cond_name = seg[1].upper()
            negated = True
        if cond_name and cond_name in eighty_eights:
            info = eighty_eights[cond_name]
            holder = info["holder"]
            vals = info["values"]
            if vals:
                ljava = _operand(holder, ctx)
                rjava = _operand(vals[0], ctx)
                base = f"{rjava}.equals({ljava})"
                return f"!{base}" if negated else base
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
