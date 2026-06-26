"""
相2「自研轻量 ASG」包（绞杀分期②·旁路并存）。

对应设计：docs/详细设计/步骤17-旁路建相2-ASG设计.md。
对外唯一入口 build_asg(program)：CobolProgram → 带类型节点树（相3 visitor 的输入）。
旁路并存：不接入旧 build_skeleton/assemble，零改 parser/segmenter/rules（旧路径回归闸不动）。

用法：
    from parser.cobol_parser import parse
    from asg import build_asg, LeafJavaVisitor
    prog = build_asg(parse("X.cob"))
    # 相3 翻译：LeafJavaVisitor(ctx).visit(node) → Java 行（visit_MoveStmt/IfStmt/PerformStmt/
    # CallStmt/EvaluateStmt/GotoStmt/Leaf）。GotoJavaVisitor 步骤17 demo 已于步骤23 退役并入 LeafJavaVisitor。
"""
from asg.nodes import (
    Program, Section, Paragraph,
    IfStmt, EvaluateStmt, PerformStmt, GotoStmt, CallStmt, MoveStmt, Leaf,
)
from asg.registry import ProcUnit, ProcRef, ProcRegistry, SymbolTable
from asg.visitor import AsgVisitor, LeafJavaVisitor
from asg.builder import build as _build

__all__ = [
    "build_asg",
    "Program", "Section", "Paragraph",
    "IfStmt", "EvaluateStmt", "PerformStmt", "GotoStmt", "CallStmt", "MoveStmt", "Leaf",
    "ProcUnit", "ProcRef", "ProcRegistry", "SymbolTable",
    "AsgVisitor", "LeafJavaVisitor",
]


def build_asg(program):
    """CobolProgram → 相2 Program 节点树（唯一入口，只编排不放逻辑）。"""
    return _build(program)
