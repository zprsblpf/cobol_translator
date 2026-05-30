"""
变量解析器：将 COBOL Variable 列表转换为 Java 字段声明，
并生成供 LLM 使用的变量上下文摘要（控制 token 数量）。
"""
from __future__ import annotations

import re
import yaml
from pathlib import Path
from dataclasses import dataclass
from parser.cobol_parser import Variable

CONFIG_DIR = Path(__file__).parent.parent / "config"


@dataclass
class JavaField:
    java_name: str       # camelCase Java 字段名
    java_type: str       # String / int / long / BigDecimal / etc.
    cobol_name: str      # 原始 COBOL 名
    is_array: bool
    array_size: int
    is_redefines: bool
    risk_note: str       # 高风险标注


def _load_type_rules() -> list[dict]:
    with open(CONFIG_DIR / "type_mappings.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg.get("pic_rules", [])


_TYPE_RULES: list[dict] = []


def _get_java_type(pic: str, comp: str) -> str:
    global _TYPE_RULES
    if not _TYPE_RULES:
        _TYPE_RULES = _load_type_rules()

    pic_upper = pic.upper()
    comp_upper = comp.upper()

    # 带 COMP-3 的整数
    if "COMP-3" in comp_upper or "COMP" in comp_upper:
        if re.search(r"V9", pic_upper):
            return "BigDecimal"
        return "long"

    # 有小数的数值
    if re.search(r"V9", pic_upper):
        return "BigDecimal"

    # 字符类型
    if pic_upper.startswith("X"):
        return "String"

    # 纯数字（估算位数）
    m = re.search(r"9\((\d+)\)", pic_upper)
    if m:
        digits = int(m.group(1))
        return "int" if digits <= 9 else "long"

    if pic_upper.startswith("9"):
        return "int"

    return "String"


def _cobol_to_java_name(cobol_name: str) -> str:
    """WSAA-POLICY-NO → wsaaPolicyNo"""
    parts = cobol_name.lower().replace("-", "_").split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _make_field(var: Variable) -> JavaField:
    """从单个 COBOL Variable 构造 JavaField。"""
    java_name = _cobol_to_java_name(var.name)
    java_type = _get_java_type(var.pic, var.comp) if var.pic else "String"
    risk_note = ""
    if var.redefines:
        risk_note = f"TODO-REDEFINES: 与 {_cobol_to_java_name(var.redefines)} 共享内存"
    return JavaField(
        java_name=java_name,
        java_type=java_type,
        cobol_name=var.name,
        is_array=var.occurs > 0,
        array_size=var.occurs,
        is_redefines=bool(var.redefines),
        risk_note=risk_note,
    )


def resolve(variables: list[Variable]) -> list[JavaField]:
    """将 COBOL 变量列表转换为 Java 字段列表（去重，以首次出现为准）。"""
    fields: list[JavaField] = []
    seen_names: set[str] = set()

    for var in variables:
        if var.is_group and var.occurs == 0:
            # GROUP 变量且无 OCCURS：只记录为注释，子字段会单独生成
            continue

        java_name = _cobol_to_java_name(var.name)
        # 同名字段只保留首次（REDEFINES 或重复定义产生的重名跳过）
        if java_name in seen_names:
            continue
        seen_names.add(java_name)
        fields.append(_make_field(var))

    return fields


def _render_field_line(f: JavaField, visibility: str = "private") -> list[str]:
    """渲染单个字段（含风险注释行）。返回行列表，4 空格缩进。"""
    lines: list[str] = []
    if f.risk_note:
        lines.append(f"    // {f.risk_note}")
    if f.is_array:
        if f.java_type == "BigDecimal":
            init = f"new BigDecimal[{f.array_size}]"
            jtype = "BigDecimal"
        elif f.java_type in ("int", "long"):
            init = f"new {f.java_type}[{f.array_size}]"
            jtype = f.java_type
        else:
            # Object/String 统一用 String[]
            init = f"new String[{f.array_size}]"
            jtype = "String"
        lines.append(
            f"    {visibility} {jtype}[] {f.java_name} = {init};"
            f" // COBOL: {f.cobol_name} OCCURS {f.array_size}"
        )
    else:
        if f.java_type == "BigDecimal":
            init = "BigDecimal.ZERO"
        elif f.java_type in ("int", "long"):
            init = "0"
        else:
            init = '""'
        lines.append(f"    {visibility} {f.java_type} {f.java_name} = {init}; // COBOL: {f.cobol_name}")
    return lines


def generate_field_declarations(fields: list[JavaField], visibility: str = "private") -> str:
    """生成 Java 字段声明代码块。"""
    lines = ["    // ── 从 COBOL WORKING-STORAGE 生成的字段 ──────────────────────"]
    for f in fields:
        lines.extend(_render_field_line(f, visibility))
    return "\n".join(lines)


def generate_grouped_field_declarations(variables: list[Variable], visibility: str = "public") -> str:
    """
    按 COBOL 01-level 组分块生成字段声明（供 XxxState 类）。
    遇 01 组输出注释头；去重规则与 resolve() 一致。
    """
    lines = ["    // ── COBOL WORKING-STORAGE / LINKAGE 全局状态（按 01 组分块）──"]
    seen_names: set[str] = set()
    for var in variables:
        if var.level == 1:
            lines.append(f"\n    // ── 01 {var.name} ──")
        if var.is_group and var.occurs == 0:
            # 纯 GROUP：仅作分组注释，子字段单独生成
            continue
        java_name = _cobol_to_java_name(var.name)
        if java_name in seen_names:
            continue
        seen_names.add(java_name)
        lines.extend(_render_field_line(_make_field(var), visibility))
    return "\n".join(lines)


def build_field_type_map(fields: list[JavaField]) -> dict:
    """{java_name: {type, is_array, array_size}}，供固化规则判型。"""
    return {
        f.java_name: {
            "type": f.java_type,
            "is_array": f.is_array,
            "array_size": f.array_size,
        }
        for f in fields
    }


def generate_variable_context(fields: list[JavaField], max_chars: int = 6000) -> str:
    """
    生成供 LLM 使用的变量上下文摘要（紧凑格式，控制 token 数量）。
    格式：COBOL名 → Java名 (类型)
    """
    lines = ["## 变量名映射表（COBOL → Java）"]
    lines.append("# 格式：COBOL变量名 → java字段名 [Java类型]")
    lines.append("# 数组字段在Java中从0开始（COBOL从1开始）\n")

    current_len = sum(len(l) for l in lines)
    for f in fields:
        if f.is_array:
            entry = f"{f.cobol_name} → {f.java_name}[] [{f.java_type}[{f.array_size}]]"
        else:
            entry = f"{f.cobol_name} → {f.java_name} [{f.java_type}]"
        if f.risk_note:
            entry += f"  ⚠️{f.risk_note}"

        if current_len + len(entry) > max_chars:
            lines.append("... (更多变量已省略)")
            break
        lines.append(entry)
        current_len += len(entry)

    return "\n".join(lines)
