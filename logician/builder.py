"""
逻辑文档生成器 — 核心构建器。

对应设计：docs/详细设计/步骤37-逻辑文档生成器设计.md §二。
设计思路：
1. 复用 asg.builder.build 构建 ASG 类型节点树
2. 复用 analyzer.callgraph.build_call_graph 构建调用链（段级）
3. DFS 从入口段沿 PERFORM 链追踪到结果叶子
4. 每路径生成 LogicPath（节点序列 + 词元 + 条件摘要）
5. 交叉点合并：被多条路径经过的节点标记 path_tags

路径 = 从入口到某个结果叶子的调用链（不是条件分支全排列）。
"""
from __future__ import annotations

from asg import builder as asg_builder
from asg import nodes
from analyzer import callgraph as cg_builder

from logician.models import (
    LogicDoc, LogicNode, LogicEdge, LogicPath, ResultLeaf,
)
from logician.tokens import extract_tokens, extract_io_call
from logician.results import find_results


# ── 构建 sections_meta（复用 analyzer.callgraph 所需格式）──────────────────

def _build_sections_meta(program: nodes.Program) -> list[dict]:
    """从 ASG Program 构建 sections_meta（兼容 analyzer.callgraph.build_call_graph 的输入格式）。

    sections_meta: [{name, lines, calls, go_tos, line_start, line_end}, ...]"""
    meta = []
    for sec in program.sections:
        lines = []
        calls = set()
        for para in sec.paragraphs:
            lines.extend(para.body_lines)
            for stmt in para.stmts:
                toks = getattr(stmt, "tokens", None) or []
                for t in toks:
                    u = t.upper().strip("'\"")
                    if u.endswith("IO") or "IO" in u:
                        calls.add(u)
        meta.append({
            "name": sec.name,
            "lines": lines,
            "calls": list(sorted(calls)),
            "line_start": sec.lineno,
            "line_end": sec.lineno + len(lines),
        })
    return meta


# ── 路径追踪（DFS 段级调用链）─────────────────────────────────────────────

