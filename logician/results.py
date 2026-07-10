"""
逻辑文档生成器 — 结果叶子识别。

对应设计：docs/详细设计/步骤37-逻辑文档生成器设计.md §二-3。
设计思路：遍历 ASG Program 的每个 Section → Paragraph → stmts，识别 5 类结果叶子：
1. table_insert — IoWriteSingleStmt.func == "WRITR"
2. table_update — IoWriteSingleStmt.func == "UPDAT"
3. table_delete — IoWriteSingleStmt.func == "DELET"
4. abend — 错误终止（FATAL-ERROR / 5xx-ERROR PERFORM / CALL '...ERROR'）
5. return — EXIT / GOBACK / STOP RUN（无后续实质性操作）
"""
from __future__ import annotations

from asg import nodes
from logician.models import ResultLeaf
from logician.tokens import extract_tokens, extract_io_call


def find_results(program: nodes.Program) -> list[ResultLeaf]:
    """遍历 ASG Program，识别所有结果叶子。

    Args:
        program: ASG Program 节点树（asg.builder.build 产出）

    Returns:
        去重的 ResultLeaf 列表
    """
    results: dict[str, ResultLeaf] = {}
    _counter = [0]

    def _next_id() -> str:
        _counter[0] += 1
        return f"R-{_counter[0]:02d}"

    def _walk_stmts(stmts: list, section_name: str):
        for stmt in stmts:
            _check_result(stmt, section_name, results, _next_id)

            # 递归进入嵌套子节点
            for attr in ("then", "els", "inline_body"):
                children = getattr(stmt, attr, None) or []
                _walk_stmts(children, section_name)

            # EVALUATE 的 WHEN 分支
            if isinstance(stmt, nodes.EvaluateStmt):
                for _cond, body in getattr(stmt, "whens", None) or []:
                    _walk_stmts(body, section_name)

    for sec in program.sections:
        sec_name = sec.name.upper() if sec.name else "?"
        for para in sec.paragraphs:
            _walk_stmts(para.stmts, sec_name)

    return list(results.values())


def _check_result(
    stmt,
    section_name: str,
    results: dict[str, ResultLeaf],
    next_id,
):
    """检查单个 ASG 节点是否为结果叶子，是则加入 results。"""
    rid = None
    kind = ""
    target = ""

    if isinstance(stmt, nodes.IoWriteSingleStmt):
        func = stmt.func.upper() if stmt.func else ""
        tbl = stmt.name.upper() if stmt.name else "?"
        if func == "WRITR":
            kind = "table_insert"
        elif func == "UPDAT":
            kind = "table_update"
        elif func == "DELET":
            kind = "table_delete"
        else:
            return  # 非可识别结果
        target = tbl
        # IoWrite 的 func+table 组合唯一标识
        rid = f"{func}:{tbl}"

    elif isinstance(stmt, nodes.CallStmt):
        # 检查 CALL 'xxxERROR' / CALL 'xxx-ERROR'
        name = (stmt.name or "").upper()
        if "ERROR" in name:
            kind = "abend"
            target = name
            rid = f"ABEND:{name}"

    elif isinstance(stmt, nodes.PerformStmt):
        # 检查 PERFORM 5xx-ERROR（错误处理段）
        target_name = None
        if stmt.target:
            target_name = stmt.target.name.upper() if stmt.target.name else None
        if target_name and "ERROR" in target_name:
            kind = "abend"
            target = target_name
            rid = f"ABEND:{target_name}"

    elif isinstance(stmt, nodes.Leaf):
        # 检查 EXIT / GOBACK / STOP RUN
        toks_upper = [t.upper().strip("'\"") for t in stmt.tokens]
        if not toks_upper:
            return
        verb = toks_upper[0]
        if verb in ("EXIT", "GOBACK"):
            kind = "return"
            target = verb
            rid = f"RETURN:{verb}"
        elif verb == "STOP":
            kind = "return"
            target = "STOP RUN"
            rid = "RETURN:STOP_RUN"

    elif isinstance(stmt, nodes.GotoStmt):
        # GO TO xxx-EXIT / GO TO EXIT 视为 return
        target_name = stmt.target.name.upper() if stmt.target and stmt.target.name else ""
        if target_name and "EXIT" in target_name:
            kind = "return"
            target = target_name
            rid = f"RETURN:{target_name}"

    if rid and kind:
        if rid not in results:
            results[rid] = ResultLeaf(
                id=next_id(),
                kind=kind,
                target=target,
                section=section_name,
                paths=[],
            )
