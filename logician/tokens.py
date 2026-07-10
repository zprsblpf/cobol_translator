"""
逻辑文档生成器 — 词元提取（语义层 + 动词层）。

对应设计：docs/详细设计/步骤37-逻辑文档生成器设计.md §二-2。
设计思路：每个 ASG 节点类型有对应的 _tokenize_<Type> 函数，通过 extract_tokens 统一分派。
IO 调用解析从 IoWriteSingleStmt/IoReadSingleStmt 节点字段直接读取（已由 ASG builder 吸收解析），
或从 CallStmt 的 token 序列推断 FUNCTION 值。
88 条件名展开需要访问 parser.ws 的工作存储树。
"""
from __future__ import annotations

from asg import nodes

from logician.models import IOCall

# ── 动词层词元（COBOL 原始动词）─────────────────────────────────────────────

# ── 语义层词元（按意图分组）─────────────────────────────────────────────────

# 赋值类
SEM_ASSIGN = "ASSIGN"        # MOVE src TO dst
SEM_RESET = "RESET"          # MOVE SPACES/ZEROS TO 结构体（初始化）
SEM_FUNC_SET = "FUNC_SET"    # MOVE READR/BEGN/WRITR TO xxx-FUNCTION

# 条件分支
SEM_BRANCH_IF = "BRANCH_IF"
SEM_BRANCH_SWITCH = "BRANCH_SWITCH"

# 调用
SEM_CALL_PROC = "CALL_PROC"  # PERFORM section-name
SEM_CALL_PROG = "CALL_PROG"  # CALL 'subprogram'
SEM_LOOP = "LOOP"            # PERFORM inline loop

# 跳转/返回
SEM_JUMP = "JUMP"
SEM_RETURN = "RETURN"

# DB IO
SEM_DB_READR = "DB_READR"
SEM_DB_BEGN = "DB_BEGN"     # BEGN 游标开始（含 for-each 和单次定位）
SEM_DB_NEXTR = "DB_NEXTR"
SEM_DB_WRITR = "DB_WRITR"
SEM_DB_UPDAT = "DB_UPDAT"
SEM_DB_DELET = "DB_DELET"

# 其他
SEM_MATH = "MATH"             # ADD/SUBTRACT/MULTIPLY/DIVIDE/COMPUTE
SEM_TEXT_OP = "TEXT_OP"       # STRING / UNSTRING / INSPECT
SEM_SEARCH = "SEARCH"
SEM_FATAL = "FATAL"           # 错误终止

# 兜底
SEM_UNRESOLVED = "UNRESOLVED"

# ── IO 功能码 → 语义层映射（用于 IoWriteSingleStmt / IoReadSingleStmt）───────

_FUNC_TO_SEM = {
    "READR": SEM_DB_READR,
    "BEGN": SEM_DB_BEGN,
    "NEXTR": SEM_DB_NEXTR,
    "WRITR": SEM_DB_WRITR,
    "UPDAT": SEM_DB_UPDAT,
    "DELET": SEM_DB_DELET,
}


def _first_verb(tokens: list[str]) -> str:
    """提取 token 列表的首动词（大写）。"""
    for t in tokens:
        u = t.upper().strip("'\"")
        if u and u[0].isalpha():
            return u
    return ""


# ── 按 ASG 节点类型的词元提取 ──────────────────────────────────────────────

def _tokenize_MoveStmt(node: nodes.MoveStmt, ctx=None) -> tuple[list[str], list[str]]:
    """MOVE → 按目标语义分派 ASSIGN / RESET / FUNC_SET。

    判定逻辑（优先级从高到低）：
    1. 如果 TO 目标是 xxx-FUNCTION 且源是 READR/BEGN/WRITR/UPDAT/DELET → FUNC_SET
    2. 如果源是 SPACES/ZEROS 且目标是 01 级结构体 → RESET
    3. 其余 → ASSIGN"""
    semantic = SEM_ASSIGN
    toks = [t.upper().strip("'\"") for t in node.tokens]

    # 检查源端是否为预留的 mock object
    has_readr = any(v in toks for v in ("READR", "BEGN", "WRITR", "UPDAT", "DELET"))
    has_function = any("FUNCTION" in t for t in toks)
    if has_readr and has_function:
        semantic = SEM_FUNC_SET
    elif any(v in toks for v in ("SPACES", "ZEROS", "ZERO", "SPACE")):
        semantic = SEM_RESET
    else:
        semantic = SEM_ASSIGN

    return [semantic], ["MOVE"]


