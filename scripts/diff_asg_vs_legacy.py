#!/usr/bin/env python3
"""
绞杀项3 旧/新两路产物逐字符比对闸（步骤18 绞杀项3①，常驻）。

用途：按动词把 rules 逐类迁进相3 visitor 时（路线图 §5-项3），对样例程序把每条该动词语句
      走「旧 rules 译器」与「ASG visitor」两路渲染，逐字符 diff，作每刀回归闸（§9-Q5）。
      已覆盖动词：
        · MOVE（步骤18）—— legacy 从 segmenter 切分树枚举每条 MOVE 跑 translate_move；
          asg build_asg → 遍历 MoveStmt 跑 LeafJavaVisitor.visit；两路逐字符比对 Java 行。
        · IF（步骤19）—— legacy 枚举每条 IF 跑 rules._try_condition（= 委托的 translate_condition）；
          asg 遍历 IfStmt 跑 translate_condition；两路逐字符比对**条件表达式串**（None 也比）。
        · PERFORM（步骤20）—— legacy 枚举每条 PERFORM 跑 rules._perform_loop（= 委托的 translate_perform_loop）；
          asg 遍历 PerformStmt 跑 translate_perform_loop；两路逐字符比对**循环壳 (open, close)**（None / ([],[]) 也比）。
      两路共用同一 ctx（body_context.build_body_ctx）与同一公用函数 → 产物应逐字符相等；
      不等即暴露「_lift 提升」或「ctx 装配」漂移。
对应设计：步骤18 §5（MOVE）、步骤19 §5（IF）、步骤20-绞杀项3③PERFORM循环子句迁visitor设计.md §5。

用法：
    python scripts/diff_asg_vs_legacy.py <program.cob> [--verb MOVE|IF|PERFORM|CALL|ARITH|CONTROL]
退出码：全等 0；有差异 1（CI/回归可断言）。

范围：
  · MOVE（步骤18 §4.3）：只比对纯 translate_move 一层；循环重绑定属 PERFORM③ 刀，本就两路都不施加，无 skip。
  · IF（步骤19 §4.2）：只比对**条件表达式**；IF body 旧路占位 vs 新路直译本就不等（渐进迁移预期态）。
  · PERFORM（步骤20 §4.2）：只切①循环子句、只比对**循环壳**；inline_body 旧占位 vs 新直译、out-of-line 目标
    旧区间合成 vs 新 TODO 占位本就不等；②THRU区间/③struct_rebind 留后续刀，block 级一致待 §5-项4。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from parser.cobol_parser import parse                                   # noqa: E402
from translator.segmenter import segment, split_paragraphs             # noqa: E402
from translator.skeleton_gen.body_context import build_body_ctx, reset_section  # noqa: E402
from translator.leaf import (  # noqa: E402
    translate_move, translate_condition, translate_perform_loop, translate_call, translate_arith_assign,
    translate_control, translate_evaluate, evaluate_case_label,
)
from translator import rules                                          # noqa: E402
from translator.skel import render_perform_call                        # noqa: E402
from asg import build_asg                                              # noqa: E402
from asg import nodes as asg_nodes                                     # noqa: E402
from asg.visitor import AsgVisitor, LeafJavaVisitor                    # noqa: E402
from asg.section_visitor import SectionJavaVisitor                     # noqa: E402


def _walk_segmenter_stmts(st):
    """按 builder._lift 的递归序遍历一条 Stmt 及其子句（then→else→when 体→perform 内联体）。"""
    yield st
    for child in getattr(st, "children", None) or []:
        yield from _walk_segmenter_stmts(child)
    for child in getattr(st, "else_children", None) or []:
        yield from _walk_segmenter_stmts(child)
    for _cond, body in getattr(st, "whens", None) or []:
        for child in body:
            yield from _walk_segmenter_stmts(child)


def _legacy_moves(program, ctx) -> list[tuple[str, list[str]]]:
    """旧路：segmenter 切分树枚举每条 MOVE → (raw, translate_move 输出)，源码序。"""
    out: list[tuple[str, list[str]]] = []
    for s in program.sections:
        for _lbl, body in split_paragraphs(s.lines):
            for st in segment(body):
                for sub in _walk_segmenter_stmts(st):
                    toks = getattr(sub, "tokens", None) or []
                    if sub.kind == "simple" and toks and toks[0].upper() == "MOVE":
                        lines, _ok = translate_move(list(toks), ctx)
                        out.append((sub.raw, lines))
    return out


class _MoveCollector(AsgVisitor):
    """遍历 ASG，对每个 MoveStmt 调 LeafJavaVisitor → (raw, java 行)，源码序。"""

    def __init__(self, ctx):
        self._leaf = LeafJavaVisitor(ctx)
        self.out: list[tuple[str, list[str]]] = []

    def visit_MoveStmt(self, node):
        self.out.append((node.raw, self._leaf.visit(node)))


def _asg_moves(program, ctx) -> list[tuple[str, list[str]]]:
    col = _MoveCollector(ctx)
    col.visit(build_asg(program))
    return col.out


def _legacy_ifs(program, ctx) -> list[tuple[str, str | None]]:
    """旧路：segmenter 切分树枚举每条 IF → (raw, rules._try_condition 输出)，源码序。

    比对单位是 _sk_if 用的条件串（rules._sk_if 即 cond = _try_condition(st.tokens, ctx)）；
    经委托 rules._try_condition 已是 translate_condition，取 rules 侧调用以验证别名接线无误。
    """
    out: list[tuple[str, str | None]] = []
    for s in program.sections:
        for _lbl, body in split_paragraphs(s.lines):
            for st in segment(body):
                for sub in _walk_segmenter_stmts(st):
                    if sub.kind == "if":
                        out.append((sub.raw, rules._try_condition(list(sub.tokens), ctx)))
    return out


class _IfCollector(AsgVisitor):
    """遍历 ASG，对每个 IfStmt 收 (raw, translate_condition 输出)，并递归 then/els 捕获嵌套 IF。"""

    def __init__(self, ctx):
        self.ctx = ctx
        self.out: list[tuple[str, str | None]] = []

    def visit_IfStmt(self, node):
        self.out.append((node.raw, translate_condition(node.cond, self.ctx)))
        self.generic_visit(node)          # 递归 then/els → 嵌套 IF 入列（源码序）


def _asg_ifs(program, ctx) -> list[tuple[str, str | None]]:
    col = _IfCollector(ctx)
    col.visit(build_asg(program))
    return col.out


def _legacy_performs(program, ctx) -> list[tuple[str, object]]:
    """旧路：segmenter 切分树枚举每条 PERFORM → (raw, rules._perform_loop 循环壳)，源码序。

    比对单位是 _sk_perform 用的循环壳 (open, close)（含 None / ([],[]) 三态）；indent 固定 0 求确定性。
    经委托 rules._perform_loop 已是 leaf.loop 同一函数，取 rules 侧调用以验证 import 接线无误。
    """
    out: list[tuple[str, object]] = []
    for s in program.sections:
        for _lbl, body in split_paragraphs(s.lines):
            for st in segment(body):
                for sub in _walk_segmenter_stmts(st):
                    if sub.kind == "perform":
                        hdr = list(sub.tokens)
                        hu = [h.upper() for h in hdr]
                        out.append((sub.raw, rules._perform_loop(hdr, hu, ctx, 0)))
    return out


class _PerformCollector(AsgVisitor):
    """遍历 ASG，对每个 PerformStmt 收 (raw, translate_perform_loop 循环壳)，递归 inline_body 捕嵌套 PERFORM。"""

    def __init__(self, ctx):
        self.ctx = ctx
        self.out: list[tuple[str, object]] = []

    def visit_PerformStmt(self, node):
        self.out.append((node.raw, translate_perform_loop(node.header, self.ctx, 0)))
        self.generic_visit(node)          # 递归 inline_body → 嵌套 PERFORM 入列（源码序）


def _asg_performs(program, ctx) -> list[tuple[str, object]]:
    col = _PerformCollector(ctx)
    col.visit(build_asg(program))
    return col.out


def _legacy_calls(program, ctx) -> list[tuple[str, object]]:
    """旧路：segmenter 切分树枚举每条 CALL → (raw, rules._t_call 输出 (lines, matched))，源码序。

    比对单位是散点 CALL 兜底译器 _t_call 的 (lines, matched)；经委托 rules._t_call 已是 leaf.call
    同一函数，取 rules 侧调用以验证别名接线无误。不重放 struct_function 时序（设计 §4.2 诚实边界）。
    """
    out: list[tuple[str, object]] = []
    for s in program.sections:
        for _lbl, body in split_paragraphs(s.lines):
            for st in segment(body):
                for sub in _walk_segmenter_stmts(st):
                    toks = getattr(sub, "tokens", None) or []
                    if sub.kind == "simple" and toks and toks[0].upper() == "CALL":
                        out.append((sub.raw, rules._t_call(list(toks), ctx)))
    return out


class _CallCollector(AsgVisitor):
    """遍历 ASG，对每个 CallStmt 收 (raw, translate_call 输出)。

    IF/PERFORM 等容器节点无对应 visit_*，由基类 generic_visit 默认递归其子节点（then/els/inline_body/
    whens/stmts），嵌套于其中的 CallStmt 自然按源码序入列（同 _MoveCollector 依赖默认递归的范式）。
    """

    def __init__(self, ctx):
        self.ctx = ctx
        self.out: list[tuple[str, object]] = []

    def visit_CallStmt(self, node):
        self.out.append((node.raw, translate_call(node.tokens, self.ctx)))


def _asg_calls(program, ctx) -> list[tuple[str, object]]:
    col = _CallCollector(ctx)
    col.visit(build_asg(program))
    return col.out


# 算术/赋值叶子动词（步骤22 绞杀项3⑤）：INITIALIZE/SET + 5 算术，均落 ASG Leaf
_ARITH_VERBS = {"INITIALIZE", "SET", "ADD", "SUBTRACT", "MULTIPLY", "DIVIDE", "COMPUTE"}


def _legacy_arith(program, ctx) -> list[tuple[str, object]]:
    """旧路：segmenter 切分树枚举每条 7 类算术/赋值语句 → (raw, rules._dispatch_leaf 输出 (lines, matched))，源码序。

    比对单位是 _dispatch_leaf 对这 7 类的 (lines, matched)；迁后 _dispatch_leaf 内部即委托
    leaf.assign/leaf.arith 同译器，取 rules 侧调用以验证别名接线无误（含 try/except 兜底同形）。
    """
    out: list[tuple[str, object]] = []
    for s in program.sections:
        for _lbl, body in split_paragraphs(s.lines):
            for st in segment(body):
                for sub in _walk_segmenter_stmts(st):
                    toks = getattr(sub, "tokens", None) or []
                    if sub.kind == "simple" and toks and toks[0].upper() in _ARITH_VERBS:
                        out.append((sub.raw, rules._dispatch_leaf(list(toks), ctx)))
    return out


class _ArithCollector(AsgVisitor):
    """遍历 ASG，对每个 7 类算术/赋值 Leaf 收 (raw, translate_arith_assign 输出)。

    非 7 类 Leaf（STRING 等）滤除——与 legacy 仅收 7 类对齐；IF/PERFORM 等容器由基类
    generic_visit 默认递归，嵌套于 body 内的 Leaf 自然按源码序入列（同 _CallCollector 范式）。
    """

    def __init__(self, ctx):
        self.ctx = ctx
        self.out: list[tuple[str, object]] = []

    def visit_Leaf(self, node):
        toks = node.tokens or []
        if toks and toks[0].upper() in _ARITH_VERBS:
            self.out.append((node.raw, translate_arith_assign(node.tokens, self.ctx)))


def _asg_arith(program, ctx) -> list[tuple[str, object]]:
    col = _ArithCollector(ctx)
    col.visit(build_asg(program))
    return col.out


# 控制流动词（步骤23 绞杀项3⑥）：EVALUATE + 控制叶子词。比对单位＝可迁的「壳」：
#   · 控制词 → translate_control 的 (lines)；· EVALUATE → (subject 串, case 标签元组)。
# honest 边界（设计 §4.2）：仅 flow_label=None；dispatch 模式留骨架刀，喂 flow_label=None ctx 规避伪差异。
# WHEN 体/IF body 旧 build_skeleton vs 新递归本就渐进不等，故 EVALUATE 只比壳（同 IF 只比条件）。
_CONTROL_VERBS = {"GO", "GOBACK", "STOP", "EXIT", "CONTINUE", "NEXT"}


def _eval_shell(subject, whens, ctx):
    return ("E", translate_evaluate(subject, ctx), tuple(evaluate_case_label(c, ctx) for c, _ in whens))


def _legacy_control(program, ctx) -> list[tuple[str, object]]:
    """旧路：segmenter 切分树枚举每条 EVALUATE / 控制叶子词。
    控制词跑 rules._sk_control（flow_label=None → 内部委托 translate_control，验 rules 接线）；EVALUATE 取壳。"""
    out: list[tuple[str, object]] = []
    for s in program.sections:
        for _lbl, body in split_paragraphs(s.lines):
            for st in segment(body):
                for sub in _walk_segmenter_stmts(st):
                    if sub.kind == "evaluate":
                        out.append((sub.raw, _eval_shell(list(sub.tokens), sub.whens, ctx)))
                    elif sub.kind == "simple" and sub.tokens and sub.tokens[0].upper() in _CONTROL_VERBS:
                        out.append((sub.raw, ("C", tuple(rules._sk_control(sub, ctx, 0)))))
    return out


class _ControlCollector(AsgVisitor):
    """遍历 ASG，对 GotoStmt / 控制词 Leaf 收 translate_control 壳、对 EvaluateStmt 收壳。

    IF/PERFORM 容器由基类 generic_visit 默认递归；EvaluateStmt 记录后递归 whens 体捕嵌套控制词（源码序）。
    """

    def __init__(self, ctx):
        self.ctx = ctx
        self.out: list[tuple[str, object]] = []

    def visit_GotoStmt(self, node):
        self.out.append((node.raw, ("C", tuple(translate_control(node.tokens, self.ctx)[0]))))

    def visit_Leaf(self, node):
        toks = node.tokens or []
        if toks and toks[0].upper() in _CONTROL_VERBS:
            self.out.append((node.raw, ("C", tuple(translate_control(node.tokens, self.ctx)[0]))))

    def visit_EvaluateStmt(self, node):
        self.out.append((node.raw, _eval_shell(node.subject, node.whens, self.ctx)))
        self.generic_visit(node)          # 递归 whens 体 → 嵌套控制词入列（源码序）


def _asg_control(program, ctx) -> list[tuple[str, object]]:
    col = _ControlCollector(ctx)
    col.visit(build_asg(program))
    return col.out


# out-of-line PERFORM 调用体（步骤24A 绞杀项4 骨架装配①）：比对调用体行 + pending_range_methods 登记副作用。
# 两路各建**独立 fresh ctx**（隔离 pending 副作用），每条 out-of-line PERFORM 收 (raw, (lines, pending 快照))。
def _perform_target(header: list, hu: list) -> str | None:
    """复刻 _sk_perform 的 target 提取：首 token 非循环关键字且非纯数字 → 大写过程名，否则 None。"""
    if header and hu[0] not in {"VARYING", "UNTIL", "WITH", "TEST"} and not header[0].isdigit():
        return header[0].upper()
    return None


def _pending_snapshot(ctx) -> dict:
    """深拷贝 ctx.pending_range_methods（值为 [(label, body_lines), …]），隔离后续累积突变以便逐条比对。"""
    return {k: [(lbl, list(body)) for lbl, body in v] for k, v in ctx.pending_range_methods.items()}


def _legacy_perform_calls(program, _ctx) -> list[tuple[str, object]]:
    """旧路：枚举每条 out-of-line PERFORM（无内联体、有 target）→ rules._perform_range 输出 + pending 快照，源码序。

    委托后 rules._perform_range 即 skel.render_perform_call 同一函数；取 rules 侧调用以验证别名接线无误。
    用独立 fresh ctx 跑，pending_range_methods 登记副作用与 asg 侧隔离对比（步骤24A §5）。"""
    ctx, _ws = build_body_ctx(program)
    out: list[tuple[str, object]] = []
    for s in program.sections:
        for _lbl, body in split_paragraphs(s.lines):
            for st in segment(body):
                for sub in _walk_segmenter_stmts(st):
                    if sub.kind == "perform" and not sub.children:
                        hdr = list(sub.tokens)
                        hu = [h.upper() for h in hdr]
                        tgt = _perform_target(hdr, hu)
                        if tgt:
                            lines = rules._perform_range(hdr, hu, tgt, ctx, 0)
                            out.append((sub.raw, (lines, _pending_snapshot(ctx))))
    return out


class _PerformCallCollector(AsgVisitor):
    """遍历 ASG，对每个 out-of-line PerformStmt（无 inline_body、有 target）收 (raw, (render_perform_call, pending 快照))。"""

    def __init__(self, ctx):
        self.ctx = ctx
        self.out: list[tuple[str, object]] = []

    def visit_PerformStmt(self, node):
        if not node.inline_body and node.target:
            hu = [h.upper() for h in node.header]
            lines = render_perform_call(node.header, hu, node.target.name, self.ctx, 0)
            self.out.append((node.raw, (lines, _pending_snapshot(self.ctx))))
        self.generic_visit(node)          # 递归 inline_body → 嵌套 out-of-line PERFORM 入列（源码序）


def _asg_perform_calls(program, _ctx) -> list[tuple[str, object]]:
    ctx, _ws = build_body_ctx(program)   # 独立 fresh ctx，隔离 pending 副作用
    col = _PerformCallCollector(ctx)
    col.visit(build_asg(program))
    return col.out


# 段内 GO TO dispatch 状态机（步骤24B 绞杀项4 骨架装配②）：以 SECTION 为采样单位，比对
#   ① 段级装配输出行（状态机壳 / 扁平拼接 / 段内 GO TO·EXIT dispatch 行）逐字符；
#   ② 收尾后 flow_label/flow_paragraphs 复位（证装配副作用洁净）。
# 两路各建 fresh ctx 隔离。选样守界（设计 §5）：样例须**无 begn 循环**（避 24C 分流）且
#   **段体动词均已迁**（未迁动词新路落 // TODO-LEAF 与旧路 build_skeleton 体不等，属渐进预期）。
def _flow_snapshot(ctx) -> tuple:
    """收尾后状态机副作用快照：装配收尾两路均须复位 → (None, ())；非空即装配漏复位。"""
    return (ctx.flow_label, tuple(sorted(ctx.flow_paragraphs)))


def _fill_legacy_leaves(lines: list[str], ctx) -> list[str]:
    """旧路 build_section 把叶子留 /*__LEAF_n__*/ 占位（二趟架构），此处用 translate_leaf 回填
    （= visitor 一趟内联直译同一函数同 ctx），隔离 24B 段级装配的比对（单行叶子在占位处原位替换，不改缩进）。"""
    fills = {}
    for lid, leaf in ctx.leaves:
        flines, matched = rules.translate_leaf(leaf, ctx)
        raw = (leaf.raw or " ".join(leaf.tokens)).strip()
        fills[f"/*__LEAF_{lid}__*/"] = "\n".join(flines) if matched else f"// TODO-LEAF: {raw}"
    out: list[str] = []
    for ln in lines:
        for ph, fill in fills.items():
            if ph in ln:
                ln = ln.replace(ph, fill)
                break
        out.append(ln)
    return out


def _legacy_flows(program, _ctx) -> list[tuple[str, object]]:
    """旧路：每个 SECTION 切 [(label, [Stmt])] → rules.build_section（= 委托 render_flow_dispatch）+ 叶子回填 + 收尾快照，源码序。

    取 rules.build_section 侧调用以验证委托接线无误；非 begn 段 _rewrite_begn_loops 为 no-op，
    故与 asg 侧 visit_Section（同 render_flow_dispatch）逐字符可比。fresh ctx 隔离 flow 副作用。
    build_section 叶子留占位，回填后与 visitor 内联直译对齐（单行叶子；多行叶子非本闸选样形态）。"""
    ctx, _ws = build_body_ctx(program)
    out: list[tuple[str, object]] = []
    for s in program.sections:
        paras = [(lbl, segment(body)) for lbl, body in split_paragraphs(s.lines)]
        lines = _fill_legacy_leaves(rules.build_section(paras, ctx, 0), ctx)
        out.append((s.name, (lines, _flow_snapshot(ctx))))
    return out


def _asg_flows(program, _ctx) -> list[tuple[str, object]]:
    """新路：遍历 ASG Section → LeafJavaVisitor.visit_Section（内部 render_flow_dispatch）+ 收尾快照，源码序。"""
    ctx, _ws = build_body_ctx(program)
    vis = LeafJavaVisitor(ctx)
    out: list[tuple[str, object]] = []
    for sec in build_asg(program).sections:
        lines = vis.visit_Section(sec)
        out.append((sec.name, (lines, _flow_snapshot(ctx))))
    return out


# BEGN/READR/WRITE IO 形态吸收（步骤24C 绞杀项4 骨架装配③）：以 SECTION 为采样单位，比对
#   ① 段级 IO 吸收体 + 状态机装配输出行（List+for-each / findBy…Begn / record!=null / repo.save…）逐字符；
#   ② 收尾后 flow 副作用 + struct_objects 复位（证 IO 渲染期 rebind 洁净、不跨段污染）。
# 两路各建 fresh ctx 隔离；rewrite_io_paras 经 build_section（旧）/ visit_Section（新）同一匹配/渲染。
# 选样守界（设计24C §5）：覆盖四形态 ①②③④ + 无 IO 对照段；段体动词均已迁（绞杀项3 已覆盖）。
def _io_snapshot(ctx) -> tuple:
    """收尾后副作用快照：flow 复位 + struct_objects 复位 → 装配洁净。
    IO 渲染期临时设 struct_objects[pfx]=loop/record 变量，收尾必复位 → 非空即漏复位。"""
    return (ctx.flow_label, tuple(sorted(ctx.flow_paragraphs)),
            tuple(sorted((k, str(v)) for k, v in ctx.struct_objects.items())))


def _legacy_ios(program, _ctx) -> list[tuple[str, object]]:
    """旧路：每 SECTION → rules.build_section（含 _rewrite_begn_loops 委托 rewrite_io_paras）+ 叶子回填 + 快照。

    build_section 把 IO 形态吸收为预渲染 raw（体内叶子留 /*__LEAF_n__*/ 占位、带 struct_rebind 标记），
    _fill_legacy_leaves 经 translate_leaf 二趟回填（读 struct_rebind → 字段重绑定）→ 与新路一趟内联对齐。
    fresh ctx 隔离 flow / struct_objects 副作用。"""
    ctx, _ws = build_body_ctx(program)
    out: list[tuple[str, object]] = []
    for s in program.sections:
        paras = [(lbl, segment(body)) for lbl, body in split_paragraphs(s.lines)]
        lines = _fill_legacy_leaves(rules.build_section(paras, ctx, 0), ctx)
        out.append((s.name, (lines, _io_snapshot(ctx))))
    return out


def _asg_ios(program, _ctx) -> list[tuple[str, object]]:
    """新路：遍历 ASG Section → visit_Section（内部 rewrite_io_paras 一趟内联渲染 + render_flow_dispatch）+ 快照。"""
    ctx, _ws = build_body_ctx(program)
    vis = LeafJavaVisitor(ctx)
    out: list[tuple[str, object]] = []
    for sec in build_asg(program).sections:
        lines = vis.visit_Section(sec)
        out.append((sec.name, (lines, _io_snapshot(ctx))))
    return out


def _legacy_sections(program, ctx) -> list[tuple[str, object]]:
    """legacy reference: render each SECTION through rules.build_section."""
    out: list[tuple[str, object]] = []
    for section in program.sections:
        reset_section(ctx)
        paras = [(label, segment(body)) for label, body in split_paragraphs(section.lines)]
        lines = rules.build_section(paras, ctx, force_sm=False)
        body = "\n".join(lines)
        for lid, leaf in ctx.leaves:
            fill_lines, matched = rules.translate_leaf(leaf, ctx)
            raw = (leaf.raw or " ".join(leaf.tokens)).strip()
            fill = "\n".join(fill_lines) if matched else f"// TODO-LEAF: {raw}"
            body = body.replace(f"/*__LEAF_{lid}__*/", fill)
        out.append((section.name, tuple(body.splitlines())))
    return out


def _asg_sections(program, ctx) -> list[tuple[str, object]]:
    """ASG route: render each SECTION through SectionJavaVisitor."""
    out: list[tuple[str, object]] = []
    visitor = SectionJavaVisitor(ctx)
    for section in build_asg(program).sections:
        reset_section(ctx)
        out.append((section.name, tuple(visitor.render_section(section))))
    return out


_SAMPLERS = {
    "MOVE": (_legacy_moves, _asg_moves),
    "IF": (_legacy_ifs, _asg_ifs),
    "PERFORM": (_legacy_performs, _asg_performs),
    "PERFORMCALL": (_legacy_perform_calls, _asg_perform_calls),
    "FLOW": (_legacy_flows, _asg_flows),
    "IO": (_legacy_ios, _asg_ios),
    "CALL": (_legacy_calls, _asg_calls),
    "ARITH": (_legacy_arith, _asg_arith),
    "CONTROL": (_legacy_control, _asg_control),
    "SECTION": (_legacy_sections, _asg_sections),
}


def main() -> int:
    ap = argparse.ArgumentParser(description="绞杀项3 旧/新两路产物逐字符比对闸（MOVE / IF）")
    ap.add_argument("cobol", help="样例 COBOL 源（.cob）")
    ap.add_argument("--verb", default="MOVE", choices=sorted(_SAMPLERS), help="比对动词")
    args = ap.parse_args()

    program = parse(args.cobol)
    ctx, _ws = build_body_ctx(program)
    legacy_fn, asg_fn = _SAMPLERS[args.verb]
    legacy = legacy_fn(program, ctx)
    asg = asg_fn(program, ctx)

    diffs: list[str] = []
    if len(legacy) != len(asg):
        diffs.append(f"{args.verb} 条数不一致：legacy={len(legacy)} asg={len(asg)}")
    for i, (lg, ag) in enumerate(zip(legacy, asg)):
        if lg[1] != ag[1]:
            diffs.append(f"#{i} raw={lg[0]!r}\n  legacy: {lg[1]}\n  asg   : {ag[1]}")

    if diffs:
        print(f"[FAIL] {args.cobol} [{args.verb}]：{len(diffs)} 处差异")
        for d in diffs:
            print(d)
        return 1
    print(f"[OK] {args.cobol} [{args.verb}]：{len(legacy)} 条 {args.verb} 两路逐字符一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
