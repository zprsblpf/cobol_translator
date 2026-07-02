"""
结构体（拷贝簿）命名范式（确定性，不依赖 LLM）。

按 config/naming_conventions.yaml 的范式从 COPY 引用派生结构体注册表，
供规则引擎渲染 对象.getXxx()。从 graph.nodes 抽离，保证 graph → translator 单向依赖。
"""
from __future__ import annotations

import re

from config.yaml_cache import load as _load_yaml   # 唯一 YAML 加载入口（步骤09）
from translator import rules as _rules


_QUALIFIER_SEP = re.compile(r"\s+(?:OF|IN)\s+", re.IGNORECASE)


def parse_qualified_field_reference(text: str) -> tuple[str, tuple[str, ...]] | None:
    """Parse COBOL qualified field refs: ``A OF B`` / ``A IN B``.

    Returns upper-case COBOL names so callers can do deterministic lookups.
    A plain token is not a qualified reference and returns ``None``.
    """
    parts = [p.strip().upper() for p in _QUALIFIER_SEP.split(text.strip()) if p.strip()]
    if len(parts) < 2:
        return None
    if not all(re.fullmatch(r"[A-Z0-9-]+", p) for p in parts):
        return None
    return parts[0], tuple(parts[1:])


def resolve_qualified_field_reference(text: str, ctx) -> str | None:
    """Resolve a qualified COBOL field through ``ctx.qualified_field_map``.

    The map key is ``(field_name, (qualifier, ...))`` in upper-case COBOL
    spelling, and the value is the Java field name. Suffix qualifier matching
    lets a shorter ``A OF B`` resolve when the registry stores ``A OF B OF C``.
    Ambiguous or unknown references return ``None`` instead of guessing.
    """
    parsed = parse_qualified_field_reference(text)
    if parsed is None:
        return None
    field, qualifiers = parsed
    qmap = getattr(ctx, "qualified_field_map", {}) or {}
    direct = qmap.get((field, qualifiers))
    if direct:
        return direct
    matches = [
        java_name for (candidate, candidate_qualifiers), java_name in qmap.items()
        if candidate == field and tuple(candidate_qualifiers[-len(qualifiers):]) == qualifiers
    ]
    if len(set(matches)) == 1:
        return matches[0]
    return None


def build_struct_registry(state: dict) -> dict:
    """
    按命名范式（config/naming_conventions.yaml）从 COPY 引用派生结构体注册表。

      COPY <名><后缀>  →  结构体前缀 <名>，字段 <名>-XXX 渲染为 对象.getXxx()。
      Java 类名优先取 config/copy_mappings.yaml 的显式映射，否则按 <名>+默认后缀。

    拷贝簿源在盘上时其字段进 field_type_map 并优先命中，此注册表仅作兜底，
    两种情况输出一致。返回 dict 便于存入 state 复用。
    """
    naming = _load_yaml("naming_conventions.yaml")
    suffixes = [s.upper() for s in naming.get("copybook_suffixes", ["SKM", "REC", "KEY"])]
    sa = naming.get("struct_access", {}) or {}
    getter = sa.get("getter_prefix", "get")
    setter = sa.get("setter_prefix", "set")
    default_suffix = sa.get("default_class_suffix", "Params")

    records = {k.upper(): v for k, v in (_load_yaml("copy_mappings.yaml").get("records", {}) or {}).items()}

    prefixes: set[str] = set()
    classes: dict[str, str] = {}

    # 1) COPY <base><suffix> → 结构体前缀 base（最可靠来源）
    for cp in state.get("copy_refs", []):
        cpu = cp.upper()
        for suf in suffixes:
            if cpu.endswith(suf) and len(cpu) > len(suf):
                base = cpu[:-len(suf)]
                prefixes.add(base)
                classes[base] = records.get(cpu) or (_rules._pascal(base) + default_suffix)
                break

    # 2) 兜底：LINKAGE USING 的 <prefix>-PARAMS、各段内出现的 <prefix>-PARAMS
    for using in state.get("linkage_using", []):
        prefixes.add(using.upper().split("-")[0])
    for sec in state.get("sections_meta", []):
        for ln in sec.get("lines", []):
            for m in re.finditer(r"\b([A-Z0-9]+)-PARAMS\b", ln.upper()):
                prefixes.add(m.group(1))

    # 3) 对象名：有类名映射则首字母小写，否则按前缀+默认后缀
    objects: dict[str, str] = {}
    for p in prefixes:
        cls = classes.get(p)
        if cls:
            objects[p] = cls[0].lower() + cls[1:]
        else:
            objects[p] = _rules._java(p) + default_suffix
            classes[p] = _rules._pascal(p) + default_suffix

    return {
        "prefixes": prefixes, "objects": objects, "classes": classes,
        "getter": getter, "setter": setter, "default_suffix": default_suffix,
    }
