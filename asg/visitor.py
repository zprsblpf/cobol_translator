"""
相2 ASG —— visitor 基类 + 单点 demo（GO TO → Java）。

对应设计：docs/详细设计/步骤17-旁路建相2-ASG设计.md §2.4。
设计思路：visit_<类名> 命名分派（仿 Python ast.NodeVisitor），加新节点只需加 visit_X，
无双分派样板。单点 demo 证明「访问带类型 GotoStmt.target」可替代 rules 的 token 嗅探。
"""
from __future__ import annotations

from asg import nodes
from translator.leaf import (
    translate_move, translate_condition, translate_perform_loop, translate_call,
    translate_arith_assign, translate_control, translate_evaluate, evaluate_case_label,
)


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


class LeafJavaVisitor(AsgVisitor):
    """相3 叶子翻译 visitor（步骤18 绞杀项3①）：visit_MoveStmt → 调公用 translate_move。

    与旧 rules 的 MOVE 翻译共用同一份 translate_move（translator.leaf），ctx 满足 LeafCtx
    （由 translator.skeleton_gen.body_context.build_body_ctx 提供，与旧路径同一对象）→
    两路产物逐字符一致（绞杀项3 比对闸基础）。范围：仅纯 _t_move 一层，循环重绑定留 PERFORM 刀。
    """

    def __init__(self, ctx):
        self.ctx = ctx                    # 满足 translator.leaf.LeafCtx 契约

    def _with_rebind(self, node, fn):
        rebind = getattr(node, "struct_rebind", None)
        if not rebind:
            return fn()
        saved = {k: self.ctx.struct_objects.get(k) for k in rebind}
        self.ctx.struct_objects.update(rebind)
        try:
            return fn()
        finally:
            for k, v in saved.items():
                if v is None:
                    self.ctx.struct_objects.pop(k, None)
                else:
                    self.ctx.struct_objects[k] = v

    def visit_MoveStmt(self, node) -> list[str]:
        def _render():
            lines, _ok = translate_move(node.tokens, self.ctx)
            return lines
        return self._with_rebind(node, _render)

    def visit_IfStmt(self, node) -> list[str]:
        """复刻 rules._sk_if 的控制结构形状：if (cond) { … } [else { … }]，cond=None → 整 IF 交 LLM（占位）。

        条件经公用 translate_condition（与旧 rules._try_condition 同一函数同一 ctx）→ 条件串逐字符一致。
        body 仅直译已迁动词（MOVE / 嵌套 IF），未迁动词落 visit_Leaf 占位——绞杀渐进的诚实呈现
        （block 级一致须待全动词迁完，§5-项4；本步比对只在条件边界，见设计 §4.2）。
        """
        def _render():
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
        return self._with_rebind(node, _render)

    def _body(self, stmts) -> list[str]:
        """递归 visit 子节点并扁平化为 Java 行（每行加一级缩进，等价 _sk_if 的 indent+1）。"""
        out: list[str] = []
        for c in stmts:
            for ln in self.visit(c):
                out.append("    " + ln)
        return out

    def visit_Leaf(self, node) -> list[str]:
        """已迁的叶子动词直译；其余未迁动词仍诚实占位。

        依次试：① 算术/赋值（translate_arith_assign，步骤22）→ ② 控制流叶子词
        （translate_control，步骤23：落 Leaf 的 CONTINUE/STOP/EXIT/GOBACK/NEXT）。
        两者 verb 集互斥、均与旧 rules 同函数同 ctx → 产物逐字符一致；俱兜不住（STRING/未固化/
        解析失败）→ // TODO-LEAF 占位。占位单调收敛（只减不增）。"""
        def _render():
            lines, ok = translate_arith_assign(node.tokens, self.ctx)
            if ok:
                return lines
            lines, ok = translate_control(node.tokens, self.ctx)
            return lines if ok else [f"// TODO-LEAF: {node.raw}"]
        return self._with_rebind(node, _render)

    def visit_GotoStmt(self, node) -> list[str]:
        """复刻 rules._sk_control 的 GO 分支（步骤23 绞杀项3⑥，并入自退役的 GotoJavaVisitor）：

        经公用 translate_control（与旧 _sk_control flow_label=None 分支同函数同 ctx → 逐字符一致）
        译 GO TO（…EXIT→return / known_section→proc_call+return / 未知段→TODO-GOTO+return / 无 target→return）。
        GotoStmt 恒为 GO、translate_control 全覆盖；无 token 的退化节点 → return;（步骤17 demo 语义）。
        dispatch 模式（__pc/continue FLOW）依赖 flow_label 骨架态，留骨架装配刀（设计 §1 非目标）。"""
        lines, ok = translate_control(node.tokens, self.ctx)
        return lines if ok else ["return;"]

    def visit_EvaluateStmt(self, node) -> list[str]:
        """复刻 rules._sk_evaluate 的 switch 壳（步骤23 绞杀项3⑥）：

        subject 经公用 translate_evaluate（单 token 非 TRUE → `x.trim()`；否则 None→交 LLM），
        每 WHEN 的 case 标签经 evaluate_case_label（与 _sk_evaluate 同函数 → 壳逐字符一致）；
        WHEN 体递归直译已迁动词（未迁落 visit_Leaf 占位，同 IF body 渐进）。
        subject=None / 无 whens → // TODO-EVALUATE 占位（EVALUATE TRUE/复杂 subject 交 LLM）。"""
        def _render():
            subj = translate_evaluate(node.subject, self.ctx)
            if subj is None or not node.whens:
                return [f"// TODO-EVALUATE: {node.raw}"]
            lines = [f"switch ({subj}) {{"]
            for cond, body in node.whens:
                lines.append(f"    {evaluate_case_label(cond, self.ctx)}: {{")
                for c in body:
                    for ln in self.visit(c):
                        lines.append(f"        {ln}")
                lines.append("        break;")
                lines.append("    }")
            lines.append("}")
            return lines
        return self._with_rebind(node, _render)

    def visit_PerformStmt(self, node) -> list[str]:
        """复刻 rules._sk_perform 的循环壳（步骤20 绞杀项3③·只切①循环子句）：

        经公用 translate_perform_loop 渲染 while/for/do-while/嵌套 for（与旧 _perform_loop 同函数同 ctx
        → 循环壳逐字符一致）；loop is None → 整条交 LLM（// TODO-PERFORM 占位，复刻 _sk_perform 兜底）。
        inline_body 递归直译已迁动词（MOVE/IF/嵌套 PERFORM），未迁落 visit_Leaf 占位；
        out-of-line（仅 target、无 inline_body）落 // TODO-PERFORM-CALL 占位——区间/目标解析属②，留后续刀（设计 §1 非目标）。
        比对只在循环壳边界（设计 §4.2），body/目标占位不比。
        """
        def _render():
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
        return self._with_rebind(node, _render)

    def visit_CallStmt(self, node) -> list[str]:
        """复刻 rules 散点 CALL 兜底（步骤21 绞杀项3④·只切① _t_call）：

        经公用 translate_call（与旧 _t_call 同函数同 ctx → 产物逐字符一致）直译固化 CALL；
        matched=False（游标/非IO/未映射，或 struct_function 未命中功能码）→ // TODO-CALL 占位，body 诚实可见。
        ②setup+CALL+IF 结构吸收 / ③struct_rebind 属骨架装配层，留后续刀（设计 §1 非目标）；
        比对只在 translate_call 纯函数边界（设计 §4.2），不重放 struct_function 时序。
        """
        def _render():
            lines, matched = translate_call(node.tokens, self.ctx)
            return lines if matched else [f"// TODO-CALL: {node.raw}"]
        return self._with_rebind(node, _render)