def _trace_paths(
    asg_prog: nodes.Program,
    call_graph: dict[str, list[str]],
    entry_section: str,
    results: list[ResultLeaf],
    ws_tree=None,
) -> tuple[dict[str, LogicNode], list[LogicEdge], list[LogicPath]]:
    """段级 DFS 追踪：从入口段沿 PERFORM 链走，遇结果叶子终止。

    Returns:
        (nodes_map, edges, paths, sec_to_id) 四元组
    """
    # 预建 section → ASG Section 索引
    sec_map: dict[str, nodes.Section] = {}
    for sec in asg_prog.sections:
        sec_map[sec.name.upper()] = sec

    # 预建 result → section 索引
    result_sections: dict[str, list[ResultLeaf]] = {}
    for r in results:
        result_sections.setdefault(r.section.upper(), []).append(r)

    # 构建 token 提取上下文（用于 88 条件名展开等）
    _token_ctx = {"ws_tree": ws_tree} if ws_tree else None

    nodes_map: dict[str, LogicNode] = {}   # keyed by node_id
    sec_to_id: dict[str, str] = {}         # section → node_id
    edges: list[LogicEdge] = []
    paths: list[LogicPath] = []

    path_counter = [0]

    def _next_path_id() -> str:
        path_counter[0] += 1
        return f"PATH-{path_counter[0]:02d}"

    node_counter = [0]

    def _next_node_id() -> str:
        node_counter[0] += 1
        return f"N{node_counter[0]}"

    def _get_or_create_node(sec_name: str) -> LogicNode:
        """获取或创建段级 LogicNode。"""
        # 查找：先查 sec_to_id，再查 nodes_map
        existing_id = sec_to_id.get(sec_name)
        if existing_id and existing_id in nodes_map:
            return nodes_map[existing_id]

        nid = "ENTRY" if sec_name == entry_section else _next_node_id()
        sec = sec_map.get(sec_name)
        if sec is None:
            node = LogicNode(
                node_id=nid,
                type="entry" if sec_name == entry_section else "box",
                label=sec_name,
                section=sec_name,
            )
            nodes_map[nid] = node
            sec_to_id[sec_name] = nid
            return node

        # 收集段级词元
        all_sem = []
        all_verb = []
        io_calls = []
        for para in sec.paragraphs:
            for stmt in para.stmts:
                sem, verb = extract_tokens(stmt, _token_ctx)
                all_sem.extend(sem)
                all_verb.extend(verb)
                io = extract_io_call(stmt)
                if io:
                    io_calls.append(io)
                # 递归进入嵌套节点
                _collect_nested_tokens(stmt, all_sem, all_verb, io_calls)

        node_type = "entry" if sec_name == entry_section else "box"
        # 如果该段有 IF/EVALUATE → fork
        has_fork = any(isinstance(s, (nodes.IfStmt, nodes.EvaluateStmt))
                       for para in sec.paragraphs for s in para.stmts)
        if has_fork:
            node_type = "fork"

        node = LogicNode(
            node_id=nid,
            type=node_type,
            label=sec_name,
            section=sec_name,
            semantic_tokens=_dedup_ordered(all_sem),
            verb_tokens=_dedup_ordered(all_verb),
            io_calls=io_calls,
        )
        nodes_map[nid] = node
        sec_to_id[sec_name] = nid
        return node

    def _collect_nested_tokens(stmt, sem_list, verb_list, io_list):
        """递归收集嵌套子节点的词元。"""
        for attr in ("then", "els", "inline_body"):
            children = getattr(stmt, attr, None) or []
            for c in children:
                s, v = extract_tokens(c, _token_ctx)
                sem_list.extend(s)
                verb_list.extend(v)
                io = extract_io_call(c)
                if io:
                    io_list.append(io)
                _collect_nested_tokens(c, sem_list, verb_list, io_list)
        if isinstance(stmt, nodes.EvaluateStmt):
            for _cond, body in getattr(stmt, "whens", None) or []:
                for c in body:
                    s, v = extract_tokens(c, _token_ctx)
                    sem_list.extend(s)
                    verb_list.extend(v)
                    io = extract_io_call(c)
                    if io:
                        io_list.append(io)
                    _collect_nested_tokens(c, sem_list, verb_list, io_list)

    def _dfs(section: str, visited: set[str], path_nodes: list[str],
             edge_conditions: list, path_edges: list[tuple]):
        """DFS 沿调用链追踪到结果叶子。"""
        if section in visited:
            return
        visited = visited | {section}

        node = _get_or_create_node(section)
        path_nodes.append(node.node_id)

        # 检查当前段是否为结果叶子所在段
        leaf_results = result_sections.get(section.upper(), [])
        if leaf_results:
            for r in leaf_results:
                path_id = _next_path_id()
                # 按 node_id 从 nodes_map 收集路径词元
                collected_sem = []
                collected_verb = []
                for nid in path_nodes:
                    ln = nodes_map.get(nid)
                    if ln:
                        collected_sem.extend(ln.semantic_tokens)
                        collected_verb.extend(ln.verb_tokens)

                lpath = LogicPath(
                    path_id=path_id,
                    result_id=r.id,
                    node_sequence=list(path_nodes),
                    semantic_tokens=_dedup_ordered(collected_sem),
                    verb_tokens=_dedup_ordered(collected_verb),
                    edge_conditions=list(edge_conditions),
                )
                paths.append(lpath)
                r.paths.append(path_id)

                # 创建结果节点
                r_nid = _next_node_id()
                r_node = LogicNode(
                    node_id=r_nid,
                    type="result",
                    label=f"{r.kind}: {r.target}",
                    section=section,
                )
                nodes_map[r_nid] = r_node

                # 添加边：当前节点 → 结果节点
                edges.append(LogicEdge(
                    from_id=node.node_id,
                    to_id=r_nid,
                    kind="always",
                    path_ids=[path_id],
                ))
                # 结果节点加入路径序列（注意不在原 path_nodes 上改）
                full_sequence = list(path_nodes) + [r_nid]
                lpath.node_sequence = full_sequence

        # 沿调用链继续 DFS（跳过结果段——已经处理过了）
        for callee in call_graph.get(section, []):
            if callee in visited:
                continue
            # 创建边
            callee_node = _get_or_create_node(callee)
            edge = LogicEdge(
                from_id=node.node_id,
                to_id=callee_node.node_id,
                kind="call",
                path_ids=[],
            )
            if edge not in edges:
                edges.append(edge)

            _dfs(callee, visited, list(path_nodes), list(edge_conditions),
                 list(path_edges) + [(node.node_id, callee_node.node_id)])

    # ── 从入口开始 DFS ──
    if entry_section:
        _dfs(entry_section, set(), [], [], [])

    # ── 交叉点合并：统计每个节点被多少路径经过 ──
    for path in paths:
        seen_nodes = set()
        for nid in path.node_sequence:
            if nid not in seen_nodes:
                seen_nodes.add(nid)
                if nid in nodes_map:
                    if path.path_id not in nodes_map[nid].path_tags:
                        nodes_map[nid].path_tags.append(path.path_id)

    # 合并 edges 的 path_ids
    for edge in edges:
        for path in paths:
            for i in range(len(path.node_sequence) - 1):
                if (path.node_sequence[i] == edge.from_id
                        and path.node_sequence[i + 1] == edge.to_id):
                    if path.path_id not in edge.path_ids:
                        edge.path_ids.append(path.path_id)

    return nodes_map, edges, paths, sec_to_id


def _dedup_ordered(items: list[str]) -> list[str]:
    """去重保序。"""
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


# ── 入口 ──────────────────────────────────────────────────────────────────

def generate(program, ws_tree=None) -> LogicDoc:
    """CobolProgram → LogicDoc。

    Args:
        program: parser.cobol_parser.CobolProgram 对象（含 .sections / .program_id 等）
        ws_tree: 可选，parser.ws 解析的 WsNode 森林，用于 88 条件名展开

    Returns:
        LogicDoc 逻辑文档对象
    """
    # 1. 构建 ASG
    asg_prog = asg_builder.build(program)

    # 2. 构建 sections_meta + 调用链
    sections_meta = _build_sections_meta(asg_prog)
    cg_result = cg_builder.build_call_graph(sections_meta)
    call_graph = cg_result.get("call_graph", {})
    entry_section = cg_result.get("entry_section", "")

    # 3. 查找结果叶子
    results = find_results(asg_prog)

    # 4. 追踪路径
    nodes_map, edges, paths, sec_to_id = _trace_paths(
        asg_prog, call_graph, entry_section, results, ws_tree=ws_tree,
    )

    # 5. 入口节点
    entry_nid = sec_to_id.get(entry_section, "ENTRY")
    entry_node = nodes_map.get(entry_nid)
    if entry_node:
        entry_node.type = "entry"

    return LogicDoc(
        program_id=program.program_id,
        entry=entry_node,
        results=results,
        paths=paths,
        nodes=nodes_map,
        edges=edges,
    )
