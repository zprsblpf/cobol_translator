"""
相3 叶子翻译公用底座 —— 赋值类叶子动词（INITIALIZE / SET）。

对应设计：docs/详细设计/步骤22-绞杀项3⑤算术赋值动词迁visitor设计.md §2[文件]、§3。
设计思路：INITIALIZE（结构体/字段重置）与 SET（数值/字段赋值）译器自 translator/rules.py
**原样迁址**（逻辑零改，仅把 ctx 注解由 rules.Ctx 改为 LeafCtx），下沉为公用底座——rules 委托
（再导入 _t_initialize/_t_set，_dispatch_leaf 调用点零改）、相3 visit_Leaf 经 translate_assign 共调
→ 两路产物逐字符一致（绞杀项3 比对闸基础）。
分派器 translate_assign 复刻旧 _dispatch_leaf 的 try/except (ValueError, IndexError) 兜底同形。
复用 leaf.expr 的 struct 命名/判型/赋值底座；ctx 仅读 field_type_map + struct 命名字段（均在 LeafCtx 契约）。
依赖单向：rules / arith → leaf.assign → leaf.expr，无环。
"""
from __future__ import annotations

from translator.leaf.context import LeafCtx
from translator.leaf.expr import (
    _assign, _is_bigdecimal, _is_field, _is_numeric_field, _operand,
    _struct_cls, _struct_obj, _struct_prefix,
)


def _t_initialize(toks: list[str], ctx: LeafCtx) -> tuple[list[str], bool]:
    """INITIALIZE dst1 [dst2 ...] → 重置为默认值。
      · 结构体参数（X-PARAMS）→ obj = new XParams();（与 MOVE SPACES 重置一致）
      · 数值字段 → 0 / BigDecimal.ZERO；字符串字段 → ""
      · 带 REPLACING/含未识别目标 → 整体交 LLM（避免半翻）。
    """
    dsts = toks[1:]
    if not dsts:
        return [], False
    lines: list[str] = []
    for dst in dsts:
        if dst.upper() in ("REPLACING", "TO", "VALUE", "ALL"):
            return [], False
        sp = _struct_prefix(dst, ctx)
        if sp and sp[1] == "PARAMS":
            lines.append(f"{_struct_obj(sp[0], ctx)} = new {_struct_cls(sp[0], ctx)}();")
        elif _is_field(dst, ctx):
            if _is_bigdecimal(dst, ctx):
                val = "BigDecimal.ZERO"
            elif _is_numeric_field(dst, ctx):
                val = "0"
            else:
                val = '""'
            lines.append(_assign(dst, val, ctx))
        else:
            return [], False
    return lines, True


def _t_set(toks: list[str], ctx: LeafCtx) -> tuple[list[str], bool]:
    # SET a [b] TO value  （仅处理 TO 数值/字段；TO TRUE/ON 等交 LLM）
    u = [t.upper() for t in toks]
    if "TO" not in u:
        return [], False
    ti = u.index("TO")
    targets = toks[1:ti]
    val_toks = toks[ti + 1:]
    if len(val_toks) != 1 or not targets:
        return [], False
    vu = val_toks[0].upper()
    if vu in ("TRUE", "FALSE", "ON", "OFF"):
        return [], False
    val = _operand(val_toks[0], ctx)
    return [_assign(t, val, ctx) for t in targets], True


_ASSIGN = {"INITIALIZE": _t_initialize, "SET": _t_set}


def translate_assign(tokens: list[str], ctx: LeafCtx) -> tuple[list[str], bool]:
    """赋值类叶子动词单点分派：按 tokens[0] 路由 INITIALIZE/SET，非此二类 → ([], False)。

    复刻旧 rules._dispatch_leaf 的 try/except (ValueError, IndexError) 兜底（解析失败回退占位）
    → 与旧路同形，保证两路产物逐字符一致。
    """
    if not tokens:
        return [], False
    fn = _ASSIGN.get(tokens[0].upper())
    if not fn:
        return [], False
    try:
        return fn(tokens, ctx)
    except (ValueError, IndexError):
        return [], False
