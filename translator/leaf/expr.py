"""
相3 叶子翻译公用底座 —— 表达式底座（operand / lvalue / assign / struct / 判型 / refmod / bd）。

对应设计：docs/详细设计/步骤18-绞杀项3①MOVE迁visitor设计.md §3.1-3.2。
来源：原 translator/rules.py 同名 helper **原样迁址**（逻辑零改，仅把 ctx 注解由 rules.Ctx 改为 LeafCtx）。
这些纯函数被 MOVE（move.py）、条件翻译、其它动词共用，故下沉为公用底座（§17 公用优先），
依赖单向：rules → leaf.expr，leaf.expr 不反向依赖 rules。
"""
from __future__ import annotations

import re

from translator.leaf.context import LeafCtx

_FIGURATIVE_ZERO = {"ZERO", "ZEROS", "ZEROES"}
_FIGURATIVE_BLANK = {"SPACE", "SPACES", "LOW-VALUE", "LOW-VALUES", "HIGH-VALUES"}


def _field_base(name: str) -> str:
    """去掉下标后的 java 基名：WSAA-NAME(IX) → wsaaName。"""
    return _java(name).split("(")[0]


def _is_field(name: str, ctx: LeafCtx) -> bool:
    return _field_base(name) in ctx.field_type_map


def _java(cobol: str) -> str:
    """WSAA-POLICY-NO → wsaaPolicyNo（与 variable_resolver 一致，含下标原样保留）。"""
    base = cobol
    sub = ""
    m = re.match(r"^([A-Za-z0-9\-]+)(\(.*\))$", cobol)
    if m:
        base, sub = m.group(1), m.group(2)
    parts = base.lower().replace("-", "_").split("_")
    jn = parts[0] + "".join(p.capitalize() for p in parts[1:])
    return jn + sub


def _is_numeric_field(name: str, ctx: LeafCtx) -> bool:
    info = ctx.field_type_map.get(_java(name).split("(")[0])
    return bool(info) and info["type"] in ("int", "long", "BigDecimal")


def _is_bigdecimal(name: str, ctx: LeafCtx) -> bool:
    info = ctx.field_type_map.get(_java(name).split("(")[0])
    return bool(info) and info["type"] == "BigDecimal"


def _is_string_field(name: str, ctx: LeafCtx) -> bool:
    """已知的字符串字段（用于条件判断里防止把字符串误判成数值比较）。"""
    info = ctx.field_type_map.get(_java(name).split("(")[0])
    return bool(info) and info["type"] == "String"


def _refmod_lo(start: str) -> str:
    """COBOL 子串起点是 1-based → Java 0-based。常量则直接折算。"""
    if re.fullmatch(r"\d+", start):
        return str(int(start) - 1)
    return f"{start} - 1"


def _refmod_hi(lo: str, length: str) -> str:
    """substring 上界 = lo + len。两端皆常量则折算。"""
    if re.fullmatch(r"-?\d+", lo) and re.fullmatch(r"\d+", length):
        return str(int(lo) + int(length))
    return f"{lo} + {length}"


def _pascal(cobol: str) -> str:
    """REQUEST-COMPANY → RequestCompany（用于 getter/setter 后缀）。"""
    parts = cobol.lower().replace("-", "_").split("_")
    return "".join(p.capitalize() for p in parts)


def _struct_prefix(tok: str, ctx: LeafCtx):
    """若 tok 是 IO/linkage 参数结构体字段（PS01CHR-CHDRCOY），返回 (前缀大写, 余名大写)；否则 None。"""
    if "-" not in tok:
        return None
    pre, rest = tok.split("-", 1)
    if pre.upper() in ctx.io_struct_prefixes:
        return pre.upper(), rest.upper()
    return None


def _struct_obj(prefix: str, ctx: LeafCtx) -> str:
    """前缀 → 结构体 Java 对象名。优先用 config/copy_mappings 派生的映射，兜底按默认后缀。"""
    obj = ctx.struct_objects.get(prefix.upper())
    return obj if obj else _java(prefix) + ctx.struct_default_suffix


def _struct_cls(prefix: str, ctx: LeafCtx) -> str:
    """前缀 → 结构体 Java 类名。"""
    cls = ctx.struct_classes.get(prefix.upper())
    if cls:
        return cls
    o = _struct_obj(prefix, ctx)
    return o[0].upper() + o[1:]