def _tokenize_CallStmt(node: nodes.CallStmt, ctx=None) -> tuple[list[str], list[str]]:
    """CALL → 按目标程序名和 FUNCTION 值分派 DB_* / CALL_PROG。

    IoWriteSingleStmt/IoReadSingleStmt 已由 ASG builder 吸收的优先。
    原始 CallStmt 从 token 中推断 FUNCTION 值。"""
    # 从 token 中查 FUNCTION 设置
    tokens_upper = [t.upper().strip("'\"") for t in node.tokens]

    # 优先查 IoWrite / IoRead 节点（已吸收），但这里是原始 CallStmt
    # 从 token 序列推断 FUNCTION：找 MOVE xxx TO yyy-FUNCTION 模式
    func_code = None
    for i, t in enumerate(tokens_upper):
        if t == "FUNCTION" and i > 0:
            # 可能是 yyy-FUNCTION
            pass
        if t in ("READR", "BEGN", "NEXTR", "WRITR", "UPDAT", "DELET"):
            # 看看是否被 MOVE 到 FUNCTION 字段
            if i + 2 < len(tokens_upper) and tokens_upper[i + 1] == "TO":
                func_code = t
                break

    # 检查 CALL 目标名是否以 IO 结尾
    name = (node.name or "").upper()
    is_io = name.endswith("IO")

    if func_code and is_io:
        sem = _FUNC_TO_SEM.get(func_code, SEM_CALL_PROG)
    elif is_io:
        sem = SEM_CALL_PROG  # IO 调用但未识别功能码
    else:
        sem = SEM_CALL_PROG

    return [sem], ["CALL"]


def _tokenize_IfStmt(node: nodes.IfStmt, ctx=None) -> tuple[list[str], list[str]]:
    """IF → BRANCH_IF。

    如果 ctx 包含 ws_tree，尝试展开 88 条件名（如 IS-6PWB → WSAA-VAL28-PRD = '6PWB'）。"""
    sem = [SEM_BRANCH_IF]
    verb = ["IF"]
    # 如果有 WS 树且条件 token 可能为 88 条件名，尝试展开
    if ctx and isinstance(ctx, dict) and ctx.get("ws_tree"):
        ws_tree = ctx["ws_tree"]
        for tok in node.cond:
            expanded = expand_88_condition(tok, ws_tree)
            if expanded:
                # 88 条件名有对应展开 → 附加到语义层
                sem.append(f"88:{expanded}")
    return sem, verb


def _tokenize_EvaluateStmt(node: nodes.EvaluateStmt, ctx=None) -> tuple[list[str], list[str]]:
    """EVALUATE → BRANCH_SWITCH。"""
    return [SEM_BRANCH_SWITCH], ["EVALUATE"]


def _tokenize_PerformStmt(node: nodes.PerformStmt, ctx=None) -> tuple[list[str], list[str]]:
    """PERFORM → 有 inline_body 为 LOOP，out-of-line 为 CALL_PROC。"""
    if node.inline_body:
        return [SEM_LOOP], ["PERFORM"]
    return [SEM_CALL_PROC], ["PERFORM"]


def _tokenize_GotoStmt(node: nodes.GotoStmt, ctx=None) -> tuple[list[str], list[str]]:
    """GO TO → JUMP。"""
    return [SEM_JUMP], ["GO"]


def _tokenize_BegnForeachStmt(node: nodes.BegnForeachStmt, ctx=None) -> tuple[list[str], list[str]]:
    """BEGN for-each → DB_BEGN。"""
    return [SEM_DB_BEGN], ["BEGN"]


