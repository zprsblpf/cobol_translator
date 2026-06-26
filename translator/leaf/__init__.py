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

__all__ = ["LeafCtx", "translate_move", "translate_condition", "translate_perform_loop",
           "translate_call", "translate_assign", "translate_arith", "translate_arith_assign",
           "translate_control", "translate_evaluate", "evaluate_case_label"]
