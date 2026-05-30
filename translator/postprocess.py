"""
Java 输出后处理（确定性，不依赖 LLM）。

对规则引擎与 LLM 输出统一生效：数组下标修正、PERFORM 跨模块路由、
字段名加 `st.` 前缀。从 graph.nodes 抽离，保证 graph → translator 单向依赖。
"""
from __future__ import annotations

import re

_JAVA_METHOD_PREFIXES = (
    "set", "get", "is", "has", "find", "save", "delete", "create", "update",
    "add", "put", "remove", "build", "make", "init", "load", "fetch",
    "read", "write", "call", "invoke", "execute", "run", "start", "stop",
    "new", "throw", "return", "if", "for", "while", "switch", "assert",
)


def _is_java_method_call(name: str) -> bool:
    """判断标识符是否是 Java 方法名（不应转为数组下标）。"""
    if name[0].isupper():
        return True
    return any(name.startswith(pfx) for pfx in _JAVA_METHOD_PREFIXES)


def _postprocess_java_body(java_body: str, current_module: str = "",
                           module_assignment: dict | None = None,
                           java_field_names: list | None = None,
                           method_to_section: dict | None = None) -> str:
    """
    统一后处理（对规则与 LLM 输出均生效），固定三遍顺序：
    (0) 清理 LLM 杂质（签名/setLength/多余尾括号）
    (1) 数组下标 name(idx) → name[idx-1]
    (2) PERFORM 路由：this.m() 若目标段不属当前模块 → facade.perform("SEC")
    (3) st. 前缀：已知字段名前加 st.
    """
    module_assignment = module_assignment or {}
    java_field_names = java_field_names or []
    method_to_section = method_to_section or {}

    # 去掉外层方法签名（如果 LLM 加了）
    java_body = re.sub(r"^(private|public|protected)\s+\w+\s+\w+\([^)]*\)\s*\{", "", java_body).strip()
    # 修正 .setLength(0) → = ""
    java_body = re.sub(r"(\w+)\.setLength\(0\);", r'\1 = "";', java_body)

    # (1) 数组下标
    def _fix_subscript(m: re.Match) -> str:
        full, name, idx = m.group(0), m.group(1), m.group(2)
        start = m.start()
        if start > 0 and java_body[start - 1] == ".":
            return full
        if _is_java_method_call(name):
            return full
        return f"{name}[{idx} - 1]"

    java_body = re.sub(r"(\w+)\((\w+)\)", _fix_subscript, java_body)

    # 修正多余尾部 }
    java_body = java_body.rstrip()
    if java_body.endswith("}") and java_body.count("{") < java_body.count("}"):
        java_body = java_body[:-1].rstrip()

    # (2) PERFORM 跨模块路由
    if module_assignment and method_to_section:
        def _route(m: re.Match) -> str:
            method = m.group(1)
            sec = method_to_section.get(method)
            if not sec:
                return m.group(0)
            target_module = module_assignment.get(sec)
            if target_module and target_module != current_module:
                return f'facade.perform("{sec}");'
            return m.group(0)
        java_body = re.sub(r"\bthis\.(\w+)\(\)\s*;", _route, java_body)

    # (3) st. 前缀
    if java_field_names:
        names_sorted = sorted(set(java_field_names), key=len, reverse=True)
        alt = "|".join(re.escape(n) for n in names_sorted)
        field_re = re.compile(rf"(?<![.\w])({alt})\b")
        java_body = _prefix_fields_outside_strings(java_body, field_re)

    return java_body


def _prefix_fields_outside_strings(text: str, field_re: re.Pattern) -> str:
    """对字符串字面量之外的字段名加 st. 前缀。"""
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in ("'", '"'):
            q = c
            j = i + 1
            while j < n and text[j] != q:
                if text[j] == "\\":
                    j += 1
                j += 1
            out.append(text[i:min(j + 1, n)])
            i = j + 1
            continue
        # 找到下一个引号或结尾，处理这一段
        j = i
        while j < n and text[j] not in ("'", '"'):
            j += 1
        segment = text[i:j]
        out.append(field_re.sub(lambda m: "st." + m.group(1), segment))
        i = j
    return "".join(out)
