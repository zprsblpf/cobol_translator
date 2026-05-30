"""
调用链分析（确定性，无 LLM）。

从入口 SECTION 出发，沿各段的 PERFORM 目标做 DFS，构建：
- call_graph: {SECTION: [按源序去重的被调 SECTION...]}（仅保留确实存在的 SECTION）
- callers:    {SECTION: [调用它的 SECTION...]}
- entry_section / entry_sequence: 入口段及其顶层 PERFORM 序列（供 execute() 接线）
- cycles:     检测到的调用环（多由 GO TO 制造），供人工审查
- markdown:   缩进展示的嵌套调用树，呈现长处理逻辑全貌
"""
from __future__ import annotations

import re

_PERFORM_RE = re.compile(
    r"\bPERFORM\s+([A-Z0-9][A-Z0-9\-]+)(?:\s+THRU\s+[A-Z0-9][A-Z0-9\-]+)?",
    re.IGNORECASE,
)


def _ordered_performs(lines: list[str], known: set[str]) -> list[str]:
    """从段代码按出现顺序提取 PERFORM 目标（去重保序，仅保留已知 SECTION）。"""
    seen: set[str] = set()
    result: list[str] = []
    for line in lines:
        for m in _PERFORM_RE.finditer(line):
            target = m.group(1).upper()
            if target in known and target not in seen:
                seen.add(target)
                result.append(target)
    return result


def build_call_graph(sections_meta: list[dict]) -> dict:
    if not sections_meta:
        return {
            "call_graph": {}, "callers": {}, "entry_section": "",
            "entry_sequence": [], "cycles": [], "max_depth": 0, "markdown": "",
        }

    known = {s["name"].upper() for s in sections_meta}

    # 1. 邻接表（保序）
    call_graph: dict[str, list[str]] = {}
    for sec in sections_meta:
        name = sec["name"].upper()
        call_graph[name] = _ordered_performs(sec.get("lines", []), known)

    # 2. 反向：调用者
    callers: dict[str, list[str]] = {n: [] for n in call_graph}
    for src, targets in call_graph.items():
        for t in targets:
            callers.setdefault(t, [])
            if src not in callers[t]:
                callers[t].append(src)

    # 3. 入口段（源序第一个）及其顶层序列
    entry_section = sections_meta[0]["name"].upper()
    entry_sequence = call_graph.get(entry_section, [])

    # 4. DFS 检测环 + 最大深度
    cycles: list[str] = []
    max_depth = 0
    seen_cycle_keys: set[str] = set()

    def dfs(node: str, stack: list[str], depth: int):
        nonlocal max_depth
        max_depth = max(max_depth, depth)
        for nxt in call_graph.get(node, []):
            if nxt in stack:
                # 回边 → 环
                idx = stack.index(nxt)
                cycle = stack[idx:] + [nxt]
                key = "->".join(sorted(set(cycle)))
                if key not in seen_cycle_keys:
                    seen_cycle_keys.add(key)
                    cycles.append(" → ".join(cycle))
                continue
            dfs(nxt, stack + [nxt], depth + 1)

    dfs(entry_section, [entry_section], 1)

    # 5. markdown 嵌套调用树（已展开的节点标记，避免环导致无限展开）
    md_lines = [f"# 调用链（入口: {entry_section}）\n", "## 嵌套调用树\n"]
    expanded: set[str] = set()

    def render(node: str, indent: int, path: set[str]):
        prefix = "  " * indent + "- "
        if node in path:
            md_lines.append(f"{prefix}{node}  (↑ 调用环)")
            return
        if node in expanded and call_graph.get(node):
            md_lines.append(f"{prefix}{node}  (↑ 见上文展开)")
            return
        md_lines.append(f"{prefix}{node}")
        expanded.add(node)
        for nxt in call_graph.get(node, []):
            render(nxt, indent + 1, path | {node})

    render(entry_section, 0, set())

    # 未被入口可达的段
    reachable = set(expanded)
    orphans = [n for n in call_graph if n not in reachable and n != entry_section]
    if orphans:
        md_lines.append("\n## 入口不可达的 SECTION（可能由 GO TO / 外部调用进入）\n")
        for o in orphans:
            md_lines.append(f"- {o}  (被调用者: {callers.get(o, []) or '无'})")

    if cycles:
        md_lines.append("\n## ⚠️ 调用环\n")
        for c in cycles:
            md_lines.append(f"- {c}")

    return {
        "call_graph": call_graph,
        "callers": callers,
        "entry_section": entry_section,
        "entry_sequence": entry_sequence,
        "cycles": cycles,
        "max_depth": max_depth,
        "markdown": "\n".join(md_lines) + "\n",
    }
