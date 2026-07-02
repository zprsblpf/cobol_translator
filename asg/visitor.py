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
    translate_leaf_stmt,
)
from translator.leaf.control import is_goto_depending
from translator.skel import (
    render_perform_call,
    render_flow_dispatch, dispatch_goto, dispatch_exit,   # 步骤24B GO TO dispatch 状态机
    rewrite_io_paras, NodeAccess,                         # 步骤24C BEGN/READR/WRITE IO 形态吸收
)


def _ind(n: int) -> str:
    return "    " * n


# ── ASG 节点访问器（步骤24C 绞杀项4 骨架装配③）──────────────────────────────────
# 把 skel.io_rewrite 匹配器读取的 5 个节点字段映射到 ASG 节点类型（设计24C §3.2）：
# 旧路 STMT_ACCESS 属性直读，新路按类型派生 kind + then/els/cond/subject/inline_body。
def _asg_kind(node) -> str:
    if isinstance(node, nodes.IfStmt):
        return "if"
    if isinstance(node, nodes.EvaluateStmt):
        return "evaluate"
    if isinstance(node, nodes.PerformStmt):
        return "perform"
    if isinstance(node, nodes.Raw):
        return "raw"
    return "simple"          # Leaf / MoveStmt / CallStmt / GotoStmt


def _asg_tokens(node) -> list:
    if isinstance(node, nodes.IfStmt):
        return node.cond          # if：条件 token（镜像 Stmt(kind=if).tokens）
    if isinstance(node, nodes.EvaluateStmt):
        return node.subject
    if isinstance(node, nodes.PerformStmt):
        return node.header
    return getattr(node, "tokens", None) or []


def _asg_children(node) -> list:
    if isinstance(node, nodes.IfStmt):
        return node.then
    if isinstance(node, nodes.PerformStmt):
        return node.inline_body
    return []


def _asg_else(node) -> list:
    return node.els if isinstance(node, nodes.IfStmt) else []


def _asg_whens(node) -> list:
    return node.whens if isinstance(node, nodes.EvaluateStmt) else []


ASG_ACCESS = NodeAccess(kind=_asg_kind, tokens=_asg_tokens, children=_asg_children,
                        else_children=_asg_else, whens=_asg_whens)


def _asg_collect_gotos(stmts: list) -> list[str]:
    """递归收集 ASG 段体内所有 GO TO 目标（大写）——镜像 rules._collect_gotos 的 token 口径，
    含嵌套 IF(then/els)/EVALUATE(whens)/PERFORM(inline_body) 体内的。"""
    out: list[str] = []
    for st in stmts:
        if isinstance(st, nodes.GotoStmt):
            if not is_goto_depending(st.tokens):
                for t in st.tokens:
                    if t.upper() not in ("GO", "TO"):
                        out.append(t.upper())
                        break
        out += _asg_collect_gotos(getattr(st, "then", None) or [])
        out += _asg_collect_gotos(getattr(st, "els", None) or [])
        out += _asg_collect_gotos(getattr(st, "inline_body", None) or [])
        for _cond, body in getattr(st, "whens", None) or []:
            out += _asg_collect_gotos(body)
    return out