def _tokenize_BegnSingleStmt(node: nodes.BegnSingleStmt, ctx=None) -> tuple[list[str], list[str]]:
    """单次 BEGN → DB_BEGN。"""
    return [SEM_DB_BEGN], ["BEGN"]


def _tokenize_IoReadSingleStmt(node: nodes.IoReadSingleStmt, ctx=None) -> tuple[list[str], list[str]]:
    """READR 单条读 → DB_READR。"""
    sem = _FUNC_TO_SEM.get(node.func.upper(), SEM_DB_READR)
    return [sem], [node.func.upper()]


def _tokenize_IoWriteSingleStmt(node: nodes.IoWriteSingleStmt, ctx=None) -> tuple[list[str], list[str]]:
    """WRITR/UPDAT/DELET → 对应 DB_*。"""
    sem = _FUNC_TO_SEM.get(node.func.upper(), SEM_UNRESOLVED)
    return [sem], [node.func.upper()]


def _tokenize_Leaf(node: nodes.Leaf, ctx=None) -> tuple[list[str], list[str]]:
    """Leaf（兜底节点）→ 按首动词分派。"""
    verb = _first_verb(node.tokens)
    verb_upper = verb.upper()

    if verb_upper in ("EXIT", "GOBACK", "STOP"):
        return [SEM_RETURN], [verb_upper]
    elif verb_upper in ("STRING", "UNSTRING", "INSPECT"):
        return [SEM_TEXT_OP], [verb_upper]
    elif verb_upper == "SEARCH":
        return [SEM_SEARCH], [verb_upper]
    elif verb_upper in ("ADD", "SUBTRACT", "MULTIPLY", "DIVIDE", "COMPUTE"):
        return [SEM_MATH], [verb_upper]
    elif verb_upper in ("CONTINUE", "NEXT"):
        # CONTINUE / NEXT SENTENCE 无实质语义
        return [SEM_RETURN], [verb_upper]
    else:
        return [SEM_UNRESOLVED], [verb_upper or "?"]


def _tokenize_Raw(node: nodes.Raw, ctx=None) -> tuple[list[str], list[str]]:
    """Raw（预渲染 Java 行）→ 视为已解析，不做词元提取。"""
    return [], []


def _tokenize_Paragraph(node: nodes.Paragraph, ctx=None) -> tuple[list[str], list[str]]:
    """Paragraph → 如果末尾语句是 RETURN，产生 RETURN 词元。

    Paragraph 本身不贡献词元（词元由其 stmts 子节点贡献），
    但末尾 EXIT/GOBACK 会由子树中的 Leaf 贡献。"""
    return [], []


# ── 统一分派 ──────────────────────────────────────────────────────────────

_TOKENIZER_DISPATCH = {
    "MoveStmt": _tokenize_MoveStmt,
    "CallStmt": _tokenize_CallStmt,
    "IfStmt": _tokenize_IfStmt,
    "EvaluateStmt": _tokenize_EvaluateStmt,
    "PerformStmt": _tokenize_PerformStmt,
    "GotoStmt": _tokenize_GotoStmt,
    "BegnForeachStmt": _tokenize_BegnForeachStmt,
    "BegnSingleStmt": _tokenize_BegnSingleStmt,
    "IoReadSingleStmt": _tokenize_IoReadSingleStmt,
    "IoWriteSingleStmt": _tokenize_IoWriteSingleStmt,
    "Leaf": _tokenize_Leaf,
    "Raw": _tokenize_Raw,
    "Paragraph": _tokenize_Paragraph,
}


def node_type_name(node) -> str:
    """返回 ASG 节点类型名。"""
    return type(node).__name__


def extract_tokens(node, ctx=None) -> tuple[list[str], list[str]]:
    """ASG 节点 → (semantic_tokens, verb_tokens) 词元对。

    Args:
        node: ASG 节点（asg.nodes 中定义的类型）
        ctx: 可选上下文（如 WS 树，供 88 条件名展开）

    Returns:
        (semantic_tokens, verb_tokens) 二元组
    """
    tn = node_type_name(node)
    tokenizer = _TOKENIZER_DISPATCH.get(tn)
    if tokenizer is None:
        # 未知节点类型，检查是否有 tokens 属性
        toks = getattr(node, "tokens", None) or []
        verb = _first_verb(toks)
        return [SEM_UNRESOLVED], [verb or tn]
    return tokenizer(node, ctx)


