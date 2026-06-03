"""
VALUE 子句解析（含 88 多值列表）。

对应设计：docs/详细设计/步骤03-WSAA块翻译设计.md。

设计思路：把 COBOL 字面量统一成「Java 初值表达式」或「去引号的取值串」。
- extract_value_raw(): 从合并定义行截出 VALUE 之后、句点之前的原文；
- literals(): 把 VALUE 原文拆成字面量列表（支持多引号串，用于 88 VALUES）；
- java_init(): 单值字面量 → Java 初值（按目标 java_type），供普通字段声明使用。
  ※ 步骤09：java_init（含 figurative / X'..' / B'..' 归一）已下沉到 config.conversions
    （规范层概念，斩断 config→parser 反向依赖），本处 re-export 以不破坏现有 import。
"""
from __future__ import annotations

import re

from config.conversions import java_init  # noqa: F401  （下沉至 config，re-export 保持兼容）

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