def _asg_ends_transfer(stmts: list) -> bool:
    """末尾顶层语句是否为无条件跳转（GO/EXIT/GOBACK/STOP）——镜像 rules._ends_with_transfer。
    GO 在 ASG 恒为 GotoStmt；EXIT/GOBACK/STOP 为 Leaf（builder 只升 GO）。"""
    if not stmts:
        return False
    last = stmts[-1]
    if isinstance(last, nodes.GotoStmt):
        return True
    toks = getattr(last, "tokens", None) or []
    return bool(toks) and toks[0].upper() in {"EXIT", "GOBACK", "STOP"}


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
        self.ctx = ctx                    # 满足 translator.leaf.LeafCtx / skel.SkelCtx 契约

    def visit_Section(self, node) -> list[str]:
        """复刻 rules.build_section 全链：IO 形态吸收（步骤24C）→ 段级 GO TO dispatch 装配（步骤24B）。

        Section.paragraphs → [(label, stmts)]，先交路径中立 rewrite_io_paras 做 BEGN/READR/WRITE IO 形态
        段级吸收（与旧 build_section 共调同一匹配/渲染，acc=ASG_ACCESS、render_body=_render_para_body、
        make_raw=nodes.Raw → 吸收体 Java + struct_objects 副作用逐字符一致；命中段换 Raw 节点）；再交
        render_flow_dispatch 做状态机壳 + 段内 GO TO/EXIT dispatch（步骤24B 已一致）。
        indent 传 0，程序级缩进由 24D 外层施加（比对在 indent 0，沿 24A 范式）。"""
        paras = [(p.label, p.stmts) for p in node.paragraphs]
        paras = rewrite_io_paras(
            paras, self.ctx, acc=ASG_ACCESS,
            render_body=self._render_para_body,
            make_raw=lambda lines: nodes.Raw(lines=lines),
        )
        return render_flow_dispatch(
            paras, self.ctx, 0,
            render_body=self._render_para_body,
            collect_gotos=_asg_collect_gotos,
            ends_transfer=_asg_ends_transfer,
        )

    def visit_Raw(self, node) -> list[str]:
        """预渲染 IO 吸收体（步骤24C）：直接吐 .lines（缩进由 _render_para_body/render_flow_dispatch 统一施加，
        镜像旧 _skeleton_one 的 kind=="raw" 整体下沉）。"""
        return list(node.lines)

    def _render_para_body(self, stmts, indent) -> list[str]:
        """render_flow_dispatch 的段体渲染回调（= 旧 build_skeleton(stmts, ctx, indent)）：
        visit 每条语句（产 indent-0 相对行）后整体下沉 indent 级；空行保持空（镜像旧 _skeleton_one raw 分支）。
        关键：render_flow_dispatch 已先设 ctx.flow_label/flow_paragraphs，故体内 GO TO/EXIT 经 dispatch 命中。"""
        out: list[str] = []
        for st in stmts:
            for ln in self.visit(st):
                out.append((_ind(indent) + ln) if ln else ln)
        return out

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
        """已迁的叶子动词直译；其余未迁动词仍诚实占位。

        依次试：① 算术/赋值（translate_arith_assign，步骤22）→ ② 控制流叶子词
        （translate_control，步骤23：落 Leaf 的 CONTINUE/STOP/EXIT/GOBACK/NEXT）。
        两者 verb 集互斥、均与旧 rules 同函数同 ctx → 产物逐字符一致；俱兜不住（STRING/未固化/
        解析失败）→ // TODO-LEAF 占位。占位单调收敛（只减不增）。
        dispatch 模式（步骤24B）：状态机内 EXIT → dispatch_exit 产 break FLOW（与旧 _sk_control EXIT 分支
        同函数同 ctx → 逐字符一致），先于算术/控制叶子委托。"""
        d = dispatch_exit(node.tokens, self.ctx, 0)
        if d is not None:
            return d
        lines, ok = translate_leaf_stmt(node.tokens, self.ctx)
        return lines if ok else [f"// TODO-LEAF: {node.raw}"]

    def visit_GotoStmt(self, node) -> list[str]:
        """复刻 rules._sk_control 的 GO 分支（步骤23 绞杀项3⑥，并入自退役的 GotoJavaVisitor）：

        经公用 translate_control（与旧 _sk_control flow_label=None 分支同函数同 ctx → 逐字符一致）
        译 GO TO（…EXIT→return / known_section→proc_call+return / 未知段→TODO-GOTO+return / 无 target→return）。
        GotoStmt 恒为 GO、translate_control 全覆盖；无 token 的退化节点 → return;（步骤17 demo 语义）。
        dispatch 模式（步骤24B 绞杀项4②）：状态机内目标命中段内标签 → dispatch_goto 产 __pc/continue FLOW
        （与旧 _sk_control GO 分支同函数同 ctx → 逐字符一致），先于 flow_label-无关委托。"""
        target = node.target.name if node.target else None
        if is_goto_depending(node.tokens):
            target = None
        d = dispatch_goto(target, self.ctx, 0)
        if d is not None:
            return d
        lines, ok = translate_control(node.tokens, self.ctx)
        return lines if ok else ["return;"]

    def visit_EvaluateStmt(self, node) -> list[str]:
        """复刻 rules._sk_evaluate 的 switch 壳（步骤23 绞杀项3⑥）：

        subject 经公用 translate_evaluate（单 token 非 TRUE → `x.trim()`；否则 None→交 LLM），
        每 WHEN 的 case 标签经 evaluate_case_label（与 _sk_evaluate 同函数 → 壳逐字符一致）；
        WHEN 体递归直译已迁动词（未迁落 visit_Leaf 占位，同 IF body 渐进）。
        subject=None / 无 whens → // TODO-EVALUATE 占位（EVALUATE TRUE/复杂 subject 交 LLM）。"""
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

    def visit_PerformStmt(self, node) -> list[str]:
        """复刻 rules._sk_perform 的循环壳（步骤20 绞杀项3③·只切①循环子句）：

        经公用 translate_perform_loop 渲染 while/for/do-while/嵌套 for（与旧 _perform_loop 同函数同 ctx
        → 循环壳逐字符一致）；loop is None → 整条交 LLM（// TODO-PERFORM 占位，复刻 _sk_perform 兜底）。
        inline_body 递归直译已迁动词（MOVE/IF/嵌套 PERFORM），未迁落 visit_Leaf 占位；
        out-of-line（仅 target、无 inline_body）经公用 render_perform_call（步骤24A 绞杀项4 骨架装配①，
        与旧 rules._perform_range 同函数同 ctx → 调用体行 + pending_range_methods 登记副作用逐字符/逐项一致）：
        无 THRU→单段/合成单单元、SECTION 级 THRU→按段展开、paragraph 级 THRU→合成区间方法、兜不住→TODO 退化。
        比对在循环壳（设计 §4.2）+ 调用体（步骤24A §5）两处边界。
        """
        loop = translate_perform_loop(node.header, self.ctx, 0)
        if loop is None:
            return [f"// TODO-PERFORM: {node.raw}"]
        open_lines, close_lines = loop
        if node.inline_body:
            body = self._body(node.inline_body)
        elif node.target:
            # token-based 复用（设计 §3.3）：与旧路同源从 header 取 target/THRU 端点，不走已解析 ref。
            hu = [h.upper() for h in node.header]
            body = render_perform_call(node.header, hu, node.target.name, self.ctx, 0)
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
