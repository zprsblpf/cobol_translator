"""
相3 叶子翻译公用底座 —— MOVE 动词译器（translate_move）。

对应设计：docs/详细设计/步骤18-绞杀项3①MOVE迁visitor设计.md §3.2、§4.3。
来源：原 translator/rules.py `_t_move` **原样迁址**（逻辑零改）。
rules 委托调用、相3 visitor（asg/visitor.LeafJavaVisitor）共调同一份 → 产物逐字符一致（绞杀项3 比对闸基础）。
"""
from __future__ import annotations

import re

from translator.leaf.context import LeafCtx
from translator.leaf.expr import (
    _FIGURATIVE_BLANK, _FIGURATIVE_ZERO, _assign, _bd, _is_bigdecimal,
    _is_numeric_field, _operand, _struct_obj, _struct_prefix,
)


def translate_move(toks: list[str], ctx: LeafCtx) -> tuple[list[str], bool]:
    # MOVE src TO dst1 [dst2 ...]
    if "TO" not in [t.upper() for t in toks]:
        return [], False
    ti = [t.upper() for t in toks].index("TO")
    src_toks = toks[1:ti]
    dsts = toks[ti + 1:]
    if len(src_toks) != 1 or not dsts:
        return [], False
    src = src_toks[0]
    su = src.upper()
    sp_src = _struct_prefix(src, ctx)
    src_is_params = bool(sp_src and sp_src[1] == "PARAMS")
    lines: list[str] = []
    for dst in dsts:
        sp_dst = _struct_prefix(dst, ctx)
        # 调用约定吸收（步骤10）：FUNCTION/FORMAT 不是真实字段，一律不生成 setter。
        #   · MOVE READR TO ELPO-FUNCTION → 仅记 struct_function（供 CALL 吸收功能码）。
        #   · MOVE ELPOREC TO ELPO-FORMAT → 仅校验记录格式，Java 侧无对应，直接吞掉。
        if sp_dst and sp_dst[1] in ("FUNCTION", "FORMAT"):
            if sp_dst[1] == "FUNCTION":
                ctx.struct_function[sp_dst[0]] = su.strip("'\"")
            continue
        # 决策 C（步骤10）：组级 params 互拷 MOVE xxx-PARAMS TO yyy-PARAMS →
        #   BeanUtils.copyProperties(src, dst)：运行时按同名属性互拷、名字对不上的自动忽略，
        #   恰好等价「同名字段互拷」，且无需拷贝簿字段表（字段不在盘上时静态无法逐字段枚举）。
        if src_is_params and sp_dst and sp_dst[1] == "PARAMS":
            lines.append(f"BeanUtils.copyProperties("
                         f"{_struct_obj(sp_src[0], ctx)}, {_struct_obj(sp_dst[0], ctx)});")
            continue
        if su in _FIGURATIVE_BLANK:
            val = '""' if not _is_numeric_field(dst, ctx) else ("BigDecimal.ZERO" if _is_bigdecimal(dst, ctx) else "0")
        elif su in _FIGURATIVE_ZERO:
            val = "BigDecimal.ZERO" if _is_bigdecimal(dst, ctx) else "0"
        else:
            val = _operand(src, ctx)
            if _is_bigdecimal(dst, ctx) and re.fullmatch(r"[+-]?\d+(\.\d+)?", val):
                val = _bd(val)
        lines.append(_assign(dst, val, ctx))
    return lines, True
