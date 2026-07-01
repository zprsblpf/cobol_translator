"""
translator.leaf —— 相3 叶子翻译公用底座（rules 与 asg.visitor 共用）。

对应设计：docs/详细设计/步骤18-绞杀项3①MOVE迁visitor设计.md §3。
门面：导出 LeafCtx 契约、表达式底座、MOVE 译器。绞杀项3 后续动词（IF/CALL/STRING…）逐刀并入本包。
"""
from translator.leaf.context import LeafCtx
from translator.leaf.arith import translate_arith, translate_arith_assign
from translator.leaf.assign import translate_assign
from translator.leaf.call import translate_call
from translator.leaf.cond import translate_condition
from translator.leaf.control import translate_control, translate_evaluate, evaluate_case_label
from translator.leaf.loop import translate_perform_loop
from translator.leaf.move import translate_move
from translator.leaf.inspect import translate_inspect
from translator.leaf.search import translate_search
from translator.leaf.string import translate_string
from translator.leaf.unstring import translate_unstring


def translate_leaf_stmt(tokens: list[str], ctx: LeafCtx) -> tuple[list[str], bool]:
    """Shared leaf-statement dispatcher for rules and ASG visitors."""
    if not tokens:
        return [], False
    verb = tokens[0].upper()
    try:
        if verb == "MOVE":
            return translate_move(tokens, ctx)
        lines, ok = translate_arith_assign(tokens, ctx)
        if ok:
            return lines, ok
        if verb == "CALL":
            return translate_call(tokens, ctx)
        if verb == "STRING":
            return translate_string(tokens, ctx)
        if verb == "UNSTRING":
            return translate_unstring(tokens, ctx)
        if verb == "INSPECT":
            return translate_inspect(tokens, ctx)
        if verb == "SEARCH":
            return translate_search(tokens, ctx)
        return translate_control(tokens, ctx)
    except (ValueError, IndexError):
        return [], False


__all__ = ["LeafCtx", "translate_move", "translate_condition", "translate_perform_loop",
           "translate_call", "translate_string", "translate_unstring", "translate_inspect", "translate_search",
           "translate_assign", "translate_arith", "translate_arith_assign",
           "translate_control", "translate_evaluate", "evaluate_case_label",
           "translate_leaf_stmt"]
