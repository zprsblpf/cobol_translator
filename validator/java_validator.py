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
    """扫描翻译后 Java 代码中的高风险模式。"""
    risks = []
    lines = java_content.split("\n")

    todo_count = java_content.count("// TODO")
    if todo_count:
        risks.append(f"残留 {todo_count} 个 TODO（未完成翻译）")

    goto_count = java_content.count("// TODO-GOTO")
    if goto_count:
        risks.append(f"残留 {goto_count} 个 TODO-GOTO（GO TO 语句需人工核实控制流）")

    redefines_count = java_content.count("// TODO-REDEFINES")
    if redefines_count:
        risks.append(f"残留 {redefines_count} 个 TODO-REDEFINES（REDEFINES 需人工确认内存共享逻辑）")

    # 检查 COBOL 残留（未被翻译的关键词）
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
