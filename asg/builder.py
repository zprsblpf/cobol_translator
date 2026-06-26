"""
相2 ASG —— builder：把 segmenter 的裸 Stmt「提升」为带类型节点 + 解析引用。

对应设计：docs/详细设计/步骤17-旁路建相2-ASG设计.md §2.3。
复用（只读，不改其源）：translator.segmenter.segment / split_paragraphs（确定性切分）、
asg.registry.build（过程注册表）。token 嗅探（tokens[0]=="GO" 等）**只在本文件 _lift 集中一次**，
相3 visitor 从此只访问类型，不再嗅探（初步设计 §0 削偶然复杂度）。
"""
from __future__ import annotations

from config import grammar_loader
from translator.segmenter import segment, split_paragraphs

from asg import nodes
from asg.registry import ProcRegistry, build as _build_reg

# PERFORM 头部修饰关键字（UNTIL/VARYING/THRU…）取自切分文法正本，不在本文件硬编码方言。
_PERFORM_KW = grammar_loader.perform_keywords()
_THRU = {"THRU", "THROUGH"}


def build(program) -> nodes.Program:
    """CobolProgram → Program 节点树。每 SECTION → split_paragraphs → segment → _lift。"""
    proc, _sym = _build_reg(program)
    secs: list[nodes.Section] = []
    for s in program.sections:
        paras: list[nodes.Paragraph] = []
        for lbl, body in split_paragraphs(s.lines):
            stmts = [_lift(st, proc) for st in segment(body)]
            paras.append(nodes.Paragraph(label=lbl, stmts=stmts))
        secs.append(nodes.Section(name=s.name.upper(), paragraphs=paras, lineno=s.line_start))
    return nodes.Program(program_id=program.program_id, sections=secs, registry=proc)


def _lift(st, proc: ProcRegistry):
    """裸 Stmt → 带类型节点（唯一的 token 嗅探点；判定抄自 rules 既有分支，产出类型节点）。"""
    if st.kind == "if":
        return nodes.IfStmt(cond=list(st.tokens),
                            then=[_lift(c, proc) for c in st.children],
                            els=[_lift(c, proc) for c in st.else_children], raw=st.raw)
    if st.kind == "evaluate":
        whens = [(cond, [_lift(c, proc) for c in body]) for cond, body in st.whens]
        return nodes.EvaluateStmt(subject=list(st.tokens), whens=whens, raw=st.raw)
    if st.kind == "perform":
        return _lift_perform(st, proc)
    # simple
    first = st.tokens[0].upper() if st.tokens else ""
    if first == "MOVE":
        return nodes.MoveStmt(tokens=list(st.tokens), raw=st.raw)
    if first == "GO":
        return nodes.GotoStmt(target=proc.resolve(_goto_target(st.tokens)),
                              tokens=list(st.tokens), raw=st.raw)
    if first == "CALL":
        name, using = _call_parts(st.tokens)
        return nodes.CallStmt(name=name, using=using, tokens=list(st.tokens), raw=st.raw)
    return nodes.Leaf(tokens=list(st.tokens), raw=st.raw)


def _lift_perform(st, proc: ProcRegistry):
    hdr = st.tokens
    target = proc.resolve(hdr[0]) if hdr and hdr[0].upper() not in _PERFORM_KW else None
    thru = None
    for i, t in enumerate(hdr):
        if t.upper() in _THRU and i + 1 < len(hdr):
            thru = proc.resolve(hdr[i + 1])
            break
    body = [_lift(c, proc) for c in st.children]
    return nodes.PerformStmt(target=target, thru=thru, header=list(hdr),
                             inline_body=body, raw=st.raw)


def _goto_target(toks) -> str | None:
    for t in toks:
        if t.upper() not in ("GO", "TO"):
            return t
    return None


def _call_parts(toks) -> tuple[str | None, list[str]]:
    name: str | None = None
    using: list[str] = []
    seen_using = False
    for t in toks[1:]:
        if t.upper() == "USING":
            seen_using = True
            continue
        if seen_using:
            using.append(t)
        elif name is None:
            name = t.strip("'\"")     # CALL 'XXX' 去引号；裸标识符原样
    return name, using