def _qualified_operand(tok: str, ctx: LeafCtx) -> str | None:
    """COBOL A OF/IN B: resolve only through an explicit qualified map."""
    if not re.search(r"\s+(?:OF|IN)\s+", tok, re.IGNORECASE):
        return None
    from translator.naming import parse_qualified_field_reference, resolve_qualified_field_reference

    parsed = parse_qualified_field_reference(tok)
    if parsed is None:
        return None
    resolved = resolve_qualified_field_reference(tok, ctx)
    if resolved:
        return resolved
    return f'"/* TODO unresolved qualified field: {tok.strip()} */"'


def _operand(tok: str, ctx: LeafCtx) -> str:
    """把单个 COBOL 操作数转成 Java 表达式（裸字段名 / 字面量 / 下标访问 / 结构体读取）。"""
    u = tok.upper()
    if tok.startswith("'") or tok.startswith('"'):
        return '"' + tok[1:-1] + '"'
    q = _qualified_operand(tok, ctx)
    if q is not None:
        return q
    if u in _FIGURATIVE_ZERO:
        return "0"
    if re.fullmatch(r"[+-]?\d+(\.\d+)?", tok):
        return tok
    # 引用修改（取子串）：X(start:len) → base.substring(start-1, start-1+len)
    m = re.match(r"^([A-Za-z0-9\-]+)\(([^:]+):([^)]*)\)$", tok)
    if m:
        base, start_t, len_t = m.group(1), m.group(2).strip(), m.group(3).strip()
        base_expr = _operand(base, ctx)
        s0 = _refmod_lo(_operand(start_t, ctx))
        if len_t:
            return f"{base_expr}.substring({s0}, {_refmod_hi(s0, _operand(len_t, ctx))})"
        return f"{base_expr}.substring({s0})"
    # 下标访问：WSAA-NAME(IX) → wsaaName(ix)（后处理转 [ix-1]）
    m = re.match(r"^([A-Za-z0-9\-]+)\((.+)\)$", tok)
    if m and _is_field(m.group(1), ctx):
        return f"{_field_base(m.group(1))}({_operand(m.group(2), ctx)})"
    if _is_field(tok, ctx):
        return _field_base(tok)
    # IO/linkage 参数结构体字段：PS01CHR-CHDRCOY → ps01chrParams.getChdrcoy()
    # （拷贝簿不在盘上、字段未进 field_type_map，但绝不能当字符串字面量）
    sp = _struct_prefix(tok, ctx)
    if sp:
        pre, rest = sp
        if rest == "PARAMS":
            return _struct_obj(pre, ctx)                  # 结构体对象本身
        return f"{_struct_obj(pre, ctx)}.{ctx.struct_getter}{_pascal(rest)}()"  # 字段读取
    # 非字段裸词（如 O-K / BEGN / 88 条件值 / 命名常量）→ 字符串字面量
    if re.fullmatch(r"[A-Za-z0-9\-]+", tok):
        return '"' + tok + '"'
    return _java(tok)


def _lvalue(dst: str, ctx: LeafCtx) -> str:
    """赋值左值（MOVE/SET/COMPUTE 的目标）→ Java 左值表达式。

    照 wsaa_translation_spec.procedure_semantics.assignment_target：目标语义上必为字段，
    绝不退化为字符串字面量。下标/引用修改目标复用 _operand 解析；裸词（含未登记字段）→
    _field_base（camelCase 标识符），修 Bug 2：`"WSAA-A65086" = ""` → `wsaaA65086 = ""`。
    """
    if re.match(r"^[A-Za-z0-9\-]+\(", dst):     # X(IX) 下标 / X(s:l) 引用修改 → 同 RHS 解析
        return _operand(dst, ctx)
    return _field_base(dst)                      # 裸字段目标：必为字段，不退化字面量


def _assign(dst: str, val: str, ctx: LeafCtx) -> str:
    """生成赋值语句：结构体字段走 setter，结构体整体走 new，普通字段走 = 。"""
    sp = _struct_prefix(dst, ctx)
    if sp:
        pre, rest = sp
        if rest == "PARAMS":
            if val in ('""', "0", "BigDecimal.ZERO", "null"):
                return f"{_struct_obj(pre, ctx)} = new {_struct_cls(pre, ctx)}();"  # MOVE SPACES/INITIALIZE 重置
            return f"{_struct_obj(pre, ctx)} = {val};"                                # MOVE 结构体→结构体 拷贝
        return f"{_struct_obj(pre, ctx)}.{ctx.struct_setter}{_pascal(rest)}({val});"
    return f"{_lvalue(dst, ctx)} = {val};"                                            # 左值必为字段（Bug 2）


def _bd(expr: str) -> str:
    if expr == "0":
        return "BigDecimal.ZERO"
    if re.fullmatch(r"[+-]?\d+(\.\d+)?", expr):
        return f"new BigDecimal(\"{expr}\")"
    return expr
