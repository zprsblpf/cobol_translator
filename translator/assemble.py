"""
最终 Java 多文件组装 + 审查清单输出（确定性，不依赖 LLM）。

从 graph.nodes 的 assemble_node 下沉：把各模块骨架的 TODO 占位替换为翻译后的
方法体，写出 State/门面/模块 Java 文件、调用链与审查清单。
graph 侧只留薄包装做 state 适配。
"""
from __future__ import annotations

import os

from translator.skeleton import _class_base, _section_to_method
from log_utils import get_flow_logger

log = get_flow_logger()


def _fill_stubs(skeleton: str, sections: list[str], translated: dict,
                meta_by_name: dict) -> tuple[str, int]:
    """把模块骨架中各 SECTION 的 TODO 占位替换为翻译后的方法体。"""
    filled = skeleton
    count = 0
    for sec_name in sections:
        sec = meta_by_name[sec_name]
        method_name = _section_to_method(sec["name"])
        body = translated.get(method_name, "")
        if not body:
            continue
        old_body = (
            f"        // COBOL SECTION: {sec['name']}"
            f"  (行 {sec['line_start']}-{sec['line_end']})\n"
            f"        // TODO: 等待 LLM 翻译"
        )
        indented = "\n".join("        " + line for line in body.split("\n"))
        new_body = (
            f"        // COBOL SECTION: {sec['name']}"
            f"  (行 {sec['line_start']}-{sec['line_end']})\n"
            f"{indented}"
        )
        if old_body in filled:
            filled = filled.replace(old_body, new_body, 1)
            count += 1
    return filled, count


def assemble_outputs(state: dict) -> dict:
    """组装多文件 Java 输出 + 审查清单。返回 state 增量。"""
    log.info("━━ ④ 组装 ━━ 组装多文件 Java 输出...")

    translated = state.get("translated_sections", {})
    sections_meta = state["sections_meta"]
    meta_by_name = {s["name"].upper(): s for s in sections_meta}
    prog_id = state["program_id"]
    base = _class_base(prog_id)
    output_dir = state.get("output_dir", "./output")
    os.makedirs(output_dir, exist_ok=True)

    written: list[tuple[str, int]] = []   # (filename, line_count)
    size_warnings: list[str] = []

    def _write(filename: str, content: str):
        path = os.path.join(output_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        n = content.count("\n") + 1
        written.append((filename, n))
        if n >= 2000:
            size_warnings.append(f"⚠️ {filename} 达 {n} 行（≥2000），建议进一步拆分")

    # State + 门面
    _write(f"{base}State.java", state.get("state_class_source", ""))
    _write(f"{base}Service.java", state.get("facade_skeleton", ""))

    # 各模块
    total_replaced = 0
    module_summary: list[str] = []
    for mod in state.get("modules", []):
        skel = state.get("module_skeletons", {}).get(mod["class_name"], "")
        filled, cnt = _fill_stubs(skel, mod["sections"], translated, meta_by_name)
        total_replaced += cnt
        _write(f"{mod['class_name']}.java", filled)
        secs_desc = ", ".join(
            f"{s}(行{meta_by_name[s]['line_start']}-{meta_by_name[s]['line_end']})"
            for s in mod["sections"]
        )
        module_summary.append(
            f"- **{mod['class_name']}.java**（桶 {mod['prefix']}，{len(mod['sections'])} 段）: {secs_desc}"
        )

    log.info("④ 写出 %d 个文件；填充 %d/%d 个方法", len(written), total_replaced, len(sections_meta))

    # 调用链产物
    cg = state.get("call_graph", {})
    if cg.get("markdown"):
        with open(os.path.join(output_dir, "call_graph.md"), "w", encoding="utf-8") as f:
            f.write(cg["markdown"])

    # 审查清单
    review_items = list(state.get("review_items", [])) + size_warnings
    review_path = os.path.join(output_dir, "review_checklist.md")
    with open(review_path, "w", encoding="utf-8") as f:
        f.write(f"# {prog_id} 翻译审查清单\n\n")
        f.write("## 高风险点（需人工验证）\n\n")
        for item in review_items:
            f.write(f"- {item}\n")
        f.write("\n## 模块拆分汇总\n\n")
        f.write(f"- {base}State.java（共享全局状态）\n")
        f.write(f"- {base}Service.java（门面 + perform 分发，入口段 {cg.get('entry_section', '?')}）\n")
        for line in module_summary:
            f.write(line + "\n")
        f.write("\n## 文件行数\n\n")
        for fn, n in written:
            f.write(f"- {fn}: {n} 行\n")
        f.write("\n## 翻译统计\n")
        f.write(f"- 总 SECTION 数: {len(sections_meta)}\n")
        f.write(f"- 已填充方法: {total_replaced}/{len(sections_meta)}\n")
        f.write(f"- 调用链最大深度: {cg.get('max_depth', 0)}\n")
        f.write(f"- 调用环数: {len(cg.get('cycles', []))}\n")
        f.write(f"- 入口段: {cg.get('entry_section', '?')}\n")
        f.write(f"- 入口序列: {', '.join(cg.get('entry_sequence', []))[:100]}\n")

        # 风险清单（从 java_validator 获取）
        try:
            from validator.java_validator import scan_risks
            # 拼接所有模块的 Java 源码
            all_java = ""
            for mod in state.get("modules", []):
                mod_skel = state.get("module_skeletons", {}).get(mod["class_name"], "")
                filled, _cnt = _fill_stubs(mod_skel, mod["sections"], translated, meta_by_name)
                all_java += filled
            java_risks = scan_risks(all_java)
            if java_risks:
                f.write("\n## Java 产物风险扫描\n\n")
                for risk in java_risks:
                    f.write(f"- {risk}\n")
        except (ImportError, Exception):
            pass  # scan_risks 不可用时不阻塞

    if size_warnings:
        for w in size_warnings:
            log.warning("④ %s", w)
    log.info("④ 组装完成: 输出目录=%s；审查清单=%s", output_dir, review_path)
    return {"final_java": state.get("facade_skeleton", ""), "status": "done"}
