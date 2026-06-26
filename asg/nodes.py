"""
相2 ASG —— 带类型节点模型（dataclass 平铺层级）。

对应设计：docs/详细设计/步骤17-旁路建相2-ASG设计.md §2.1。
设计思路：节点种类有限，用 @dataclass 平铺、不做深继承；visitor 用 visit_<类名> 分派
（见 asg/visitor.py），加新节点只需加一个 visit_X 方法。每节点带 raw/lineno 供回溯。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from asg.registry import ProcRef


# ── 语句节点（带类型，取代 segmenter 裸 Stmt 的 token 袋）────────────────────────

@dataclass
class Leaf:
    """兜底：本步未细分类型的简单语句（MOVE/COMPUTE/…），原样收，相3 visit 落 // TODO。"""
    tokens: list[str] = field(default_factory=list)
    raw: str = ""
    lineno: int = 0


@dataclass
class MoveStmt:
    """MOVE src TO dst…（步骤18 绞杀项3①）：本步只保 token，语义由公用 translate_move 解析。"""
    tokens: list[str] = field(default_factory=list)
    raw: str = ""
    lineno: int = 0


@dataclass
class GotoStmt:
    target: ProcRef | None = None     # 已解析的过程引用（解析失败为 None）
    raw: str = ""
    lineno: int = 0


@dataclass
class CallStmt:
    name: str | None = None           # 取自 CALL 'XXX'
    using: list[str] = field(default_factory=list)
    tokens: list[str] = field(default_factory=list)   # 原始 token 串（供 leaf.translate_call 解析 USING/参数，镜像 MoveStmt）
    raw: str = ""
    lineno: int = 0


@dataclass
class PerformStmt:
    target: ProcRef | None = None     # PERFORM 目标（已解析）
    thru: ProcRef | None = None       # THRU 端点（已解析）
    header: list[str] = field(default_factory=list)     # 原始头部 token（UNTIL/VARYING 等）
    inline_body: list = field(default_factory=list)     # 内联体（list[Node]）
    raw: str = ""
    lineno: int = 0


@dataclass
class IfStmt:
    cond: list[str] = field(default_factory=list)
    then: list = field(default_factory=list)      # list[Node]
    els: list = field(default_factory=list)       # list[Node]
    raw: str = ""
    lineno: int = 0


@dataclass
class EvaluateStmt:
    subject: list[str] = field(default_factory=list)
    whens: list = field(default_factory=list)     # [(cond_tokens, [Node]), ...]
    raw: str = ""
    lineno: int = 0


# ── 结构节点（Program → Section → Paragraph）──────────────────────────────────

@dataclass
class Paragraph:
    label: str | None = None          # None 表段首无标号块
    stmts: list = field(default_factory=list)     # list[Node]
    lineno: int = 0


@dataclass
class Section:
    name: str = ""
    paragraphs: list = field(default_factory=list)
    lineno: int = 0


@dataclass
class Program:
    program_id: str = ""
    sections: list = field(default_factory=list)
    registry: object = None           # ProcRegistry（挂在根，相3 查表用）