def extract_io_call(node) -> IOCall | None:
    """从 ASG 节点提取 IO 调用信息。

    优先从 IoWriteSingleStmt / IoReadSingleStmt / BegnForeachStmt / BegnSingleStmt 读取，
    对原始 CallStmt 则从 token 推断。"""
    if isinstance(node, nodes.IoWriteSingleStmt):
        return IOCall(
            func=node.func.upper() if node.func else "WRITR",
            table=node.name.upper() if node.name else "",
            raw=node.raw,
        )
    if isinstance(node, nodes.IoReadSingleStmt):
        return IOCall(
            func=node.func.upper() if node.func else "READR",
            table=node.name.upper() if node.name else "",
            raw=node.raw,
        )
    if isinstance(node, nodes.BegnForeachStmt):
        return IOCall(
            func="BEGN",
            table=node.name.upper() if node.name else "",
            raw=node.raw,
        )
    if isinstance(node, nodes.BegnSingleStmt):
        return IOCall(
            func="BEGN",
            table=node.name.upper() if node.name else "",
            raw=node.raw,
        )
    if isinstance(node, nodes.CallStmt):
        # 从 token 推断，参考 knowledge/io_call_patterns.md
        toks_upper = [t.upper().strip("'\"") for t in node.tokens]
        io_func = None
        for t in toks_upper:
            if t in ("READR", "BEGN", "NEXTR", "WRITR", "UPDAT", "DELET"):
                io_func = t
                break
        if io_func:
            return IOCall(
                func=io_func,
                table=node.name.upper() if node.name else "",
                raw=node.raw,
            )
    return None


def expand_88_condition(cond_name: str, ws_tree) -> str | None:
    """88 条件名 → 等价条件表达式。

    从 WORKING-STORAGE 树中查找 88 条件名的 holder 字段和值列表，
    展开为 "HOLDER = 'VALUE'" 或 "HOLDER IN ('V1', 'V2')" 形式。

    88 条件在 WsNode 中以 conditions 列表形式挂载在 holder 字段上：
        WSAA-VAL28-PRD PIC X(04).        ← WsNode (name="WSAA-VAL28-PRD")
            88 IS-6PWB VALUES '6PWB'.    ← Condition (name="IS-6PWB", values=["6PWB"])
            88 IS-WPDH VALUES 'WPDH'.    ← Condition (name="IS-WPDH", values=["WPDH"])

    Args:
        cond_name: 88 条件名（如 IS-6PWB）
        ws_tree: list[WsNode] — parser.ws.parse_ws 产出

    Returns:
        展开后的表达式字符串，未解析返回 None
    """
    if ws_tree is None:
        return None

    try:
        from parser.ws.model import WsNode
    except ImportError:
        return None

    try:
        for entry in _walk_ws_entries(ws_tree):
            conds = entry.conditions if hasattr(entry, "conditions") else []
            for cond in conds:
                if cond.name.upper() == cond_name.upper():
                    # holder 字段名 = 挂载 88 条件的 WsNode 自身的 name
                    holder = entry.name
                    values = cond.values
                    if holder and values:
                        if len(values) == 1:
                            return f"{holder} = '{values[0]}'"
                        else:
                            vals = ", ".join(f"'{v}'" for v in values)
                            return f"{holder} IN ({vals})"
    except Exception:
        pass
    return None


def _walk_ws_entries(ws_tree):
    """递归遍历 WS 节点森林（先序遍历）。"""
    stack = list(ws_tree) if isinstance(ws_tree, (list, tuple)) else [ws_tree]
    while stack:
        node = stack.pop()
        yield node
        children = getattr(node, "children", None) or []
        stack.extend(reversed(children))
