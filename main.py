#!/usr/bin/env python3
"""
COBOL → Java 自动翻译器
用法:
  python main.py ZPOLDWNM.cob                    # 全量翻译
  python main.py ZPOLDWNM.cob --parse-only        # 只解析，不翻译
  python main.py ZPOLDWNM.cob --section 1000-INIT # 单 SECTION 测试
  python main.py ZPOLDWNM.cob --sections 5        # 只翻译前5个SECTION（测试用）
  python main.py ZPOLDWNM.cob --output /tmp/out   # 指定输出目录
"""
import argparse
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def cmd_parse_only(cob_file: str):
    """只解析，打印统计摘要。"""
    from parser.cobol_parser import parse
    print(f"解析: {cob_file}")
    prog = parse(cob_file)
    summary = prog.summary()
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    print(f"\n前10个 SECTION:")
    for s in prog.sections[:10]:
        risk = " ⚠️GO-TO" if s.go_tos else ""
        print(f"  [{s.name}] 行{s.line_start}-{s.line_end} "
              f"CALL={s.calls[:2]} GOTO={s.go_tos}{risk}")

    print(f"\n高风险 SECTION（含 GO TO）:")
    for s in [sec for sec in prog.sections if sec.go_tos]:
        print(f"  [{s.name}] 行{s.line_start} → GO TO {s.go_tos}")

    print(f"\nCOPY 引用列表: {prog.copy_refs[:10]}")
    return prog


def cmd_translate_section(cob_file: str, section_name: str, output_dir: str):
    """单 SECTION 测试翻译。"""
    from parser.cobol_parser import parse
    from parser.variable_resolver import (
        resolve, generate_variable_context, generate_field_declarations,
        build_field_type_map,
    )
    from graph.nodes import (
        build_context_and_skeleton_node,
        translate_section_node,
    )
    from translator.skeleton import _section_to_method

    prog = parse(cob_file)
    sec = prog.get_section(section_name)
    if not sec:
        print(f"错误: 找不到 SECTION [{section_name}]")
        print(f"可用: {[s.name for s in prog.sections[:20]]}")
        sys.exit(1)

    fields = resolve(prog.working_storage + prog.linkage_vars)
    var_ctx = generate_variable_context(fields)
    # 关键：单 SECTION 路径也必须填充字段类型表，否则 rules 引擎把所有字段名
    # 当成非字段裸词，整体加引号输出（"WSAA-REP" = "Y"）。
    field_type_map = build_field_type_map(fields)
    field_names = [f.java_name for f in fields]
    all_sections_meta = [
        {
            "name": s.name, "lines": s.lines,
            "line_start": s.line_start, "line_end": s.line_end,
            "performs": s.performs, "calls": s.calls, "go_tos": s.go_tos,
        }
        for s in prog.sections
    ]

    # 构建 IO 上下文
    import yaml
    config_dir = Path(__file__).parent / "config"
    with open(config_dir / "io_mappings.yaml") as f:
        io_cfg = yaml.safe_load(f)

    # 与全量路径一致：派生范式做基底 + io_programs 增量覆盖（resolve_io_info）
    from translator.rules import resolve_io_info
    all_io = {**io_cfg.get("io_programs", {}), **io_cfg.get("io_programs2", {})}
    io_pattern = io_cfg.get("io_default_pattern", {})
    io_lines = []
    for call in sec.calls:
        info = resolve_io_info(call, all_io, io_pattern)
        if info and info.get("java_class"):
            io_lines.append(f"CALL '{call}' → {info['java_class']}.method()")
    io_context = "\n".join(io_lines) or "（本 SECTION 无 IO 调用）"

    state = {
        "current_section": {
            "name": sec.name,
            "lines": sec.lines,
            "line_start": sec.line_start,
            "line_end": sec.line_end,
            "performs": sec.performs,
            "calls": sec.calls,
            "go_tos": sec.go_tos,
        },
        "variable_context": var_ctx,
        "io_context": io_context,
        "linkage_using": prog.linkage_using,
        "copy_refs": prog.copy_refs,
        "sections_meta": all_sections_meta,
        "field_type_map": field_type_map,
        "java_field_names": field_names,
        "module_assignment": {},
        "var_lifecycle": {},
        "translated_sections": {},
        "review_items": [],
    }

    print(f"\n翻译 SECTION: {section_name} ({len(sec.lines)} 行)")
    print(f"CALL: {sec.calls}")
    print(f"GO TO: {sec.go_tos}")
    print("-" * 50)
    print("原始 COBOL:")
    print("\n".join(sec.lines[:30]))
    print("-" * 50)

    result = translate_section_node(state)
    method_name = _section_to_method(section_name)
    java_body = result.get("translated_sections", {}).get(method_name, "翻译失败")

    print(f"\n翻译结果 (private void {method_name}()) {{")
    print(java_body)
    print("}")

    # 保存
    import os
    os.makedirs(output_dir, exist_ok=True)
    out_file = Path(output_dir) / f"{method_name}.java.fragment"
    out_file.write_text(java_body, encoding="utf-8")
    print(f"\n已保存到: {out_file}")


