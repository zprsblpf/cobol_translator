"""
结构体（拷贝簿）命名范式（确定性，不依赖 LLM）。

按 config/naming_conventions.yaml 的范式从 COPY 引用派生结构体注册表，
供规则引擎渲染 对象.getXxx()。从 graph.nodes 抽离，保证 graph → translator 单向依赖。
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from translator import rules as _rules

CONFIG_DIR = Path(__file__).parent.parent / "config"


def _load_yaml(name: str) -> dict:
    try:
        with open(CONFIG_DIR / name, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


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
