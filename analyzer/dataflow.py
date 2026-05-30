"""
变量数据流分析（确定性，无 LLM）。

逐段抽取变量的写（MOVE…TO / COMPUTE X= / ADD…TO|GIVING / SUBTRACT…FROM|GIVING /
MULTIPLY…GIVING / DIVIDE…GIVING / SET…TO / INITIALIZE）与读（语句中出现的字段引用），
得到 var_lifecycle: {java_name: {written_in:[SEC...], read_in:[SEC...]}}，
并标注跨段风险（读先写后、仅写未读、仅读未写）。
"""
from __future__ import annotations

import re

from parser.variable_resolver import _cobol_to_java_name

# COBOL 标识符（允许连字符，至少 2 段或含连字符）
_IDENT_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+")

_MOVE_RE = re.compile(r"\bMOVE\b\s+.+?\bTO\b\s+(.+)$", re.IGNORECASE)
_COMPUTE_RE = re.compile(r"\bCOMPUTE\b\s+(.+?)(?:\bROUNDED\b)?\s*=", re.IGNORECASE)
_ADD_RE = re.compile(r"\bADD\b\s+.+?\bTO\b\s+(.+)$", re.IGNORECASE)
_SUBTRACT_RE = re.compile(r"\bSUBTRACT\b\s+.+?\bFROM\b\s+(.+)$", re.IGNORECASE)
_GIVING_RE = re.compile(r"\bGIVING\b\s+(.+)$", re.IGNORECASE)
_SET_RE = re.compile(r"\bSET\b\s+(.+?)\bTO\b", re.IGNORECASE)
_INIT_RE = re.compile(r"\bINITIALIZE\b\s+(.+)$", re.IGNORECASE)


def _java_idents(text: str, field_map: dict) -> set[str]:
    """文本中所有映射到已知字段的 java 名。"""
    out: set[str] = set()
    for m in _IDENT_RE.finditer(text):
        jn = _cobol_to_java_name(m.group(0))
        if jn in field_map:
            out.add(jn)
    return out


def _write_targets(line: str, field_map: dict) -> set[str]:
    """单行的写目标 java 名集合。"""
    targets: set[str] = set()
    chunks: list[str] = []
    for rx in (_MOVE_RE, _ADD_RE, _SUBTRACT_RE, _SET_RE, _INIT_RE, _COMPUTE_RE):
        m = rx.search(line)
        if m:
            chunks.append(m.group(1))
    gm = _GIVING_RE.search(line)
    if gm:
        chunks.append(gm.group(1))
    for chunk in chunks:
        # 去掉 GIVING/ROUNDED 等后缀关键字之后的内容只保留目标标识符
        chunk = re.split(r"\bGIVING\b|\bROUNDED\b|\bON\b|\bSIZE\b", chunk, flags=re.IGNORECASE)[0]
        targets |= _java_idents(chunk, field_map)
    return targets


def analyze_dataflow(sections_meta: list[dict], field_type_map: dict) -> dict:
    var_lifecycle: dict[str, dict] = {}

    def _touch(jn: str):
        if jn not in var_lifecycle:
            var_lifecycle[jn] = {"written_in": [], "read_in": []}

    for sec in sections_meta:
        name = sec["name"].upper()
        writes: set[str] = set()
        reads: set[str] = set()
        for line in sec.get("lines", []):
            reads |= _java_idents(line, field_type_map)
            writes |= _write_targets(line, field_type_map)
        for jn in writes:
            _touch(jn)
            if name not in var_lifecycle[jn]["written_in"]:
                var_lifecycle[jn]["written_in"].append(name)
        for jn in reads:
            _touch(jn)
            if name not in var_lifecycle[jn]["read_in"]:
                var_lifecycle[jn]["read_in"].append(name)

    # 执行顺序代理：源序索引
    order = {sec["name"].upper(): i for i, sec in enumerate(sections_meta)}

    review_items: list[str] = []
    read_before_write: list[str] = []
    only_written: list[str] = []
    only_read: list[str] = []
    for jn, info in var_lifecycle.items():
        w, r = info["written_in"], info["read_in"]
        if w and not r:
            only_written.append(jn)
        elif r and not w:
            only_read.append(jn)
        elif w and r:
            first_write = min(order.get(s, 1 << 30) for s in w)
            first_read = min(order.get(s, 1 << 30) for s in r)
            if first_read < first_write:
                read_before_write.append(jn)

    if read_before_write:
        review_items.append(
            f"⚠️ 数据流-读先写后（{len(read_before_write)} 个变量，可能依赖入参/默认值或更早赋值）: "
            f"{read_before_write[:15]}{' …' if len(read_before_write) > 15 else ''}"
        )
    multi_writer = [jn for jn, i in var_lifecycle.items() if len(i["written_in"]) > 1]
    if multi_writer:
        review_items.append(
            f"ℹ️ 数据流-被多段写的共享变量 {len(multi_writer)} 个（跨段贯穿，靠共享 State 保证一致）"
        )
    if only_read:
        review_items.append(
            f"ℹ️ 数据流-仅读未写 {len(only_read)} 个（多为常量/入参）: "
            f"{only_read[:10]}{' …' if len(only_read) > 10 else ''}"
        )

    return {
        "var_lifecycle": var_lifecycle,
        "review_items": review_items,
    }


def writers_context(section_name: str, sections_meta: list[dict],
                    field_type_map: dict, var_lifecycle: dict, max_vars: int = 20) -> str:
    """为指定段生成"本段读取的变量在哪些段被写入"的跨段上下文（注入 LLM 提示）。"""
    sec = next((s for s in sections_meta if s["name"].upper() == section_name.upper()), None)
    if not sec:
        return ""
    reads: set[str] = set()
    for line in sec.get("lines", []):
        reads |= _java_idents(line, field_type_map)
    lines: list[str] = []
    for jn in sorted(reads):
        info = var_lifecycle.get(jn)
        if not info:
            continue
        writers = [w for w in info["written_in"] if w != section_name.upper()]
        if writers:
            lines.append(f"- {jn} ← 由 {', '.join(writers[:5])} 写入")
        if len(lines) >= max_vars:
            break
    if not lines:
        return ""
    return "## 跨段数据流（本段所读变量在别处被写，注意取值来源）\n" + "\n".join(lines)
