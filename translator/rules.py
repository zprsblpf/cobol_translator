"""
固化规则引擎。

两层职责：
- 骨架层 build_skeleton(): 递归生成控制流/调用结构（IF/EVALUATE/PERFORM/GO/CONTINUE…），
  叶子语句位置插入占位 `/*__LEAF_n__*/` 并登记到 leaves，确定性、不调 LLM。
- 叶子层 translate_leaf(): 对单条叶子语句（MOVE/算术/SET…）尝试固化；命中返回 Java，
  未命中 matched=False，交 LLM 兜底。

字段名一律输出"裸名"，由 nodes._postprocess_java_body 统一加 `st.` 前缀并做跨模块路由。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field

from translator.segmenter import Stmt


@dataclass
class Ctx:
    field_type_map: dict
    section_to_method: object          # callable: SEC名 -> java 方法名
    known_sections: set                # 所有 SECTION 名（大写）
    leaves: list = dc_field(default_factory=list)   # [(id, Stmt)]
    _counter: list = dc_field(default_factory=lambda: [0])
    flow_label: str | None = None      # 状态机循环标签（dispatch 模式下为 "FLOW"，否则 None）
    flow_paragraphs: set = dc_field(default_factory=set)  # 本 SECTION 内 paragraph 标签（大写）
    # ── 结构体（拷贝簿）命名范式：由 config/naming_conventions.yaml 驱动，不写死 ──
    io_struct_prefixes: set = dc_field(default_factory=set)  # 结构体前缀（大写，如 LETCLST/PS01CHR/LETCMNT）
    struct_objects: dict = dc_field(default_factory=dict)    # 前缀 → Java 对象名（如 PS01CHR → ps01chrParams）
    struct_classes: dict = dc_field(default_factory=dict)    # 前缀 → Java 类名（如 PS01CHR → Ps01chrParams）
    struct_getter: str = "get"          # 字段读取访问器前缀
    struct_setter: str = "set"          # 字段写入访问器前缀
    struct_default_suffix: str = "Params"  # 无显式类名映射时的兜底后缀
    # ── IO 子程序映射（CALL 'xxxIO' 固化，由 config/io_mappings.yaml 驱动）──
    io_programs: dict = dc_field(default_factory=dict)      # 合并 io_programs+io_programs2，名→info
    date_programs: dict = dc_field(default_factory=dict)    # 日期子程序，名→info
    system_programs: dict = dc_field(default_factory=dict)  # 系统子程序（SYSERR 等），名→info
    io_default_pattern: dict = dc_field(default_factory=dict)  # *IO 查表派生范式（io_mappings.yaml）
    struct_function: dict = dc_field(default_factory=dict)  # 运行时跟踪：前缀→最近功能码（如 ELPO→READR）

    def new_leaf(self, stmt: Stmt) -> str:
        i = self._counter[0]
        self._counter[0] += 1
        self.leaves.append((i, stmt))
        return f"/*__LEAF_{i}__*/"


# 控制流类简单语句（骨架层处理），其余 simple 视为叶子
_CONTROL_FIRST = {"GO", "CONTINUE", "NEXT", "EXIT", "GOBACK", "STOP"}

_FIGURATIVE_ZERO = {"ZERO", "ZEROS", "ZEROES"}
_FIGURATIVE_BLANK = {"SPACE", "SPACES", "LOW-VALUE", "LOW-VALUES", "HIGH-VALUES"}
_REL_OPS = {"=": "==", ">": ">", "<": "<", ">=": ">=", "<=": "<=", "NOT": "NOT"}


def _ind(n: int) -> str:
    return "    " * n


def _field_base(name: str) -> str:
    """去掉下标后的 java 基名：WSAA-NAME(IX) → wsaaName。"""
    return _java(name).split("(")[0]


def _is_field(name: str, ctx: Ctx) -> bool:
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


def _is_numeric_field(name: str, ctx: Ctx) -> bool:
    info = ctx.field_type_map.get(_java(name).split("(")[0])
    return bool(info) and info["type"] in ("int", "long", "BigDecimal")


def _is_bigdecimal(name: str, ctx: Ctx) -> bool:
    info = ctx.field_type_map.get(_java(name).split("(")[0])
    return bool(info) and info["type"] == "BigDecimal"


def _is_string_field(name: str, ctx: Ctx) -> bool:
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


def _struct_prefix(tok: str, ctx: Ctx):
    """若 tok 是 IO/linkage 参数结构体字段（PS01CHR-CHDRCOY），返回 (前缀大写, 余名大写)；否则 None。"""
    if "-" not in tok:
        return None
    pre, rest = tok.split("-", 1)
    if pre.upper() in ctx.io_struct_prefixes:
        return pre.upper(), rest.upper()
    return None


def _struct_obj(prefix: str, ctx: Ctx) -> str:
    """前缀 → 结构体 Java 对象名。优先用 config/copy_mappings 派生的映射，兜底按默认后缀。"""
    obj = ctx.struct_objects.get(prefix.upper())
    return obj if obj else _java(prefix) + ctx.struct_default_suffix


def _struct_cls(prefix: str, ctx: Ctx) -> str:
    """前缀 → 结构体 Java 类名。"""
    cls = ctx.struct_classes.get(prefix.upper())
    if cls:
        return cls
    o = _struct_obj(prefix, ctx)
    return o[0].upper() + o[1:]


def _operand(tok: str, ctx: Ctx) -> str:
    """把单个 COBOL 操作数转成 Java 表达式（裸字段名 / 字面量 / 下标访问 / 结构体读取）。"""
    u = tok.upper()
    if tok.startswith("'") or tok.startswith('"'):
        return '"' + tok[1:-1] + '"'
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


def _assign(dst: str, val: str, ctx: Ctx) -> str:
    """生成赋值语句：结构体字段走 setter，结构体整体走 new，普通字段走 = 。"""
    sp = _struct_prefix(dst, ctx)
    if sp:
        pre, rest = sp
        if rest == "PARAMS":
            if val in ('""', "0", "BigDecimal.ZERO", "null"):
                return f"{_struct_obj(pre, ctx)} = new {_struct_cls(pre, ctx)}();"  # MOVE SPACES/INITIALIZE 重置
            return f"{_struct_obj(pre, ctx)} = {val};"                                # MOVE 结构体→结构体 拷贝
        return f"{_struct_obj(pre, ctx)}.{ctx.struct_setter}{_pascal(rest)}({val});"
    return f"{_operand(dst, ctx)} = {val};"


# ── 条件翻译 ──────────────────────────────────────────────────────────────────

def _try_condition(tokens: list[str], ctx: Ctx) -> str | None:
    """翻译 IF / UNTIL / WHEN 条件为 Java 布尔表达式；失败返回 None。"""
    if not tokens:
        return None
    # 按 AND/OR 切分（保留连接符）
    parts: list[str] = []
    cur: list[str] = []
    for t in tokens:
        if t.upper() in ("AND", "OR"):
            parts.append(cur)
            parts.append([t.upper()])
            cur = []
        else:
            cur.append(t)
    parts.append(cur)

    out: list[str] = []
    for seg in parts:
        if len(seg) == 1 and seg[0] in ("AND", "OR"):
            out.append("&&" if seg[0] == "AND" else "||")
            continue
        expr = _try_comparison(seg, ctx)
        if expr is None:
            return None
        out.append(expr)
    return " ".join(out)


def _try_comparison(seg: list[str], ctx: Ctx) -> str | None:
    if not seg:
        return None
    # 定位关系运算符
    negate = False
    op_idx = -1
    op = ""
    for i, t in enumerate(seg):
        u = t.upper()
        if u == "NOT":
            negate = True
            continue
        if u in ("=", "EQUAL"):
            op, op_idx = "=", i
            break
        if u in (">", "GREATER"):
            op, op_idx = ">", i
            break
        if u in ("<", "LESS"):
            op, op_idx = "<", i
            break
        if u in (">=",):
            op, op_idx = ">=", i
            break
        if u in ("<=",):
            op, op_idx = "<=", i
            break
    if op_idx < 0:
        return None  # 88 条件名 / 复杂条件 → 交 LLM
    left = [t for t in seg[:op_idx] if t.upper() != "NOT"]
    right = seg[op_idx + 1:]
    if len(left) != 1 or len(right) < 1:
        return None
    lname = left[0]
    ljava = _operand(lname, ctx)
    rtok = right[0]
    ru = rtok.upper()

    # = SPACES / NOT = SPACES
    if ru in _FIGURATIVE_BLANK:
        base = f"StringUtils.isBlank({ljava})"
        if op != "=":
            return None
        return f"!{base}" if negate else base

    rjava = _operand(rtok, ctx)
    # 数值比较判定：左/右任一为已知数值字段，或右为数字字面量/figurative ZERO。
    # 右操作数为数值字段时，左侧若是「已知字符串字段」则不强转数值（防 String 与 long 误比）；
    # 左侧类型未知（如 IO 结构体 getter）则随右侧按数值处理（修 field>field 漏判 → 整块掉 LLM）。
    numeric = (
        _is_numeric_field(lname, ctx)
        or ru in _FIGURATIVE_ZERO
        or re.fullmatch(r"[+-]?\d+(\.\d+)?", rtok)
        or (_is_numeric_field(rtok, ctx) and not _is_string_field(lname, ctx))
    )
    if numeric:
        if _is_bigdecimal(lname, ctx) or _is_bigdecimal(rtok, ctx):
            j = f"{ljava}.compareTo({_bd(rjava)})"
            cmp = {"=": "== 0", ">": "> 0", "<": "< 0", ">=": ">= 0", "<=": "<= 0"}[op]
            base = f"{j} {cmp}"
            if negate:
                base = _negate_numeric(j, op)
            return f"({base})"
        jop = {"=": "==", ">": ">", "<": "<", ">=": ">=", "<=": "<="}[op]
        if negate:
            jop = {"==": "!=", ">": "<=", "<": ">=", ">=": "<", "<=": ">"}[jop]
        return f"{ljava} {jop} {rjava}"
    # 字符串比较
    if op != "=":
        return None
    base = f"{rjava}.equals({ljava})"
    return f"!{base}" if negate else base


def _bd(expr: str) -> str:
    if expr == "0":
        return "BigDecimal.ZERO"
    if re.fullmatch(r"[+-]?\d+(\.\d+)?", expr):
        return f"new BigDecimal(\"{expr}\")"
    return expr


def _negate_numeric(cmp_expr: str, op: str) -> str:
    inv = {"=": "!= 0", ">": "<= 0", "<": ">= 0", ">=": "< 0", "<=": "> 0"}[op]
    return f"{cmp_expr} {inv}"


# ── 段内控制流（paragraph + GO TO）─────────────────────────────────────────────

def _collect_gotos(stmts: list[Stmt]) -> list[str]:
    """递归收集所有 GO TO 目标（大写），含嵌套 IF/EVALUATE/PERFORM 体内的。"""
    out: list[str] = []
    for st in stmts:
        if st.kind == "simple" and st.tokens and st.tokens[0].upper() == "GO":
            for t in st.tokens:
                if t.upper() not in ("GO", "TO"):
                    out.append(t.upper())
                    break
        out.extend(_collect_gotos(st.children))
        out.extend(_collect_gotos(st.else_children))
        for _cond, body in st.whens:
            out.extend(_collect_gotos(body))
    return out


def _ends_with_transfer(stmts: list[Stmt]) -> bool:
    """末尾顶层语句是否为无条件跳转（GO/EXIT/GOBACK/STOP）—— 决定是否需要补 fall-through。"""
    if not stmts:
        return False
    last = stmts[-1]
    return (last.kind == "simple" and last.tokens
            and last.tokens[0].upper() in {"GO", "EXIT", "GOBACK", "STOP"})


# ── BEGN+NEXTR 段循环 → List + for-each 改写（确定性，先于状态机降级）──────────────

def _stmt_call_io(st: Stmt, ctx: Ctx):
    """CALL 'xxxIO' USING <PFX>-PARAMS → (子程序名, 前缀)，否则 None。"""
    if st.kind != "simple" or not st.tokens or st.tokens[0].upper() != "CALL":
        return None
    if len(st.tokens) < 2:
        return None
    name = st.tokens[1].strip("'\"").upper()
    u = [t.upper() for t in st.tokens]
    if "USING" not in u:
        return None
    arg = st.tokens[u.index("USING") + 1] if u.index("USING") + 1 < len(st.tokens) else ""
    if not name.endswith("IO") or "-" not in arg:
        return None
    return name, arg.split("-", 1)[0].upper()


def _goto_target(st: Stmt):
    if st.kind == "simple" and st.tokens and st.tokens[0].upper() == "GO":
        for t in st.tokens[1:]:
            if t.upper() != "TO":
                return t.upper()
    return None


def _is_move_nextr(st: Stmt, pfx: str) -> bool:
    if st.kind != "simple":
        return False
    tu = [t.upper() for t in st.tokens]
    return tu[:1] == ["MOVE"] and "NEXTR" in tu and f"{pfx}-FUNCTION" in tu


def _setup_has_begn(stmts: list[Stmt], pfx: str) -> bool:
    for st in stmts:
        if st.kind == "simple":
            tu = [t.upper() for t in st.tokens]
            if tu[:1] == ["MOVE"] and "BEGN" in tu and f"{pfx}-FUNCTION" in tu:
                return True
    return False


def _then_single_goto(st: Stmt):
    """IF 的 then 分支恰为单条 GO TO X（无 else）→ 返回 X。"""
    if st.kind == "if" and not st.else_children and len(st.children) == 1:
        return _goto_target(st.children[0])
    return None


def _is_filter_if(st: Stmt, pfx: str, loop_label: str) -> bool:
    """IF cond → [MOVE NEXTR TO pfx-FUNCTION, GO TO loop_label]（结果集过滤 → continue）。"""
    if st.kind != "if" or st.else_children or len(st.children) != 2:
        return False
    return _is_move_nextr(st.children[0], pfx) and _goto_target(st.children[1]) == loop_label


def _contains_goto(st: Stmt) -> bool:
    if _goto_target(st):
        return True
    for c in st.children + st.else_children:
        if _contains_goto(c):
            return True
    for _cond, body in (st.whens or []):
        if any(_contains_goto(x) for x in body):
            return True
    return False


def _split_or(tokens: list[str]) -> list[list[str]]:
    """按顶层 OR 切分条件 token（本场景条件无括号）。"""
    out, cur = [], []
    for t in tokens:
        if t.upper() == "OR":
            out.append(cur); cur = []
        else:
            cur.append(t)
    out.append(cur)
    return out


def _begn_breakout_keys(cond_tokens: list[str], pfx: str):
    """跳出条件 → 等值键列表 [(键COBOL名, 值COBOL名)]。
    每个 OR 子项须为 <pfx>-STATUZ NOT = O-K（跳过）或 <pfx>-KEY NOT = VAL（取键）；
    含 AND / 非 pfx 字段 / 形状不符 → None（放弃改写）。
    """
    keys = []
    for term in _split_or(cond_tokens):
        tu = [t.upper() for t in term]
        if "AND" in tu or "NOT" not in tu or "=" not in tu:
            return None
        ni = tu.index("NOT")
        left = term[:ni]
        eqi = tu.index("=", ni)
        right = term[eqi + 1:]
        if len(left) != 1 or len(right) != 1:
            return None
        lf = left[0].upper()
        if "-" not in lf or lf.split("-", 1)[0] != pfx:
            return None
        key = lf.split("-", 1)[1]
        if key == "STATUZ":
            continue
        keys.append((key, right[0]))
    return keys or None


def _match_begn_loop(loop_label: str, stmts: list[Stmt], ctx: Ctx):
    """识别 BEGN+NEXTR 自跳循环段，返回 {pfx,name,keys,exit_label,filters,body} 或 None。"""
    if not stmts:
        return None
    ci = _stmt_call_io(stmts[0], ctx)
    if not ci:
        return None
    name, pfx = ci
    keys = exit_label = None
    filters: list[Stmt] = []
    body: list[Stmt] = []
    for st in stmts[1:]:
        tgt = _then_single_goto(st)
        if tgt and keys is None and tgt != loop_label:
            kk = _begn_breakout_keys(st.tokens, pfx)
            if kk is None:
                return None
            keys, exit_label = kk, tgt
            continue
        if _is_filter_if(st, pfx, loop_label):
            filters.append(st)
            continue
        if _is_move_nextr(st, pfx) or _goto_target(st) == loop_label:
            continue                        # 尾部 MOVE NEXTR / GO TO 自身 → 吸收
        if _contains_goto(st):
            return None                     # 体内有未识别跳转 → 不安全，放弃
        body.append(st)
    if keys is None or exit_label is None:
        return None
    return {"pfx": pfx, "name": name, "keys": keys,
            "exit_label": exit_label, "filters": filters, "body": body}


def _strip_struct_setup(stmts: list[Stmt], pfx: str) -> list[Stmt]:
    """移除对 <pfx>-* 的赋值/INITIALIZE（BEGN setup 已被 finder 吸收）。"""
    out = []
    for st in stmts:
        if st.kind == "simple" and st.tokens:
            tu = [t.upper() for t in st.tokens]
            if tu[0] == "MOVE" and "TO" in tu and any(
                    t.startswith(f"{pfx}-") for t in tu[tu.index("TO") + 1:]):
                continue
            if tu[0] == "INITIALIZE" and any(t.upper().startswith(f"{pfx}-") for t in st.tokens[1:]):
                continue
        out.append(st)
    return out


def _tag_rebind(stmts: list[Stmt], rebind: dict) -> None:
    """给 for-each 体内所有 Stmt（含嵌套）打结构体重绑定标记，供延迟的叶子翻译使用。"""
    for st in stmts:
        st.struct_rebind = rebind
        _tag_rebind(st.children, rebind)
        _tag_rebind(st.else_children, rebind)
        for _c, body in (st.whens or []):
            _tag_rebind(body, rebind)


def _render_begn_foreach(info: dict, ctx: Ctx) -> list[str]:
    """渲染 List + for-each（裸字段名，st. 前缀由 nodes 后处理统一添加）。"""
    pfx, name = info["pfx"], info["name"]
    io = resolve_io_info(name, ctx.io_programs, ctx.io_default_pattern)
    repo = io["field_name"] if io else _java(pfx) + "Repository"
    rec_cls = _pascal(pfx) + "Record"
    loop_var = _java(pfx)
    list_var = loop_var + "List"
    finder = "findBy" + "And".join(_pascal(k) for k, _ in info["keys"]) + "Begn"
    vals = ", ".join(_operand(v, ctx) for _, v in info["keys"])
    lines = [f"List<{rec_cls}> {list_var} = {repo}.{finder}({vals});",
             f"for ({rec_cls} {loop_var} : {list_var}) {{"]
    rebind = {pfx: loop_var}
    _tag_rebind(info["filters"] + info["body"], rebind)   # 延迟叶子用标记
    saved = ctx.struct_objects.get(pfx)
    ctx.struct_objects[pfx] = loop_var          # 渲染期条件/循环头 <pfx>-FIELD → loop_var.getField()
    for f in info["filters"]:
        cond = _try_condition(f.tokens, ctx)
        lines.append(f"    if ({cond}) {{ continue; }}" if cond
                     else f"    // TODO 过滤条件: {' '.join(f.tokens)}")
    lines.extend(build_skeleton(info["body"], ctx, 1))
    if saved is None:
        ctx.struct_objects.pop(pfx, None)
    else:
        ctx.struct_objects[pfx] = saved
    lines.append("}")
    return lines


def _stmt_touches_pfx(st: Stmt, pfx: str) -> bool:
    """检查语句 token 中是否包含 <pfx>- 前缀的标识符。"""
    if st.kind != "simple" or not st.tokens:
        return False
    for t in st.tokens:
        if t.upper().startswith(f"{pfx}-"):
            return True
    return False


def _match_begn_single(stmts: list[Stmt], ctx: Ctx):
    """识别单次 BEGN 等值定位（无 NEXTR 回跳）：INITIALIZE → MOVE keys → MOVE BEGN → CALL → IF。
    返回 {pfx,name,keys,then_stmts,call_idx,setup_start} 或 None。"""
    if not stmts:
        return None

    # 1. 定位 CALL 'xxxIO' USING pfx-PARAMS（前序须有 MOVE BEGN TO pfx-FUNCTION）
    call_idx = None
    call_info = None
    for i, st in enumerate(stmts):
        ci = _stmt_call_io(st, ctx)
        if ci:
            name, pfx = ci
            for s in stmts[:i]:
                if s.kind == "simple" and s.tokens:
                    tu = [t.upper() for t in s.tokens]
                    if tu[:1] == ["MOVE"] and "BEGN" in tu and f"{pfx}-FUNCTION" in tu:
                        call_idx = i
                        call_info = ci
                        break
            if call_idx is not None:
                break
    if call_idx is None:
        return None

    name, pfx = call_info

    # 2. 紧随 CALL 后须有 IF（then 分支不含 GO TO 回跳）
    if call_idx + 1 >= len(stmts):
        return None
    if_stmt = stmts[call_idx + 1]
    if if_stmt.kind != "if":
        return None

    # then 分支含 GO TO 回跳 → 属于 loop pattern，不在 single-shot 处理
    if _contains_goto(if_stmt):
        return None

    # 从 IF 条件提取等值键（复用 loop 的 breakout keys 解析）
    keys = _begn_breakout_keys(if_stmt.tokens, pfx)
    if not keys:
        return None

    # 3. 从 CALL 向前找 setup 起始（首个不涉及 pfx 的语句的下一位置）
    setup_start = call_idx
    for i in range(call_idx - 1, -1, -1):
        if _stmt_touches_pfx(stmts[i], pfx):
            setup_start = i
        else:
            break

    return {
        "pfx": pfx, "name": name, "keys": keys,
        "then_stmts": if_stmt.children,
        "call_idx": call_idx, "setup_start": setup_start,
    }


def _render_begn_single(info: dict, ctx: Ctx) -> list[str]:
    """渲染单次 BEGN → findBy...Begn() + List.isEmpty() 检查。"""
    pfx, name = info["pfx"], info["name"]
    io = resolve_io_info(name, ctx.io_programs, ctx.io_default_pattern)
    repo = io["field_name"] if io else _java(pfx) + "Repository"
    rec_cls = _pascal(pfx) + "Record"
    list_var = _java(pfx) + "List"
    finder = "findBy" + "And".join(_pascal(k) for k, _ in info["keys"]) + "Begn"
    vals = ", ".join(_operand(v, ctx) for _, v in info["keys"])

    lines = [f"List<{rec_cls}> {list_var} = {repo}.{finder}({vals});"]
    then_lines = build_skeleton(info["then_stmts"], ctx, 1)
    if then_lines:
        lines.append(f"if ({list_var}.isEmpty()) {{")
        lines.extend(then_lines)
        lines.append("}")
    return lines


def _rewrite_begn_loops(paras: list[tuple], ctx: Ctx) -> list[tuple]:
    """把 BEGN+NEXTR 自跳循环 / 单次 BEGN 等值定位 改写为 List+for-each / findBy…Begn()。"""
    norm = [(lbl or f"__ENTRY_{i}", list(stmts)) for i, (lbl, stmts) in enumerate(paras)]
    labels = [l for l, _ in norm]
    result = [(paras[i][0], norm[i][1]) for i in range(len(paras))]   # (原标签, stmts副本)
    changed = False

    # ── Pass 1：BEGN + NEXTR 自跳循环 ──────────────────────────────────
    for i, (lbl, stmts) in enumerate(norm):
        info = _match_begn_loop(lbl, stmts, ctx)
        if not info:
            continue
        next_lbl = labels[i + 1] if i + 1 < len(labels) else None
        if info["exit_label"] != next_lbl:
            continue                                   # 跳出目标须为相邻下一段，才能自然 fall-through
        if not any(_setup_has_begn(s, info["pfx"]) for _, s in norm[:i]):
            continue                                   # 前序段须有 MOVE BEGN（确认是 BEGN 读）
        raw = Stmt(kind="raw", tokens=[])
        raw.lines = _render_begn_foreach(info, ctx)
        result[i] = (paras[i][0], [raw])
        for k in range(i):                             # 剥除前序段里该 pfx 的 setup
            result[k] = (result[k][0], _strip_struct_setup(result[k][1], info["pfx"]))
        changed = True

    # ── Pass 2：单次 BEGN 等值定位（同段内 setup + CALL + IF，无回跳）──
    for i, (_lbl, _stmts) in enumerate(norm):
        if result[i][1] and result[i][1][0].kind == "raw":
            continue   # 已被 Pass 1 处理为循环
        info = _match_begn_single(_stmts, ctx)
        if not info:
            continue
        raw = Stmt(kind="raw", tokens=[])
        raw.lines = _render_begn_single(info, ctx)
        before = _stmts[:info["setup_start"]]
        after = _stmts[info["call_idx"] + 2:]   # 跳过 CALL + IF
        result[i] = (paras[i][0], before + [raw] + after)
        changed = True

    return result if changed else paras


def build_section(paras: list[tuple], ctx: Ctx, indent: int = 0) -> list[str]:
    """
    段内控制流降级。paras = [(label_or_None, [Stmt]), ...]。
    - 先尝试把 BEGN+NEXTR 自跳循环改写为 List + for-each（吸收 setFunction/跳出/NEXTR）。
    - 无回跳 GO TO（back-edge）：扁平拼接各 paragraph 骨架（前向 GO TO→EXIT 仍按 return 处理）。
    - 存在回跳（target paragraph 索引 <= 当前）：用带标签的 while(true)+switch 状态机降级。
    """
    paras = _rewrite_begn_loops(paras, ctx)
    # 首段若无标签，赋合成入口名
    norm: list[tuple[str, list[Stmt]]] = [
        (lbl or f"__ENTRY_{i}", stmts) for i, (lbl, stmts) in enumerate(paras)
    ]
    labels = [l for l, _ in norm]
    label_index = {l: i for i, l in enumerate(labels)}

    has_back_edge = False
    for i, (_lbl, stmts) in enumerate(norm):
        for tgt in _collect_gotos(stmts):
            j = label_index.get(tgt)
            if j is not None and j <= i:
                has_back_edge = True
                break
        if has_back_edge:
            break

    if not has_back_edge:
        ctx.flow_label = None
        ctx.flow_paragraphs = set()
        out: list[str] = []
        for lbl, stmts in norm:
            if not lbl.startswith("__ENTRY_"):
                out.append(f"{_ind(indent)}// paragraph {lbl}")
            out.extend(build_skeleton(stmts, ctx, indent))
        return out

    # 状态机降级
    ctx.flow_label = "FLOW"
    ctx.flow_paragraphs = set(labels)
    out = [
        f'{_ind(indent)}String __pc = "{labels[0]}";   // 段内 GO TO 回跳 → 状态机',
        f"{_ind(indent)}FLOW: while (true) {{",
        f"{_ind(indent + 1)}switch (__pc) {{",
    ]
    for i, (lbl, stmts) in enumerate(norm):
        out.append(f'{_ind(indent + 1)}case "{lbl}": {{')
        out.extend(build_skeleton(stmts, ctx, indent + 2))
        if not _ends_with_transfer(stmts):
            if i + 1 < len(norm):
                out.append(f'{_ind(indent + 2)}__pc = "{labels[i + 1]}"; continue FLOW;  // fall-through')
            else:
                out.append(f"{_ind(indent + 2)}break FLOW;")
        out.append(f"{_ind(indent + 1)}}}")
    out.append(f"{_ind(indent + 1)}default: break FLOW;")
    out.append(f"{_ind(indent + 1)}}}")
    out.append(f"{_ind(indent)}}}")
    ctx.flow_label = None
    ctx.flow_paragraphs = set()
    return out


# ── 骨架层 ────────────────────────────────────────────────────────────────────

def build_skeleton(stmts: list[Stmt], ctx: Ctx, indent: int = 0) -> list[str]:
    lines: list[str] = []
    for st in stmts:
        lines.extend(_skeleton_one(st, ctx, indent))
    return lines


def _skeleton_one(st: Stmt, ctx: Ctx, indent: int) -> list[str]:
    if st.kind == "raw":
        # 预渲染的 Java 行（如 BEGN+NEXTR → List+for 改写），按当前缩进整体下沉
        return [(_ind(indent) + l if l else l) for l in getattr(st, "lines", [])]
    if st.kind == "if":
        return _sk_if(st, ctx, indent)
    if st.kind == "evaluate":
        return _sk_evaluate(st, ctx, indent)
    if st.kind == "perform":
        return _sk_perform(st, ctx, indent)
    # simple
    first = (st.tokens[0].upper() if st.tokens else "")
    if first in _CONTROL_FIRST:
        return _sk_control(st, ctx, indent)
    # 叶子 → 占位
    return [_ind(indent) + ctx.new_leaf(st)]


def _sk_if(st: Stmt, ctx: Ctx, indent: int) -> list[str]:
    cond = _try_condition(st.tokens, ctx)
    if cond is None:
        # 条件无法确定 → 整个 IF 交 LLM
        return [_ind(indent) + ctx.new_leaf(st)]
    lines = [f"{_ind(indent)}if ({cond}) {{"]
    body = build_skeleton(st.children, ctx, indent + 1) or [_ind(indent + 1) + "// (空)"]
    lines.extend(body)
    if st.else_children:
        lines.append(f"{_ind(indent)}}} else {{")
        lines.extend(build_skeleton(st.else_children, ctx, indent + 1))
    lines.append(f"{_ind(indent)}}}")
    return lines


def _sk_evaluate(st: Stmt, ctx: Ctx, indent: int) -> list[str]:
    subj = " ".join(st.tokens).strip()
    if subj.upper() in ("TRUE", "") or not st.whens:
        # EVALUATE TRUE（条件式）较复杂，交 LLM
        return [_ind(indent) + ctx.new_leaf(st)]
    subj_java = _operand(st.tokens[0], ctx) if len(st.tokens) == 1 else None
    if subj_java is None:
        return [_ind(indent) + ctx.new_leaf(st)]
    lines = [f"{_ind(indent)}switch ({subj_java}.trim()) {{"]
    for cond, body in st.whens:
        cu = " ".join(cond).upper()
        if cu in ("OTHER", ""):
            lines.append(f"{_ind(indent + 1)}default: {{")
        else:
            val = _operand(cond[0], ctx) if cond else '""'
            lines.append(f"{_ind(indent + 1)}case {val}: {{")
        lines.extend(build_skeleton(body, ctx, indent + 2))
        lines.append(f"{_ind(indent + 2)}break;")
        lines.append(f"{_ind(indent + 1)}}}")
    lines.append(f"{_ind(indent)}}}")
    return lines


def _proc_call(target: str, ctx: Ctx) -> str:
    method = ctx.section_to_method(target)
    return f"this.{method}();"


def _sk_perform(st: Stmt, ctx: Ctx, indent: int) -> list[str]:
    header = st.tokens
    hu = [h.upper() for h in header]
    # 提取过程名（首 token 非循环关键字且非纯数字）
    target = None
    if header and hu[0] not in {"VARYING", "UNTIL", "WITH", "TEST"} and not header[0].isdigit():
        target = header[0].upper()

    # 循环子句
    loop_open: list[str] = []
    loop_close = ""
    # VARYING v FROM a BY b UNTIL cond
    if "VARYING" in hu:
        try:
            vi = hu.index("VARYING")
            v = _operand(header[vi + 1], ctx)
            a = _operand(header[hu.index("FROM") + 1], ctx)
            b = _operand(header[hu.index("BY") + 1], ctx)
            ucond = _try_condition(header[hu.index("UNTIL") + 1:], ctx)
            if ucond is None:
                return [_ind(indent) + ctx.new_leaf(st)]
            loop_open = [f"{_ind(indent)}for ({v} = {a}; !({ucond}); {v} = {v} + {b}) {{"]
            loop_close = f"{_ind(indent)}}}"
        except (ValueError, IndexError):
            return [_ind(indent) + ctx.new_leaf(st)]
    elif "UNTIL" in hu:
        ucond = _try_condition(header[hu.index("UNTIL") + 1:], ctx)
        if ucond is None:
            return [_ind(indent) + ctx.new_leaf(st)]
        loop_open = [f"{_ind(indent)}while (!({ucond})) {{"]
        loop_close = f"{_ind(indent)}}}"
    elif "TIMES" in hu:
        ti = hu.index("TIMES")
        cnt = _operand(header[ti - 1], ctx) if ti > 0 else "1"
        loop_open = [f"{_ind(indent)}for (int _i = 0; _i < {cnt}; _i++) {{"]
        loop_close = f"{_ind(indent)}}}"

    inner_indent = indent + (1 if loop_open else 0)
    body: list[str] = []
    if st.children:
        body = build_skeleton(st.children, ctx, inner_indent)
    elif target:
        body = [_ind(inner_indent) + _proc_call(target, ctx)]
    else:
        return [_ind(indent) + ctx.new_leaf(st)]

    if loop_open:
        return loop_open + body + [loop_close]
    return body


def _sk_control(st: Stmt, ctx: Ctx, indent: int) -> list[str]:
    toks = [t.upper() for t in st.tokens]
    first = toks[0]
    if first == "GO":
        # GO TO target
        target = None
        for t in toks:
            if t not in ("GO", "TO"):
                target = t
                break
        # dispatch 模式下，目标是本段 paragraph → 状态机跳转（保住循环/分支语义）
        if target and ctx.flow_label and target in ctx.flow_paragraphs:
            return [f'{_ind(indent)}__pc = "{target}"; continue {ctx.flow_label};  // GO TO {target}']
        if target and target.endswith("EXIT"):
            return [f"{_ind(indent)}return;  // GO TO {target}"]
        if target:
            line = f"{_ind(indent)}// TODO-GOTO: 跳转 {target}，需人工核对控制流"
            if target in ctx.known_sections:
                return [line, f"{_ind(indent)}{_proc_call(target, ctx)}", f"{_ind(indent)}return;"]
            return [line, f"{_ind(indent)}return;"]
        return [f"{_ind(indent)}return;"]
    if first in ("GOBACK", "STOP"):
        return [f"{_ind(indent)}return;"]
    if first == "EXIT":
        # dispatch 模式下 EXIT paragraph = 退出状态机循环
        if ctx.flow_label:
            return [f"{_ind(indent)}break {ctx.flow_label};  // EXIT"]
        return [f"{_ind(indent)}return;  // EXIT"]
    if first == "CONTINUE":
        return [f"{_ind(indent)};  // CONTINUE"]
    if first == "NEXT":
        return [f"{_ind(indent)};  // NEXT SENTENCE"]
    return [_ind(indent) + ctx.new_leaf(st)]


# ── 叶子层 ────────────────────────────────────────────────────────────────────

def translate_leaf(stmt: Stmt, ctx: Ctx) -> tuple[list[str], bool]:
    toks = stmt.tokens
    if not toks:
        return [], False
    # for-each 体内的叶子：临时把结构体对象重绑定到循环变量（<pfx>-FIELD → loopVar.getField()）。
    # 叶子翻译发生在第二趟（占位符回填），故需随 stmt 携带重绑定，而非依赖渲染期 ctx。
    rebind = getattr(stmt, "struct_rebind", None)
    saved = None
    if rebind:
        saved = {k: ctx.struct_objects.get(k) for k in rebind}
        ctx.struct_objects.update(rebind)
    try:
        return _dispatch_leaf(toks, ctx)
    finally:
        if rebind:
            for k, v in saved.items():
                if v is None:
                    ctx.struct_objects.pop(k, None)
                else:
                    ctx.struct_objects[k] = v


def _dispatch_leaf(toks: list[str], ctx: Ctx) -> tuple[list[str], bool]:
    verb = toks[0].upper()
    try:
        if verb == "MOVE":
            return _t_move(toks, ctx)
        if verb == "INITIALIZE":
            return _t_initialize(toks, ctx)
        if verb == "SET":
            return _t_set(toks, ctx)
        if verb == "ADD":
            return _t_add(toks, ctx)
        if verb == "SUBTRACT":
            return _t_subtract(toks, ctx)
        if verb == "MULTIPLY":
            return _t_multiply(toks, ctx)
        if verb == "DIVIDE":
            return _t_divide(toks, ctx)
        if verb == "COMPUTE":
            return _t_compute(toks, ctx)
        if verb == "CALL":
            return _t_call(toks, ctx)
    except (ValueError, IndexError):
        return [], False
    return [], False


def derive_io_info(name: str, pattern: dict | None) -> dict | None:
    """按 io_mappings.yaml 的 `io_default_pattern` 范式为 CALL 'xxxIO' 兜底派生 Repository 映射。

    所有映射关系（类/字段后缀、包名、参数结构体后缀、操作码→方法）都来自配置表 pattern，
    py 只负责套用命名范式（base → PascalCase/camelCase），不写死任何业务映射。
    例（pattern 后缀=Repository、包=com.example.repository）：
      SCF4CHRIO → Scf4chrRepository / scf4chrRepository / SCF4CHR-PARAMS。
    仅对 *IO 结尾的子程序生效；pattern 缺失或非 *IO → 返回 None（不派生）。
    """
    if not pattern:
        return None
    if not name or not name.upper().endswith("IO") or len(name) <= 2:
        return None
    base = name[:-2].upper()              # SCF4CHR
    cls_base = base.lower().capitalize()  # Scf4chr（PascalCase）
    field = cls_base[0].lower() + cls_base[1:]  # scf4chr（camelCase）
    cls = f"{cls_base}{pattern.get('class_suffix', '')}"
    return {
        "java_class": cls,
        "field_name": f"{field}{pattern.get('field_suffix', '')}",
        "param_struct": f"{base}{pattern.get('param_struct_suffix', '')}",
        "import": f"{pattern.get('import_package', '').rstrip('.')}.{cls}",
        "operations": dict(pattern.get("operations", {})),
        "_derived": True,
    }


def resolve_io_info(name: str, io_programs: dict, pattern: dict | None) -> dict | None:
    """统一解析 CALL 'xxxIO' 的映射：派生范式做基底，io_programs 显式条目按字段/操作码深合并覆盖。

    这样 io_mappings.yaml 的 io_programs 只需登记「非标准的增量」（如某表 READR 用
    findByPolicyNo），java_class/field_name/param_struct/import 与标准操作码全部由
    io_default_pattern 自动派生，无需逐表重复抄写。
    非 *IO 子程序（无法派生）→ 直接返回显式条目或 None。
    """
    base = derive_io_info(name, pattern)
    entry = io_programs.get(name)
    if not base:
        return entry            # 非 *IO：只认显式登记
    if not entry:
        return base             # 纯标准 *IO：全靠范式
    merged = {**base, **entry}  # 顶层字段：显式覆盖派生
    ops = dict(base.get("operations", {}))
    ops.update(entry.get("operations", {}))   # 操作码：逐码覆盖，未覆盖的保留标准派生
    merged["operations"] = ops
    return merged


def _t_call(toks: list[str], ctx: Ctx) -> tuple[list[str], bool]:
    """
    CALL 'xxxIO' USING xxx-PARAMS → 固化 Repository 调用。
      · 功能码由前一句 MOVE … TO xxx-FUNCTION 设，记在 ctx.struct_function。
      · 单条操作（READR/UPDAT/WRITE/DELET…）在 io_default_pattern.operations 有对应方法
        → 直出 obj = repo.method(obj);
      · 顺序读游标（BEGN/BEGNH/NEXTR）刻意不在 operations 中（无法用固定单方法表达，
        见 knowledge/io_call_patterns.md）→ 落到运行时分发 obj = repo.execute(obj.getFunction(), obj);
        在还原出的 while 循环内逐条推进（功能码经 MOVE 由 BEGN→NEXTR 变化）。
      · 功能码静态也拿不到 → 同样走 execute() 运行时分发（仍确定性）。
      · 未映射的子程序 → matched=False，交 LLM 兜底。
    契约：参数对象进出（Repository 在返回对象上写 STATUZ），下游 STATUZ 检查零改写。
    """
    if len(toks) < 2:
        return [], False
    name = toks[1].strip("'\"").upper()

    # 取 USING 后第一个实参作为参数结构体
    u = [t.upper() for t in toks]
    arg = None
    if "USING" in u:
        ui = u.index("USING")
        if ui + 1 < len(toks):
            arg = toks[ui + 1]

    # 表里有用表里的；没有但符合 *IO 查表范式 → 按命名规范兜底派生（固定化翻译）
    info = resolve_io_info(name, ctx.io_programs, ctx.io_default_pattern)
    if info:
        repo = info["field_name"]
        ops = info.get("operations", {})
        prefix = (arg.split("-", 1)[0].upper() if arg and "-" in arg
                  else info.get("param_struct", "").split("-", 1)[0].upper())
        obj = _struct_obj(prefix, ctx) if prefix else "params"
        func = ctx.struct_function.get(prefix)
        if func and func in ops:
            method = re.sub(r"\{[^}]*\}", obj, ops[func])           # findByKey({key}) → findByKey(elpoParams)
            return [f"{obj} = {repo}.{method};"], True               # 静态固化
        # 功能码静态拿不到 → 运行时分发
        return [f"{obj} = {repo}.execute({obj}.{ctx.struct_getter}Function(), {obj});"], True

    # 日期子程序：dateConversionService.convertDateN(params)
    dinfo = ctx.date_programs.get(name)
    if dinfo and dinfo.get("method") and dinfo.get("field_name"):
        prefix = (arg.split("-", 1)[0].upper() if arg and "-" in arg else name)
        obj = _struct_obj(prefix, ctx)
        method = re.sub(r"\{[^}]*\}", obj, dinfo["method"])
        return [f"{dinfo['field_name']}.{method};"], True

    # 系统子程序（SYSERR 等）：直出 java_code，否则 service.method
    sinfo = ctx.system_programs.get(name)
    if sinfo:
        if sinfo.get("java_code"):
            code = sinfo["java_code"].strip()
            return [code if code.endswith(";") else code + ";"], True
        if sinfo.get("method") and sinfo.get("field_name"):
            prefix = (arg.split("-", 1)[0].upper() if arg and "-" in arg else name)
            obj = _struct_obj(prefix, ctx)
            method = re.sub(r"\{[^}]*\}", obj, sinfo["method"])
            return [f"{sinfo['field_name']}.{method};"], True

    return [], False    # 未映射 → LLM 兜底


def _t_move(toks: list[str], ctx: Ctx) -> tuple[list[str], bool]:
    # MOVE src TO dst1 [dst2 ...]
    if "TO" not in [t.upper() for t in toks]:
        return [], False
    ti = [t.upper() for t in toks].index("TO")
    src_toks = toks[1:ti]
    dsts = toks[ti + 1:]
    if len(src_toks) != 1 or not dsts:
        return [], False
    src = src_toks[0]
    su = src.upper()
    lines: list[str] = []
    for dst in dsts:
        # 跟踪 IO 功能码：MOVE READR TO ELPO-FUNCTION → struct_function["ELPO"]="READR"
        # （仍照常生成 setter，因运行时分发退路需要 obj.getFunction() 携带功能码）
        sp_dst = _struct_prefix(dst, ctx)
        if sp_dst and sp_dst[1] == "FUNCTION":
            ctx.struct_function[sp_dst[0]] = su.strip("'\"")
        if su in _FIGURATIVE_BLANK:
            val = '""' if not _is_numeric_field(dst, ctx) else ("BigDecimal.ZERO" if _is_bigdecimal(dst, ctx) else "0")
        elif su in _FIGURATIVE_ZERO:
            val = "BigDecimal.ZERO" if _is_bigdecimal(dst, ctx) else "0"
        else:
            val = _operand(src, ctx)
            if _is_bigdecimal(dst, ctx) and re.fullmatch(r"[+-]?\d+(\.\d+)?", val):
                val = _bd(val)
        lines.append(_assign(dst, val, ctx))
    return lines, True


def _t_initialize(toks: list[str], ctx: Ctx) -> tuple[list[str], bool]:
    """INITIALIZE dst1 [dst2 ...] → 重置为默认值。
      · 结构体参数（X-PARAMS）→ obj = new XParams();（与 MOVE SPACES 重置一致）
      · 数值字段 → 0 / BigDecimal.ZERO；字符串字段 → ""
      · 带 REPLACING/含未识别目标 → 整体交 LLM（避免半翻）。
    """
    dsts = toks[1:]
    if not dsts:
        return [], False
    lines: list[str] = []
    for dst in dsts:
        if dst.upper() in ("REPLACING", "TO", "VALUE", "ALL"):
            return [], False
        sp = _struct_prefix(dst, ctx)
        if sp and sp[1] == "PARAMS":
            lines.append(f"{_struct_obj(sp[0], ctx)} = new {_struct_cls(sp[0], ctx)}();")
        elif _is_field(dst, ctx):
            if _is_bigdecimal(dst, ctx):
                val = "BigDecimal.ZERO"
            elif _is_numeric_field(dst, ctx):
                val = "0"
            else:
                val = '""'
            lines.append(_assign(dst, val, ctx))
        else:
            return [], False
    return lines, True


def _t_set(toks: list[str], ctx: Ctx) -> tuple[list[str], bool]:
    # SET a [b] TO value  （仅处理 TO 数值/字段；TO TRUE/ON 等交 LLM）
    u = [t.upper() for t in toks]
    if "TO" not in u:
        return [], False
    ti = u.index("TO")
    targets = toks[1:ti]
    val_toks = toks[ti + 1:]
    if len(val_toks) != 1 or not targets:
        return [], False
    vu = val_toks[0].upper()
    if vu in ("TRUE", "FALSE", "ON", "OFF"):
        return [], False
    val = _operand(val_toks[0], ctx)
    return [_assign(t, val, ctx) for t in targets], True


def _arith_val(name: str, expr: str, ctx: Ctx) -> str:
    return _bd(expr) if _is_bigdecimal(name, ctx) and re.fullmatch(r"[+-]?\d+(\.\d+)?", expr) else expr


def _t_add(toks: list[str], ctx: Ctx) -> tuple[list[str], bool]:
    # ADD a TO b [GIVING c]
    u = [t.upper() for t in toks]
    if "TO" not in u:
        return [], False
    ti = u.index("TO")
    a_toks = toks[1:ti]
    if len(a_toks) != 1:
        return [], False
    a = a_toks[0]
    rest = toks[ti + 1:]
    ru = [t.upper() for t in rest]
    if "GIVING" in ru:
        gi = ru.index("GIVING")
        b = rest[gi - 1]
        c = rest[gi + 1]
        if _is_bigdecimal(c, ctx):
            return [f"{_operand(c, ctx)} = {_operand(b, ctx)}.add({_arith_val(c, _operand(a, ctx), ctx)});"], True
        return [f"{_operand(c, ctx)} = {_operand(b, ctx)} + {_operand(a, ctx)};"], True
    b = rest[0]
    if _is_bigdecimal(b, ctx):
        return [f"{_operand(b, ctx)} = {_operand(b, ctx)}.add({_arith_val(b, _operand(a, ctx), ctx)});"], True
    return [f"{_operand(b, ctx)} += {_operand(a, ctx)};"], True


def _t_subtract(toks: list[str], ctx: Ctx) -> tuple[list[str], bool]:
    # SUBTRACT a FROM b [GIVING c]
    u = [t.upper() for t in toks]
    if "FROM" not in u:
        return [], False
    fi = u.index("FROM")
    a_toks = toks[1:fi]
    if len(a_toks) != 1:
        return [], False
    a = a_toks[0]
    rest = toks[fi + 1:]
    ru = [t.upper() for t in rest]
    if "GIVING" in ru:
        gi = ru.index("GIVING")
        b = rest[gi - 1]
        c = rest[gi + 1]
        if _is_bigdecimal(c, ctx):
            return [f"{_operand(c, ctx)} = {_operand(b, ctx)}.subtract({_arith_val(c, _operand(a, ctx), ctx)});"], True
        return [f"{_operand(c, ctx)} = {_operand(b, ctx)} - {_operand(a, ctx)};"], True
    b = rest[0]
    if _is_bigdecimal(b, ctx):
        return [f"{_operand(b, ctx)} = {_operand(b, ctx)}.subtract({_arith_val(b, _operand(a, ctx), ctx)});"], True
    return [f"{_operand(b, ctx)} -= {_operand(a, ctx)};"], True


def _t_multiply(toks: list[str], ctx: Ctx) -> tuple[list[str], bool]:
    # MULTIPLY a BY b [GIVING c]
    u = [t.upper() for t in toks]
    if "BY" not in u:
        return [], False
    bi = u.index("BY")
    a = toks[1:bi]
    if len(a) != 1:
        return [], False
    a = a[0]
    rest = toks[bi + 1:]
    ru = [t.upper() for t in rest]
    if "GIVING" in ru:
        gi = ru.index("GIVING")
        b = rest[gi - 1]
        c = rest[gi + 1]
    else:
        b = c = rest[0]
    if _is_bigdecimal(c, ctx):
        return [f"{_operand(c, ctx)} = {_operand(b, ctx)}.multiply({_arith_val(c, _operand(a, ctx), ctx)});"], True
    return [f"{_operand(c, ctx)} = {_operand(b, ctx)} * {_operand(a, ctx)};"], True


def _t_divide(toks: list[str], ctx: Ctx) -> tuple[list[str], bool]:
    # DIVIDE a INTO b [GIVING c] | DIVIDE a BY b GIVING c [ROUNDED]
    u = [t.upper() for t in toks]
    rounded = "ROUNDED" in u
    if "INTO" in u:
        ki = u.index("INTO")
        divisor = toks[1]          # a INTO b: a 是除数
        rest = toks[ki + 1:]
    elif "BY" in u:
        ki = u.index("BY")
        dividend_pre = toks[1:ki]
        rest = toks[ki + 1:]
        if len(dividend_pre) != 1:
            return [], False
        # a BY b: a/b
        dividend = dividend_pre[0]
        ru = [t.upper() for t in rest]
        divisor = rest[0]
        if "GIVING" in ru:
            c = rest[ru.index("GIVING") + 1]
        else:
            c = dividend
        if _is_bigdecimal(c, ctx):
            scale = "2" if rounded else "2"
            return [f"{_operand(c, ctx)} = {_operand(dividend, ctx)}.divide({_operand(divisor, ctx)}, {scale}, RoundingMode.HALF_UP);"], True
        return [f"{_operand(c, ctx)} = {_operand(dividend, ctx)} / {_operand(divisor, ctx)};"], True
    else:
        return [], False
    # INTO 形式
    ru = [t.upper() for t in rest]
    b = rest[0]
    c = rest[ru.index("GIVING") + 1] if "GIVING" in ru else b
    if _is_bigdecimal(c, ctx):
        return [f"{_operand(c, ctx)} = {_operand(b, ctx)}.divide({_operand(divisor, ctx)}, 2, RoundingMode.HALF_UP);"], True
    return [f"{_operand(c, ctx)} = {_operand(b, ctx)} / {_operand(divisor, ctx)};"], True


def _t_compute(toks: list[str], ctx: Ctx) -> tuple[list[str], bool]:
    # COMPUTE dst [ROUNDED] = expr  （仅固化整型；BigDecimal 表达式交 LLM）
    u = [t.upper() for t in toks]
    if "=" not in u:
        return [], False
    eq = u.index("=")
    dst_toks = [t for t in toks[1:eq] if t.upper() != "ROUNDED"]
    if len(dst_toks) != 1:
        return [], False
    dst = dst_toks[0]
    if _is_bigdecimal(dst, ctx):
        return [], False  # BigDecimal 中缀转链式不可靠 → LLM
    expr_toks = toks[eq + 1:]
    parts = []
    for t in expr_toks:
        if t in ("+", "-", "*", "/", "(", ")"):
            parts.append(t)
        else:
            parts.append(_operand(t, ctx))
    return [f"{_operand(dst, ctx)} = {' '.join(parts)};"], True