_EXTRA_STATE_DEFAULTS = {
    "java_field_declarations_grouped": "",
    "field_type_map": {},
    "java_field_names": [],
    "module_assignment": {},
    "modules": [],
    "module_skeletons": {},
    "state_class_source": "",
    "facade_skeleton": "",
    "call_graph": {},
    "entry_sequence": [],
    "var_lifecycle": {},
}


def cmd_full_translate(cob_file: str, output_dir: str, max_sections: int = 0,
                       skeleton_only: bool = False):
    """全量翻译或限制数量翻译。"""
    from graph.graph import get_graph

    print(f"\n{'='*60}")
    print(f"  COBOL → Java 翻译器")
    print(f"  输入: {cob_file}")
    print(f"  输出: {output_dir}")
    if max_sections:
        print(f"  模式: 测试（前 {max_sections} 个 SECTION）")
    print(f"{'='*60}\n")

    # 如果有限制，先解析拿 sections_meta，再截断
    if max_sections:
        from parser.cobol_parser import parse
        from parser.variable_resolver import resolve, generate_variable_context, generate_field_declarations
        prog = parse(cob_file)
        fields = resolve(prog.working_storage + prog.linkage_vars)

        initial_state = {
            "cobol_file": cob_file,
            "output_dir": output_dir,
            "program_id": prog.program_id,
            "sections_meta": [
                {
                    "name": s.name, "lines": s.lines,
                    "line_start": s.line_start, "line_end": s.line_end,
                    "performs": s.performs, "calls": s.calls, "go_tos": s.go_tos,
                }
                for s in prog.sections[:max_sections]
            ],
            "variable_context": generate_variable_context(fields),
            "java_field_declarations": generate_field_declarations(fields),
            "linkage_using": prog.linkage_using,
            "copy_refs": prog.copy_refs,
            "translated_sections": {},
            "review_items": [],
            "errors": [],
            "status": "building",
            "io_context": "",
            "java_skeleton": "",
            "final_java": "",
            "validation_errors": [],
            "skeleton_only": skeleton_only,
            **_EXTRA_STATE_DEFAULTS,
        }
        # 直连路径需自行补齐解析期产物（分组字段 / 类型映射 / 字段名）
        from parser.variable_resolver import (
            generate_grouped_field_declarations, build_field_type_map,
        )
        _all_vars = prog.working_storage + prog.linkage_vars
        initial_state["java_field_declarations_grouped"] = \
            generate_grouped_field_declarations(_all_vars, visibility="public")
        initial_state["field_type_map"] = build_field_type_map(fields)
        initial_state["java_field_names"] = [f.java_name for f in fields]
        # 跳过 parse 节点，直接从 build_context 开始
        from graph.nodes import build_context_and_skeleton_node
        ctx_result = build_context_and_skeleton_node(initial_state)
        initial_state.update(ctx_result)

        # 翻译各 SECTION
        from graph.nodes import translate_section_node
        for sec_meta in initial_state["sections_meta"]:
            child = dict(initial_state)
            child["current_section"] = sec_meta
            result = translate_section_node(child)
            initial_state["translated_sections"].update(result.get("translated_sections", {}))

        # 组装
        from graph.nodes import assemble_node
        assemble_node(initial_state)
    else:
        # 全量走 LangGraph 图
        graph = get_graph()
        initial_state = {
            "cobol_file": cob_file,
            "output_dir": output_dir,
            "program_id": "",
            "sections_meta": [],
            "variable_context": "",
            "io_context": "",
            "java_field_declarations": "",
            "linkage_using": [],
            "java_skeleton": "",
            "translated_sections": {},
            "final_java": "",
            "review_items": [],
            "validation_errors": [],
            "errors": [],
            "status": "parsing",
            "skeleton_only": skeleton_only,
            **_EXTRA_STATE_DEFAULTS,
        }
        final = graph.invoke(initial_state)
        if final.get("status") == "error":
            print("翻译失败:", final.get("errors"))
            sys.exit(1)

    print(f"\n翻译完成！输出目录: {output_dir}")


def main():
    parser = argparse.ArgumentParser(description="COBOL → Java 翻译器")
    parser.add_argument("cob_file", help=".cob 文件路径")
    parser.add_argument("--parse-only", action="store_true", help="只解析，不翻译")
    parser.add_argument("--section", help="只翻译指定 SECTION（测试）")
    parser.add_argument("--sections", type=int, default=0, help="只翻译前N个SECTION（测试）")
    parser.add_argument("--skeleton-only", action="store_true",
                        help="仅生成控制流/调用骨架（叶子保留原 COBOL 占位，不调 LLM）")
    parser.add_argument("--output", default="./output", help="输出目录")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="处理流程日志输出到 DEBUG 级别")
    args = parser.parse_args()

    # 初始化日志：处理流程(flow) 与 LLM 沟通(llm) 两个独立通道
    import logging
    from log_utils import setup_logging
    setup_logging(level=logging.DEBUG if args.verbose else logging.INFO)

    cob_file = args.cob_file
    if not Path(cob_file).exists():
        print(f"错误: 文件不存在: {cob_file}")
        sys.exit(1)

    if args.parse_only:
        cmd_parse_only(cob_file)
    elif args.section:
        cmd_translate_section(cob_file, args.section.upper(), args.output)
    else:
        cmd_full_translate(cob_file, args.output, max_sections=args.sections,
                           skeleton_only=args.skeleton_only)


if __name__ == "__main__":
    main()
