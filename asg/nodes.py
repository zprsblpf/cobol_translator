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
class Raw:
    """预渲染的 Java 行节点（步骤24C 绞杀项4 骨架装配③）：IO 形态吸收（BEGN for-each / findBy…Begn /
    repo.save…）由 skel.io_rewrite.rewrite_io_paras 命中后产出整段 Java，包成 Raw 替换原段节点。
    visit_Raw 直接吐 .lines（缩进由段体渲染统一施加），镜像旧 Stmt(kind="raw") 的 build_skeleton 分支。"""
    lines: list[str] = field(default_factory=list)
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
    tokens: list[str] = field(default_factory=list)   # 原始 token 串（供 leaf.translate_control 复刻 _sk_control，镜像 CallStmt 步骤21）
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


@dataclass
class BegnForeachStmt:
    """BEGN+NEXTR 自跳循环吸收后的结构节点（步骤25）：相3 渲染为 List + for-each。"""
    pfx: str = ""
    name: str = ""
    keys: list[tuple[str, str]] = field(default_factory=list)
    filters: list = field(default_factory=list)
    body: list = field(default_factory=list)
    raw: str = ""
    lineno: int = 0


@dataclass
class BegnSingleStmt:
    """单次 BEGN 等值定位吸收后的结构节点（步骤26）：相3 渲染为 findBy...Begn + isEmpty 分支。"""
    pfx: str = ""
    name: str = ""
    keys: list[tuple[str, str]] = field(default_factory=list)
    then_body: list = field(default_factory=list)
    raw: str = ""
    lineno: int = 0


@dataclass
class IoReadSingleStmt:
    """READR/READS 单条读吸收后的结构节点（步骤27）：finder + null 判断/try-catch。"""
    pfx: str = ""
    name: str = ""
    func: str = ""
    keys: list[tuple[str, str]] = field(default_factory=list)
    mode: str = "plain"  # plain | ok | notok | error
    then_body: list = field(default_factory=list)
    else_body: list = field(default_factory=list)
    try_tail: list = field(default_factory=list)
    raw: str = ""
    lineno: int = 0


# ── 结构节点（Program → Section → Paragraph）──────────────────────────────────

@dataclass
class IoWriteSingleStmt:
    """UPDAT/WRITR/DELET single write IO absorbed as save/delete structure."""
    pfx: str = ""
    name: str = ""
    func: str = ""
    is_new: bool = False
    is_delete: bool = False
    setters: list = field(default_factory=list)
    mode: str = "plain"  # plain | error
    then_body: list = field(default_factory=list)
    try_tail: list = field(default_factory=list)
    raw: str = ""
    lineno: int = 0


@dataclass
class Paragraph:
    label: str | None = None          # None 表段首无标号块
    stmts: list = field(default_factory=list)     # list[Node]
    body_lines: list[str] = field(default_factory=list)  # 原始 COBOL 行（供 PERFORM paragraph/THRU 登记 pending 方法）
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
