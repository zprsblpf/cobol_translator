"""
相2 ASG —— visitor 基类 + 单点 demo（GO TO → Java）。

对应设计：docs/详细设计/步骤17-旁路建相2-ASG设计.md §2.4。
设计思路：visit_<类名> 命名分派（仿 Python ast.NodeVisitor），加新节点只需加 visit_X，
无双分派样板。单点 demo 证明「访问带类型 GotoStmt.target」可替代 rules 的 token 嗅探。
"""
from __future__ import annotations

from asg import nodes


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
