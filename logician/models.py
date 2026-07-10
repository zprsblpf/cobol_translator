"""
逻辑文档生成器 — 数据模型（dataclass 平铺）。

对应设计：docs/详细设计/步骤37-逻辑文档生成器设计.md §二。
设计思路：7 个 dataclass 覆盖逻辑树全部层级，从顶层 LogicDoc 到底层 IOCall/EdgeCondition。
所有节点扁平化（nodes dict + edges list），路径通过 node_sequence 引用节点，交叉点通过 path_tags 记录。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class IOCall:
    """IO 调用记录。

    func: READR / BEGN / NEXTR / WRITR / UPDAT / DELET
    table: 操作的目标表名（如 TMRDPF、TMLCLST）
    raw: 原始 COBOL CALL 文本"""
    func: str = ""
    table: str = ""
    raw: str = ""


@dataclass
class EdgeCondition:
    """边上的条件信息。

    expr: 展开后的条件表达式（含 88 条件名展开）
    branch: "yes" 条件真分支 / "no" 假分支
    raw: 原始 COBOL 条件文本"""
    expr: str = ""
    branch: str = ""    # "yes" | "no"
    raw: str = ""


@dataclass
class LogicNode:
    """逻辑树节点。

    node_id: 唯一 ID，"ENTRY" 固定为入口
    type: "entry" / "box"（普通处理） / "fork"（条件分支） / "result"（结果叶子）
    label: 显示名，如 "1500-READ-ELPO"
    section: 所属 COBOL SECTION 名
    cobol_lines: 原始 COBOL 行
    semantic_tokens: 语义层词元列表（如 ["CALL_PROC", "DB_READR"]）
    verb_tokens: 动词层词元列表（如 ["PERFORM", "CALL"]）
    io_calls: 本节点的 IO 调用
    path_tags: 途经此节点的 PATH-ID 列表"""
    node_id: str = ""
    type: str = ""                     # "entry" | "box" | "fork" | "result"
    label: str = ""
    section: str | None = None
    cobol_lines: list[str] = field(default_factory=list)
    semantic_tokens: list[str] = field(default_factory=list)
    verb_tokens: list[str] = field(default_factory=list)
    io_calls: list[IOCall] = field(default_factory=list)
    path_tags: list[str] = field(default_factory=list)


@dataclass
class LogicEdge:
    """逻辑树边。

    from_id / to_id: 起点/终点 node_id
    kind: "always"（无条件）/ "conditional"（条件分支）/ "call"（PERFORM 调用）
    branch: "yes" / "no"（仅 condition 时有意义）
    expr: 条件表达式（仅 condition 时）
    path_ids: 经过此边的路径"""
    from_id: str = ""
    to_id: str = ""
    kind: str = "always"             # "always" | "conditional" | "call"
    branch: str | None = None        # "yes" | "no" | None
    expr: str | None = None
    path_ids: list[str] = field(default_factory=list)


@dataclass
class LogicPath:
    """一条从入口到结果叶子的完整路径。

    path_id: "PATH-01"
    result_id: 指向的结果叶子 ID
    node_sequence: 经过的 node_id 列表（顺序）
    semantic_tokens: 路径级语义摘要（去重合并）
    verb_tokens: 路径级动词摘要
    edge_conditions: 路径上的条件分支"""
    path_id: str = ""
    result_id: str = ""
    node_sequence: list[str] = field(default_factory=list)
    semantic_tokens: list[str] = field(default_factory=list)
    verb_tokens: list[str] = field(default_factory=list)
    edge_conditions: list[EdgeCondition] = field(default_factory=list)


@dataclass
class ResultLeaf:
    """结果叶子：路径的终点。

    id: "R-01"
    kind: "table_insert" / "table_update" / "table_delete" / "abend" / "return"
    target: 表名（如 TMRDPF）或错误段名或 "EXIT/GOBACK"
    section: 所在 SECTION
    paths: 到达此结果的路径列表"""
    id: str = ""
    kind: str = ""          # "table_insert" | "table_update" | "table_delete" | "abend" | "return"
    target: str = ""
    section: str = ""
    paths: list[str] = field(default_factory=list)


@dataclass
class LogicDoc:
    """逻辑文档顶层容器。

    program_id: COBOL PROGRAM-ID
    schema_version: 结构版本号
    side: "COBOL" 或 "Java"
    entry: 入口节点
    results: 结果叶子清单
    paths: 路径列表
    nodes: 节点字典 {node_id: LogicNode}
    edges: 边列表"""
    program_id: str = ""
    schema_version: str = "1.0"
    side: str = "COBOL"
    entry: LogicNode | None = None
    results: list[ResultLeaf] = field(default_factory=list)
    paths: list[LogicPath] = field(default_factory=list)
    nodes: dict[str, LogicNode] = field(default_factory=dict)
    edges: list[LogicEdge] = field(default_factory=list)
