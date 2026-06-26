"""
固化规则引擎。

两层职责：
- 骨架层 build_skeleton(): 递归生成控制流/调用结构（IF/EVALUATE/PERFORM/GO/CONTINUE…），
  叶子语句位置插入占位 `/*__LEAF_n__*/` 并登记到 leaves，确定性、不调 LLM。
- 叶子层 translate_leaf(): 对单条叶子语句（MOVE/算术/SET…）尝试固化；命中返回 Java，
  未命中 matched=False，交 LLM 兜底。

字段名一律输出"裸名"，由 translator.postprocess._postprocess_java_body 统一加 `st.` 前缀并做跨模块路由。
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field

from config import grammar_loader               # 控制流降级策略正本（步骤08）
from config import spec_loader                   # 命名正本（步骤13 §2.4：合成区间方法名）
from translator.segmenter import Stmt
# 叶子翻译公用底座（步骤18 绞杀项3①）：MOVE 译器 + 表达式底座下沉至 translator.leaf，
# 此处只读 import 回来，原 helper 定义已删、改委托（依赖单向 rules → leaf，无环）。
from translator.leaf.expr import (
    _FIGURATIVE_BLANK, _FIGURATIVE_ZERO, _assign, _field_base, _is_bigdecimal,
    _is_field, _is_numeric_field, _is_string_field, _java, _lvalue, _operand, _pascal,
    _refmod_hi, _refmod_lo, _struct_cls, _struct_obj, _struct_prefix,
)
from translator.leaf.move import translate_move
# 条件翻译（步骤19 绞杀项3②）：_try_condition 闭包下沉至 translator.leaf.cond，别名导回，
# _sk_if / PERFORM-UNTIL / WHEN / BEGN-foreach 过滤等 4 处调用点零改（依赖单向 rules → leaf，无环）。
from translator.leaf.cond import translate_condition as _try_condition
# PERFORM 循环子句翻译（步骤20 绞杀项3③）：_perform_loop 三件套下沉至 translator.leaf.loop，
# 原名导回，_sk_perform 调用点零改（依赖单向 rules → leaf，无环）。
from translator.leaf.loop import _perform_loop
# CALL 散点兜底翻译（步骤21 绞杀项3④）：_t_call 下沉至 translator.leaf.call，别名导回 → _dispatch_leaf 零改；
# resolve_io_info/derive_io_info 一并下沉再导入回 → 结构吸收 4 处调用点 + rules.resolve_io_info 公开面零改
# （graph/nodes、main、context、skeleton、regress 等外部引用照常；依赖单向 rules → leaf，无环）。
from translator.leaf.call import translate_call as _t_call, resolve_io_info, derive_io_info
# 算术/赋值叶子动词（步骤22 绞杀项3⑤）：_t_initialize/_t_set 下沉 translator.leaf.assign，
# _t_add/_t_subtract/_t_multiply/_t_divide/_t_compute（及私有 _arith_val）下沉 translator.leaf.arith，
# 别名导回 → _dispatch_leaf 7 个调用点零改；_arith_val 仅 4 算术译器内部用、随迁不再导入
# （依赖单向 rules → leaf，无环）。
from translator.leaf.assign import _t_initialize, _t_set
from translator.leaf.arith import _t_add, _t_subtract, _t_multiply, _t_divide, _t_compute
# 控制流动词（步骤23 绞杀项3⑥）：_sk_control 的 flow_label-无关分支 + _sk_evaluate 的 switch 壳判定
# 下沉 translator.leaf.control，rules 委托（dispatch 分支保留在 _sk_control，骨架态不迁）；
# 依赖单向 rules → leaf，无环。
from translator.leaf.control import translate_control, translate_evaluate, evaluate_case_label


@dataclass
class Ctx:
    field_type_map: dict
    section_to_method: object          # callable: SEC名 -> java 方法名
    known_sections: set                # 所有 SECTION 名（大写）
    section_order: list = dc_field(default_factory=list)  # 全程序 SECTION 名顺序（大写）——PERFORM…THRU 区间判定用（步骤12 §2）
    # 步骤13 §2.1 缺口1：全程序「过程单元顺序表」，四元 (name_upper, kind, section_upper, body_lines)，
    # kind∈{section,paragraph}，按源码物理顺序罗列所有 SECTION 头与其下 paragraph；paragraph 级 THRU 区间解析用。
    proc_order: list = dc_field(default_factory=list)
    # 步骤13 §2.3 缺口2：程序级合成区间方法登记表，{合成方法名: 区间内各单元体按 proc_order 序拼接的 COBOL 行}。
    # **程序级、reset_section 不清**：_perform_range 命中 paragraph 区间时登记，render_skeleton 收尾 drain 落地为类级方法。
    pending_range_methods: dict = dc_field(default_factory=dict)
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

_REL_OPS = {"=": "==", ">": ">", "<": "<", ">=": ">=", "<=": "<=", "NOT": "NOT"}


def _ind(n: int) -> str:
    return "    " * n


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


# ── BEGN/READR/WRITE IO 形态识别 + struct_rebind 段级吸收（步骤24C 绞杀项4 骨架装配③）──
# 整族（_rewrite_begn_loops 一族 ~600 行）下沉 translator.skel.io_rewrite（路径中立：NodeAccess +
# render_body + make_raw 回调），rules 委托、与 asg.visitor 共调同一匹配/渲染 → IO 吸收体逐字符一致。
# 逻辑零改（设计24C §3.3/§4.3）。build_section 调用点（_rewrite_begn_loops）零改。
from translator.skel.io_rewrite import rewrite_io_paras, STMT_ACCESS   # noqa: E402


def _raw_stmt(lines: list[str]) -> Stmt:
    """旧路 raw 节点工厂：Stmt(kind="raw") + 预渲染 .lines（build_skeleton 的 kind=="raw" 分支消费）。"""
    raw = Stmt(kind="raw", tokens=[])
    raw.lines = lines
    return raw


def _rewrite_begn_loops(paras: list[tuple], ctx: Ctx) -> list[tuple]:
    """委托 skel.io_rewrite.rewrite_io_paras（旧路注入：STMT_ACCESS / build_skeleton / Stmt-raw）。
    旧路两趟架构：render_body=build_skeleton 留 /*__LEAF_n__*/ 占位、struct_rebind 标记供二趟回填。"""
    return rewrite_io_paras(
        paras, ctx, acc=STMT_ACCESS,
        render_body=lambda stmts, ind: build_skeleton(stmts, ctx, ind),
        make_raw=_raw_stmt,
    )


def build_section(paras: list[tuple], ctx: Ctx, indent: int = 0, force_sm: bool = False) -> list[str]:
    """
    段内控制流降级。paras = [(label_or_None, [Stmt]), ...]。
    - 先尝试把 BEGN+NEXTR 自跳循环改写为 List + for-each（吸收 setFunction/跳出/NEXTR）。
    - 无回跳 GO TO（back-edge）：扁平拼接各 paragraph 骨架（前向 GO TO→EXIT 仍按 return 处理）。
    - 存在回跳（target paragraph 索引 <= 当前）：用带标签的 while(true)+switch 状态机降级。
    - force_sm（步骤14 §2.3 D14-3=a，仅合成区间方法置 True）：区间内**任一**指向内部标签的 GO TO
      （前向亦然）即建状态机，使前向跳过中间单元精确路由。普通 SECTION 默认 False，渲染零变化。
    """
    paras = _rewrite_begn_loops(paras, ctx)   # IO 形态吸收，委托 skel.io_rewrite（步骤24C，设计24C §4.3）
    # 状态机装配下沉 translator.skel.flow_dispatch（步骤24B 绞杀项4 骨架装配②），rules 委托：
    # begn 改写后的 paras + 三回调（本路节点为 Stmt）→ 与 visitor 共用同一装配 → 壳/副作用逐字符一致。
    return render_flow_dispatch(
        paras, ctx, indent,
        render_body=lambda stmts, ind: build_skeleton(stmts, ctx, ind),
        collect_gotos=_collect_gotos,
        ends_transfer=_ends_with_transfer,
        force_sm=force_sm,
    )


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
    # switch 主体判定下沉 leaf.control.translate_evaluate（步骤23 绞杀项3⑥，委托）；
    # WHEN 体渲染/递归仍在骨架层；EVALUATE TRUE/复杂 subject/无 whens → 交 LLM。
    if not st.whens:
        return [_ind(indent) + ctx.new_leaf(st)]
    subj_java = translate_evaluate(st.tokens, ctx)
    if subj_java is None:
        return [_ind(indent) + ctx.new_leaf(st)]
    lines = [f"{_ind(indent)}switch ({subj_java}) {{"]
    for cond, body in st.whens:
        lines.append(f"{_ind(indent + 1)}{evaluate_case_label(cond, ctx)}: {{")
        lines.extend(build_skeleton(body, ctx, indent + 2))
        lines.append(f"{_ind(indent + 2)}break;")
        lines.append(f"{_ind(indent + 1)}}}")
    lines.append(f"{_ind(indent)}}}")
    return lines


# out-of-line PERFORM 调用体（含 THRU 合成区间 + proc_order 路由）：步骤24A 绞杀项4 骨架装配①
# 下沉至 translator.skel.perform_call，rules 委托。别名导回 _perform_range/_perform_single_paragraph/
# _proc_call 保 rules.* 公开面（test_translation 等直接引用），_sk_perform 调用点零改（依赖单向 rules → skel，无环）。
from translator.skel.perform_call import (                # noqa: E402  (置此处紧邻委托点，便于阅读)
    render_perform_call as _perform_range,
    _perform_single_paragraph,
    _perform_range_paragraph,
    _proc_call,
)
# 段内 GO TO dispatch 状态机装配（步骤24B 绞杀项4 骨架装配②）：build_section / _sk_control 委托，
# 与 asg.visitor 共调 → 状态机壳 + flow_label/flow_paragraphs 副作用 + dispatch 行逐字符一致。
from translator.skel.flow_dispatch import (                # noqa: E402
    render_flow_dispatch, dispatch_goto, dispatch_exit,
)


def _sk_perform(st: Stmt, ctx: Ctx, indent: int) -> list[str]:
    header = st.tokens
    hu = [h.upper() for h in header]
    # 提取过程名（首 token 非循环关键字且非纯数字）
    target = None
    if header and hu[0] not in {"VARYING", "UNTIL", "WITH", "TEST"} and not header[0].isdigit():
        target = header[0].upper()

    loop = _perform_loop(header, hu, ctx, indent)   # 步骤16：循环子句解析（含 TEST AFTER / VARYING AFTER）
    if loop is None:
        return [_ind(indent) + ctx.new_leaf(st)]    # 兜不住 → 整条落 LLM 叶子（D16-3）
    open_lines, close_lines = loop

    inner_indent = indent + len(open_lines)         # 每层 open = 一层嵌套，body 进最内层
    if st.children:
        body = build_skeleton(st.children, ctx, inner_indent)
    elif target:
        body = _perform_range(header, hu, target, ctx, inner_indent)
    else:
        return [_ind(indent) + ctx.new_leaf(st)]

    if open_lines:
        return open_lines + body + close_lines
    return body


def _sk_control(st: Stmt, ctx: Ctx, indent: int) -> list[str]:
    # dispatch 模式（flow_label 真）：状态机内 GO/EXIT 路由行，委托 skel.flow_dispatch（步骤24B），
    # 与 visitor 共用同一判定 → 逐字符一致；先于 flow_label-无关委托判定。
    toks = [t.upper() for t in st.tokens]
    first = toks[0]
    if first == "GO":
        target = next((t for t in toks if t not in ("GO", "TO")), None)
        d = dispatch_goto(target, ctx, indent)
        if d is not None:
            return d
    d = dispatch_exit(toks, ctx, indent)
    if d is not None:
        return d
    # flow_label-无关分支委托 leaf.control.translate_control（步骤23 绞杀项3⑥，裸行 + 本层施加 _ind）。
    lines, ok = translate_control(st.tokens, ctx)
    if ok:
        return [_ind(indent) + l for l in lines]
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
            return translate_move(toks, ctx)
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
