"""
翻译上下文 + Java 骨架构建（确定性，不依赖 LLM）。

从 graph.nodes 的 build_context_and_skeleton_node 下沉：合并 IO 映射、跨段分析
（调用图 / 数据流）、分模块、生成 State/模块/门面骨架与结构体注册表。
graph 侧只留薄包装做 state 适配。
"""
from __future__ import annotations

from config import spec_loader            # IO 映射访问层（步骤09：不再直读 io_mappings.yaml）
from translator import rules as _rules
from translator.skeleton import (
    _class_base, _assign_sections_to_modules, _calls_to_repos,
    _build_state_class, _build_module_skeleton, _build_facade_skeleton,
)
from translator.naming import build_struct_registry
from analyzer.callgraph import build_call_graph
from analyzer.dataflow import analyze_dataflow
from log_utils import get_flow_logger

log = get_flow_logger()


def build_context_and_skeleton(state: dict) -> dict:
    """构建 IO/COPY 上下文并生成 Java 骨架。返回 state 增量。"""
    log.info("━━ ② 上下文+骨架 ━━ 构建 IO/COPY 上下文并生成 Java 骨架...")

    # IO 映射经访问层取（步骤09：不再直读 io_mappings.yaml；io_programs2 兼容已收口在 spec_loader）
    all_io = spec_loader.io_programs()
    io_pattern = spec_loader.io_default_pattern()
    date_progs = spec_loader.date_programs()
    sys_progs = spec_loader.system_programs()

    # 收集本程序实际用到的所有 IO 调用
    all_calls: set[str] = set()
    for sec in state["sections_meta"]:
        all_calls.update(sec.get("calls", []))

    # 构建 IO 上下文摘要
    io_lines = ["## IO 调用映射（COBOL CALL → Java Repository）"]
    repositories: dict[str, dict] = {}
    date_services: list[str] = []

    for call_name in sorted(all_calls):
        # 派生范式做基底，io_programs 显式条目按增量覆盖（非 *IO 返回显式条目/None）
        info = _rules.resolve_io_info(call_name, all_io, io_pattern)
        if info:
            io_lines.append(
                f"CALL '{call_name}' → {info['java_class']}.method()"
                f"  (字段: {info['field_name']})"
            )
            repositories[info["field_name"]] = info
        elif call_name in date_progs:
            info = date_progs[call_name]
            if "method" in info:
                io_lines.append(f"CALL '{call_name}' → dateConversionService.{info['method']}")
                if "DateConversionService" not in date_services:
                    date_services.append("DateConversionService")
            else:
                # date_programs 中意外混入的 IO 程序
                io_lines.append(f"CALL '{call_name}' → {info['java_class']}.method()")
                repositories[info["field_name"]] = info
        elif call_name in sys_progs:
            info = sys_progs[call_name]
            io_lines.append(f"CALL '{call_name}' → {info.get('java_code', 'TODO')}")

    io_context = "\n".join(io_lines)

    prog_id = state["program_id"]
    base = _class_base(prog_id)
    sections_meta = state["sections_meta"]

    log.info("② IO 调用: 收集到 %d 个唯一 CALL，映射 %d 个 Repository",
             len(all_calls), len(repositories))

    # ── 跨段分析（确定性）──────────────────────────────────────────────
    cg = build_call_graph(sections_meta)
    df = analyze_dataflow(sections_meta, state.get("field_type_map", {}))
    log.info("② 跨段分析: 入口段=%s，调用链最大深度=%d，调用环 %d 个",
             cg.get("entry_section", "?"), cg.get("max_depth", 0), len(cg.get("cycles", [])))

    # ── 大框架：分模块 ────────────────────────────────────────────────
    module_assignment, modules = _assign_sections_to_modules(sections_meta, base)
    meta_by_name = {s["name"].upper(): s for s in sections_meta}

    # _calls_to_repos 仅需 io_default_pattern + date_programs，组小字典传入
    io_cfg = {"io_default_pattern": io_pattern, "date_programs": date_progs}

    # 每模块所需 Repository
    for mod in modules:
        repos, uses_date = _calls_to_repos(
            (c for s in mod["sections"] for c in meta_by_name[s].get("calls", [])),
            all_io, io_cfg,
        )
        mod["repos"] = repos
        mod["uses_date"] = uses_date

    # ── 生成 State / 模块 / 门面 ──────────────────────────────────────
    state_src = _build_state_class(base, prog_id, state["cobol_file"],
                                   state.get("java_field_declarations_grouped", ""))
    module_skeletons = {
        mod["class_name"]: _build_module_skeleton(mod, base, prog_id, meta_by_name)
        for mod in modules
    }
    facade_src = _build_facade_skeleton(
        base, prog_id, state["cobol_file"], modules,
        state.get("linkage_using", []), module_assignment,
        cg.get("entry_section", ""),
    )

    struct_reg = build_struct_registry(state)

    review_items = list(df.get("review_items", []))
    for c in cg.get("cycles", []):
        review_items.append(f"⚠️ 调用环: {c}（需人工确认控制流）")

    log.info("② 骨架生成完成: %d 个模块类 + State + 门面；结构体注册表 %d 个前缀",
             len(modules), len(struct_reg.get("prefixes", [])))
    return {
        "io_context": io_context,
        "module_assignment": module_assignment,
        "modules": modules,
        "module_skeletons": module_skeletons,
        "state_class_source": state_src,
        "facade_skeleton": facade_src,
        "call_graph": cg,
        "entry_sequence": cg.get("entry_sequence", []),
        "var_lifecycle": df.get("var_lifecycle", {}),
        "review_items": review_items,
        # 结构体命名注册表：程序级算一次，各 SECTION 复用
        "struct_registry": struct_reg,
        # IO 子程序映射：程序级算一次，供各 SECTION 的 _t_call 固化复用
        "io_mappings": {
            "io_programs": all_io,
            "date_programs": date_progs,
            "system_programs": sys_progs,
            "io_default_pattern": io_pattern,
        },
        "status": "translating",
    }
