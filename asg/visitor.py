"""
相2 ASG —— visitor 基类 + 单点 demo（GO TO → Java）。

对应设计：docs/详细设计/步骤17-旁路建相2-ASG设计.md §2.4。
设计思路：visit_<类名> 命名分派（仿 Python ast.NodeVisitor），加新节点只需加 visit_X，
无双分派样板。单点 demo 证明「访问带类型 GotoStmt.target」可替代 rules 的 token 嗅探。
"""
from __future__ import annotations

from asg import nodes
from translator.leaf import translate_move, translate_condition, translate_perform_loop, translate_call


class AsgVisitor:
    """visitor 基类：visit(node) → visit_<类名>(node)，缺省 generic_visit 递归子节点。"""

    def visit(self, node):
        meth = getattr(self, "visit_" + type(node).__name__, self.generic_visit)
        return meth(node)

    def generic_visit(self, node):
        return [self.visit(c) for c in _children(node)]


def _children(node) -> list:
    """节点的子节点（供 generic_visit 递归）。"""
    out: list = []
    for attr in ("then", "els", "inline_body", "stmts", "paragraphs", "sections"):
        out += getattr(node, attr, None) or []
    if isinstance(node, nodes.EvaluateStmt):
        for _cond, body in node.whens:
            out += body
    return out


class GotoJavaVisitor(AsgVisitor):
    """单点 demo：GotoStmt → Java，复刻 rules._sk_control 的 flow_label=None GO 分支
    （目标 …EXIT → return；未知段 → TODO-GOTO + return），证明访问 target 可替代 token 嗅探。

    范围：dispatch 模式(flow_label 状态机跳转)与「已知段 proc_call」平价留项3（§7-Q2）。
    """

    def __init__(self, known_sections: set | None = None):
        self.known_sections = known_sections or set()

    def visit_GotoStmt(self, node) -> list[str]:
        target = node.target.name if node.target else None
        if not target:
            return ["return;"]
        if target.endswith("EXIT"):
            return [f"return;  // GO TO {target}"]
        # 未知段（非 dispatch 模式）：与 _sk_control 末两支逐字符一致
        return [f"// TODO-GOTO: 跳转 {target}，需人工核对控制流", "return;"]


class LeafJavaVisitor(AsgVisitor):
    """相3 叶子翻译 visitor（步骤18 绞杀项3①）：visit_MoveStmt → 调公用 translate_move。

    与旧 rules 的 MOVE 翻译共用同一份 translate_move（translator.leaf），ctx 满足 LeafCtx
    （由 translator.skeleton_gen.body_context.build_body_ctx 提供，与旧路径同一对象）→
    两路产物逐字符一致（绞杀项3 比对闸基础）。范围：仅纯 _t_move 一层，循环重绑定留 PERFORM 刀。
    """

    def __init__(self, ctx):
        self.ctx = ctx                    # 满足 translator.leaf.LeafCtx 契约

    def visit_MoveStmt(self, node) -> list[str]:
        lines, _ok = translate_move(node.tokens, self.ctx)
        return lines

    def visit_IfStmt(self, node) -> list[str]:
        """复刻 rules._sk_if 的控制结构形状：if (cond) { … } [else { … }]，cond=None → 整 IF 交 LLM（占位）。

        条件经公用 translate_condition（与旧 rules._try_condition 同一函数同一 ctx）→ 条件串逐字符一致。
        body 仅直译已迁动词（MOVE / 嵌套 IF），未迁动词落 visit_Leaf 占位——绞杀渐进的诚实呈现
        （block 级一致须待全动词迁完，§5-项4；本步比对只在条件边界，见设计 §4.2）。
        """
        cond = translate_condition(node.cond, self.ctx)
        if cond is None:
            return [f"// TODO-IF: {node.raw}"]
        lines = [f"if ({cond}) {{"]
        lines += self._body(node.then) or ["    // (空)"]
        if node.els:
            lines.append("} else {")
            lines += self._body(node.els)
        lines.append("}")
        return lines

    def _body(self, stmts) -> list[str]:
        """递归 visit 子节点并扁平化为 Java 行（每行加一级缩进，等价 _sk_if 的 indent+1）。"""
        out: list[str] = []
        for c in stmts:
            for ln in self.visit(c):
                out.append("    " + ln)
        return out

    def visit_Leaf(self, node) -> list[str]:
        """未迁动词（CALL/算术/GOTO…）：诚实占位，使非空 body 可见、不静默吞行。"""
        return [f"// TODO-LEAF: {node.raw}"]

    def visit_PerformStmt(self, node) -> list[str]:
        """复刻 rules._sk_perform 的循环壳（步骤20 绞杀项3③·只切①循环子句）：

        经公用 translate_perform_loop 渲染 while/for/do-while/嵌套 for（与旧 _perform_loop 同函数同 ctx
        → 循环壳逐字符一致）；loop is None → 整条交 LLM（// TODO-PERFORM 占位，复刻 _sk_perform 兜底）。
        inline_body 递归直译已迁动词（MOVE/IF/嵌套 PERFORM），未迁落 visit_Leaf 占位；
        out-of-line（仅 target、无 inline_body）落 // TODO-PERFORM-CALL 占位——区间/目标解析属②，留后续刀（设计 §1 非目标）。
        比对只在循环壳边界（设计 §4.2），body/目标占位不比。
        """
        loop = translate_perform_loop(node.header, self.ctx, 0)
        if loop is None:
            return [f"// TODO-PERFORM: {node.raw}"]
        open_lines, close_lines = loop
        if node.inline_body:
            body = self._body(node.inline_body)
        elif node.target:
            thru = f" THRU {node.thru.name}" if node.thru else ""
            body = [f"// TODO-PERFORM-CALL: {node.target.name}{thru}"]
        else:
            return [f"// TODO-PERFORM: {node.raw}"]
        return (open_lines + body + close_lines) if open_lines else body

    def visit_CallStmt(self, node) -> list[str]:
        """复刻 rules 散点 CALL 兜底（步骤21 绞杀项3④·只切① _t_call）：

        经公用 translate_call（与旧 _t_call 同函数同 ctx → 产物逐字符一致）直译固化 CALL；
        matched=False（游标/非IO/未映射，或 struct_function 未命中功能码）→ // TODO-CALL 占位，body 诚实可见。
        ②setup+CALL+IF 结构吸收 / ③struct_rebind 属骨架装配层，留后续刀（设计 §1 非目标）；
        比对只在 translate_call 纯函数边界（设计 §4.2），不重放 struct_function 时序。
        """
        lines, matched = translate_call(node.tokens, self.ctx)
        return lines if matched else [f"// TODO-CALL: {node.raw}"]
