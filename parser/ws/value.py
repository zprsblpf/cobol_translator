"""
VALUE 子句解析（含 88 多值列表）。

对应设计：docs/详细设计/步骤03-WSAA块翻译设计.md。

设计思路：把 COBOL 字面量统一成「Java 初值表达式」或「去引号的取值串」。
- extract_value_raw(): 从合并定义行截出 VALUE 之后、句点之前的原文；
- literals(): 把 VALUE 原文拆成字面量列表（支持多引号串，用于 88 VALUES）；
- java_init(): 单值字面量 → Java 初值（按目标 java_type），供普通字段声明使用。
  figurative（SPACES/ZEROES）、十六进制 X'..'、B'..' 均在此归一。
"""
from __future__ import annotations

import re

# VALUE 必须是独立子句（前为空白），避免误匹配名字里的 VALUE（如 CASH-VALUE-NOTPRINT）
_VALUE_RE = re.compile(r"(?<=\s)VALUES?\b\s*(.*)$", re.IGNORECASE)
_LITERAL_RE = re.compile(r"'((?:[^']|'')*)'|(\S+)")   # 引号串 或 裸 token


def extract_value_raw(entry: str) -> tuple[bool, str]:
    """返回 (是否含 VALUE, VALUE 之后原文去尾点)。"""
    m = _VALUE_RE.search(entry)
    if not m:
        return False, ""
    return True, m.group(1).strip().rstrip(".").strip()


def literals(value_raw: str) -> list[str]:
    """拆成字面量列表：'6PWB' 'WPDH' → ['6PWB','WPDH']；裸词原样。"""
    out: list[str] = []
    for m in _LITERAL_RE.finditer(value_raw):
        if m.group(1) is not None:          # 引号串（可为空串）
            out.append(m.group(1).replace("''", "'"))
        elif m.group(2):                    # 裸 token
            out.append(m.group(2))
    return out


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
    """单值 VALUE → Java 初值表达式。"""
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
