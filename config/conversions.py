"""
config.conversions —— 纯转换函数（步骤09 §4.2）。

用途：承接原先散在 parser 的两个纯转换函数，斩断 config→parser 的反向依赖。
      命名范式与 VALUE→初值都是"规范层概念"，理应位于 config；parser 反过来从此处取用。
对应设计：docs/详细设计/步骤09-config配置层重构设计.md §4.2。

本模块零业务依赖（仅用标准库 re），可被 config 与 parser 双向安全引用。

用法：
    from config.conversions import cobol_to_java_name, java_init
    cobol_to_java_name("WSAA-POLICY-NO")   # -> "wsaaPolicyNo"
    java_init("'ABC'", "String")           # -> '"ABC"'
"""
from __future__ import annotations

import re


# ── 命名：COBOL 名 → Java 小驼峰（原 parser/variable_resolver._cobol_to_java_name）──

def cobol_to_java_name(cobol_name: str) -> str:
    """WSAA-POLICY-NO → wsaaPolicyNo。"""
    parts = cobol_name.lower().replace("-", "_").split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


# ── VALUE → Java 初值（原 parser/ws/value.java_init，含 figurative / 十六进制 / 二进制）──

_FIG_ZERO = {"ZERO", "ZEROS", "ZEROES"}
_FIG_BLANK = {"SPACE", "SPACES", "LOW-VALUE", "LOW-VALUES", "HIGH-VALUE", "HIGH-VALUES"}


def _hex_to_java(hexbody: str) -> str:
    """X'0F' → "\\u000F"（按字节转 Java unicode 转义）。"""
    try:
        b = bytes.fromhex(hexbody)
        return '"' + "".join(f"\\u{x:04X}" for x in b) + '"'
    except ValueError:
        return '""'


def java_init(value_raw: str, java_type: str) -> str:
    """单值 VALUE → Java 初值表达式（按目标 java_type）。"""
    v = value_raw.strip()
    u = v.upper()
    if u in _FIG_ZERO:
        return "BigDecimal.ZERO" if java_type == "BigDecimal" else "0"
    if u in _FIG_BLANK:
        return '""'
    m = re.fullmatch(r"X'([0-9A-Fa-f]+)'", v)
    if m:
        return _hex_to_java(m.group(1))
    m = re.fullmatch(r"B'([01]+)'", v)
    if m:
        return "true" if "1" in m.group(1) else "false"
    if v.startswith("'") and v.endswith("'") and len(v) >= 2:
        return '"' + v[1:-1].replace("''", "'") + '"'
    if re.fullmatch(r"[+-]?\d+(\.\d+)?", v):
        if java_type == "BigDecimal":
            return f'new BigDecimal("{v}")'
        return v
    # 兜底：当作字符串字面量
    return '"' + v.strip("'") + '"'
