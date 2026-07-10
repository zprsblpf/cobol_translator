"""Java 语法校验：调用 javac 编译，扫描高风险残留。"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


def validate_with_javac(java_file: str) -> dict:
    """尝试用 javac 编译，返回结果字典。"""
    java_homes = [
        "/data/code/jdk17",
        "/data/code/jdk21",
        "/usr/lib/jvm/java-17-openjdk-amd64",
        "/usr/lib/jvm/java-21-openjdk-amd64",
    ]
    javac_bin = None
    for jh in java_homes:
        candidate = Path(jh) / "bin" / "javac"
        if candidate.exists():
            javac_bin = str(candidate)
            break

    if not javac_bin:
        return {"compiled": False, "error": "javac 未找到，跳过编译校验", "warnings": []}

    result = subprocess.run(
        [javac_bin, "-source", "17", "-target", "17", java_file],
        capture_output=True, text=True, timeout=30,
    )
    errors = [l.strip() for l in result.stderr.splitlines() if "error:" in l.lower()]
    warnings = [l.strip() for l in result.stderr.splitlines() if "warning:" in l.lower()]
    return {
        "compiled": result.returncode == 0,
        "error_count": len(errors),
        "errors": errors[:20],  # 最多显示20条
        "warnings": warnings[:10],
    }


def scan_risks(java_content: str) -> list[str]:
    """扫描翻译后 Java 代码中的高风险模式和翻译质量指标。

    返回:
        risk items list（每个元素为描述字符串）
    """
    risks = []
    lines = java_content.split("\n")

    # ── TODO 分类统计 ──
    todo_total = java_content.count("// TODO")
    if todo_total:
        risks.append(f"残留 {todo_total} 个 TODO（未完成翻译）")

    todo_leaf = java_content.count("TODO-LEAF")
    if todo_leaf:
        risks.append(f"  - TODO-LEAF: {todo_leaf}（叶子语句未翻译）")

    todo_call = java_content.count("TODO-CALL")
    if todo_call:
        risks.append(f"  - TODO-CALL: {todo_call}（CALL 语句未映射）")

    todo_perform = java_content.count("TODO-PERFORM")
    if todo_perform:
        risks.append(f"  - TODO-PERFORM: {todo_perform}（PERFORM 循环未翻译）")

    todo_if = java_content.count("TODO-IF")
    if todo_if:
        risks.append(f"  - TODO-IF: {todo_if}（IF 条件未翻译）")

    todo_evaluate = java_content.count("TODO-EVALUATE")
    if todo_evaluate:
        risks.append(f"  - TODO-EVALUATE: {todo_evaluate}（EVALUATE 未翻译）")

    todo_goto = java_content.count("TODO-GOTO")
    if todo_goto:
        risks.append(f"残留 {todo_goto} 个 TODO-GOTO（GO TO 语句需人工核实控制流）")

    todo_redefines = java_content.count("TODO-REDEFINES")
    if todo_redefines:
        risks.append(f"残留 {todo_redefines} 个 TODO-REDEFINES（REDEFINES 需人工确认）")

    todo_raw = java_content.count("TODO-RAW")
    if todo_raw:
        risks.append(f"  - TODO-RAW: {todo_raw}（原始行未解析）")

    # ── IO 结构统计 ──
    io_readr = len(re.findall(r"findBy\w*Readr\s*\(", java_content))
    io_begn = len(re.findall(r"findBy\w*Begn\s*\(", java_content))
    io_save = len(re.findall(r"(?<!\.)\bsave\s*\(", java_content))
    io_update_count = len(re.findall(r"(?<!\.)\bupdate\s*\(", java_content))
    io_delete_count = len(re.findall(r"(?<!\.)\bdelete\s*\(", java_content))

    if io_readr or io_begn or io_save or io_update_count or io_delete_count:
        io_parts = []
        if io_readr:
            io_parts.append(f"READR={io_readr}")
        if io_begn:
            io_parts.append(f"BEGN={io_begn}")
        if io_save:
            io_parts.append(f"WRITR={io_save}")
        if io_update_count:
            io_parts.append(f"UPDAT={io_update_count}")
        if io_delete_count:
            io_parts.append(f"DELET={io_delete_count}")
        risks.append(f"IO 调用统计: {', '.join(io_parts)}")

    # ── 未解析的 GO TO 目标 ──
    unresolved_gotos = re.findall(r"//\s*TODO-GOTO[:\s]*(.*)", java_content)
    if unresolved_gotos:
        unique_targets = sorted(set(g.strip() for g in unresolved_gotos if g.strip()))
        if unique_targets:
            risks.append(f"未解析 GO TO 目标: {', '.join(unique_targets[:10])}"
                         + (f" ...（共 {len(unique_targets)} 个）" if len(unique_targets) > 10 else ""))

    # ── LLM 调用统计 ──
    llm_calls = len(re.findall(r"processWithLlm|llm_fallback|LLM", java_content, re.IGNORECASE))
    if llm_calls:
        risks.append(f"LLM 兜底调用: {llm_calls} 处（需检查是否可确定性替代）")

    # ── 产物规模 ──
    risks.append(f"产物总行数: {len(lines)}")
    risks.append(f"TODO 密度: {todo_total / max(len(lines), 1) * 100:.1f}%")

    # ── COBOL 残留检查（未被翻译的关键词）──
    cobol_keywords = ["PERFORM ", "MOVE ", "CALL '", "IF ", "COMPUTE "]
    for kw in cobol_keywords:
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("*"):
                continue
            if kw in line and "// COBOL" not in line:
                risks.append(f"第{i}行可能含未翻译 COBOL 代码: {line.strip()[:60]}")
                break  # 每类只报第一个

    return risks
