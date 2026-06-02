"""
主线 SECTION 方法体确定性翻译的备料与渲染（步骤07）。

用途：把 CobolProgram 收敛成规则引擎 rules.Ctx 所需的上下文，并把单个 SECTION 的
      COBOL 段体确定性翻译为 Java 方法体（复用 segmenter + rules，无 LLM）。
对应设计：docs/详细设计/步骤07-主线SECTION方法体确定性翻译设计.md。

设计思路：
- 备料配方与 parser.pipeline / graph 同源（resolve→field_type_map、build_struct_registry、io_mappings），
  保证主线与 graph 规则命中的叶子 Java 一致（仅前缀 wsaa. vs st. 不同）。
- 后处理按步骤07 决策 A=方案B（仅数组下标 + wsaa. 前缀，不引入多模块路由）、
  B=B1（this.X() 补成 this.X(wsaa, using…)），复用 postprocess 的公共件。
- ctx 程序级算一次；leaves/_counter/flow_* 是段级状态，每段渲染前重置。
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from parser.variable_resolver import resolve, build_field_type_map
from translator import rules as _rules
from translator.naming import build_struct_registry
from translator.postprocess import fix_array_subscripts, _prefix_fields_outside_strings
from translator.skeleton import _section_to_method
from translator.segmenter import segment, split_paragraphs

CONFIG_DIR = Path(__file__).parent.parent.parent / "config"


def _load_io_maps() -> dict:
    """载 config/io_mappings.yaml 并合并 io_programs(+io_programs2)/date/system/default（同 context.py）。"""
    try:
        with open(CONFIG_DIR / "io_mappings.yaml", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except FileNotFoundError:
        cfg = {}
    return {
        "io_programs": {**cfg.get("io_programs", {}), **cfg.get("io_programs2", {})},
        "date_programs": cfg.get("date_programs", {}),
        "system_programs": cfg.get("system_programs", {}),
        "io_default_pattern": cfg.get("io_default_pattern", {}),
    }


def build_body_ctx(program) -> tuple[_rules.Ctx, list[str]]:
    """CobolProgram → (rules.Ctx, ws_field_names)。ws_field_names 仅含 WORKING-STORAGE 字段（用于 wsaa. 前缀）。"""
    # field_type_map 用 WS+LINKAGE 全量（同 pipeline，供规则判型）；前缀集只取 WS（LINKAGE 是方法入参，裸名）
    field_type_map = build_field_type_map(resolve(program.working_storage + program.linkage_vars))
    ws_field_names = [f.java_name for f in resolve(program.working_storage)]
    state = {
        "copy_refs": list(program.copy_refs),
        "linkage_using": list(program.linkage_using),
        "sections_meta": [{"name": s.name, "lines": s.lines, "calls": s.calls} for s in program.sections],
    }
    reg = build_struct_registry(state)
    io = _load_io_maps()
    ctx = _rules.Ctx(
        field_type_map=field_type_map,
        section_to_method=_section_to_method,
        known_sections={s.name.upper() for s in program.sections},
        io_struct_prefixes=reg["prefixes"], struct_objects=reg["objects"],
        struct_classes=reg["classes"], struct_getter=reg["getter"],
        struct_setter=reg["setter"], struct_default_suffix=reg["default_suffix"],
        io_programs=io["io_programs"], date_programs=io["date_programs"],
        system_programs=io["system_programs"], io_default_pattern=io["io_default_pattern"],
    )
    return ctx, ws_field_names


def reset_section(ctx: _rules.Ctx) -> None:
    """重置段级状态，避免叶子编号/循环标签/结构体功能码跨段串号。"""
    ctx.leaves = []
    ctx._counter = [0]
    ctx.flow_label = None
    ctx.flow_paragraphs = set()
    ctx.struct_function = {}


def _postprocess_body(body: str, ws_field_names: list[str], call_args: str,
                      known_methods: set[str]) -> str:
    """主线瘦后处理（步骤07 决策 A=方案B / B=B1）：数组下标 + this.X() 补实参 + wsaa. 前缀。"""
    body = fix_array_subscripts(body)
    # B1：指向本类 SECTION 方法的无参 this.X() → this.X(wsaa, <using…>)
    if call_args:
        def _route(m: "re.Match") -> str:
            return f"this.{m.group(1)}({call_args});" if m.group(1) in known_methods else m.group(0)
        body = re.sub(r"\bthis\.(\w+)\(\)\s*;", _route, body)
    # 方案B：WORKING-STORAGE 字段加 wsaa. 前缀（字符串字面量外）
    if ws_field_names:
        alt = "|".join(re.escape(n) for n in sorted(set(ws_field_names), key=len, reverse=True))
        field_re = re.compile(rf"(?<![.\w])({alt})\b")
        body = _prefix_fields_outside_strings(body, field_re, prefix="wsaa.")
    return body


def translate_section_body(body_lines: list[str], ctx: _rules.Ctx, ws_field_names: list[str],
                           call_args: str, known_methods: set[str]) -> str:
    """单个 SECTION 段体 → Java 方法体（确定性，无 LLM）。规则兜不住的叶子落 // TODO 叶子待译。"""
    reset_section(ctx)
    try:
        paras = [(lbl, segment(b)) for lbl, b in split_paragraphs(body_lines)]
        body = "\n".join(_rules.build_section(paras, ctx))
    except Exception as e:
        commented = "\n".join(f"// {ln}" for ln in body_lines)
        return f"// TODO 段翻译失败（{e}）；原 COBOL：\n{commented}"
    for lid, leaf in ctx.leaves:
        lines, matched = _rules.translate_leaf(leaf, ctx)
        raw = (leaf.raw or " ".join(leaf.tokens)).strip()
        fill = "\n".join(lines) if matched else f"// TODO 叶子待译: {raw}"
        body = body.replace(f"/*__LEAF_{lid}__*/", fill)
    body = re.sub(r"/\*__LEAF_\d+__\*/", "// TODO: 未翻译叶子", body)   # 防御
    return _postprocess_body(body, ws_field_names, call_args, known_methods)
