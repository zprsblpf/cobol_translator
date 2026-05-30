"""
COBOL 解析流水线（确定性，不依赖 LLM）。

从 graph.nodes 的 parse_cobol_node 下沉：解析源文件 + 变量解析 +
组装 SECTION 元数据与高风险点。graph 侧只留薄包装做 state 适配。
"""
from __future__ import annotations

from parser.cobol_parser import parse as parse_cobol
from parser.variable_resolver import (
    resolve, generate_field_declarations, generate_variable_context,
    generate_grouped_field_declarations, build_field_type_map,
)
from log_utils import get_flow_logger

log = get_flow_logger()


def build_parse_result(cobol_file: str) -> dict:
    """解析 COBOL 源 + 变量解析 + 组装 SECTION 元数据/高风险点。返回 state 增量。"""
    log.info("━━ ① 解析 ━━ 文件: %s", cobol_file)
    prog = parse_cobol(cobol_file)
    log.info("① PROGRAM-ID=%s 解析摘要: %s", prog.program_id, prog.summary())

    # 变量解析
    all_vars = prog.working_storage + prog.linkage_vars
    fields = resolve(all_vars)
    var_ctx = generate_variable_context(fields, max_chars=6000)
    field_decls = generate_field_declarations(fields)
    grouped_decls = generate_grouped_field_declarations(all_vars, visibility="public")
    field_type_map = build_field_type_map(fields)
    field_names = [f.java_name for f in fields]

    # SECTION 元数据
    sections_meta = [
        {
            "name": sec.name,
            "lines": sec.lines,
            "line_start": sec.line_start,
            "line_end": sec.line_end,
            "performs": sec.performs,
            "calls": sec.calls,
            "go_tos": sec.go_tos,
        }
        for sec in prog.sections
    ]

    # 高风险点
    review_items = []
    for sec in prog.sections:
        if sec.go_tos:
            review_items.append(
                f"⚠️ GO TO: SECTION [{sec.name}] 行{sec.line_start} 含 GO TO → {sec.go_tos}"
            )
    for var in prog.working_storage:
        if var.redefines:
            review_items.append(
                f"⚠️ REDEFINES: {var.name} REDEFINES {var.redefines}"
            )

    log.info("① 解析完成: %d 个 SECTION，%d 个字段，%d 个 COPY 引用，%d 个高风险点",
             len(sections_meta), len(fields), len(prog.copy_refs), len(review_items))
    return {
        "program_id": prog.program_id,
        "sections_meta": sections_meta,
        "variable_context": var_ctx,
        "java_field_declarations": field_decls,
        "java_field_declarations_grouped": grouped_decls,
        "field_type_map": field_type_map,
        "java_field_names": field_names,
        "linkage_using": prog.linkage_using,
        "copy_refs": prog.copy_refs,
        "review_items": review_items,
        "status": "building",
        "errors": [],
    }
