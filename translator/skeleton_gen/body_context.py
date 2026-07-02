"""
主线 SECTION 方法体确定性翻译的备料与渲染（步骤07）。

用途：把 CobolProgram 收敛成规则引擎 rules.Ctx 所需的上下文，并把单个 SECTION 的
      COBOL 段体确定性翻译为 Java 方法体（复用 segmenter + rules，无 LLM）。
对应设计：docs/详细设计/步骤07-主线SECTION方法体确定性翻译设计.md。

设计思路：
- 备料配方与 parser.pipeline / graph 同源（resolve→field_type_map、build_struct_registry、io_mappings），
  保证主线与 graph 规则命中的叶子 Java 一致（仅前缀 wsaa. vs st. 不同）。
- 后处理按步骤07 决策 A=方案B（仅数组下标 + wsaa. 前缀，不引入多模块路由）、
  B=B1（this.X() 补成 this.X(wsaa, using…)），复用 postprocess 的公共件。
- ctx 程序级算一次；leaves/_counter/flow_* 是段级状态，每段渲染前重置。
"""
from __future__ import annotations

import re

from config import spec_loader   # IO 映射访问层（步骤09：不再直读 io_mappings.yaml）
from parser.variable_resolver import resolve, build_field_type_map
from translator import rules as _rules
from translator.naming import build_struct_registry
from translator.postprocess import fix_array_subscripts, _prefix_fields_outside_strings
from translator.skeleton import _section_to_method
from translator.segmenter import segment, split_paragraphs


def _load_io_maps() -> dict:
    """组装 io_maps（io_programs 已合并 io_programs2；同 context.py 形态）。经访问层取，不直读 yaml。"""
    return {
        "io_programs": spec_loader.io_programs(),
        "date_programs": spec_loader.date_programs(),
        "system_programs": spec_loader.system_programs(),
        "io_default_pattern": spec_loader.io_default_pattern(),
    }


def _build_proc_order(program) -> list[tuple]:
    """全程序「过程单元顺序表」（步骤13 §2.1 缺口1）：按源码物理顺序罗列每个 SECTION 头与其下 paragraph，
    每项四元 (name_upper, kind, section_upper, body_lines)。
    构建：每段 split_paragraphs → 首个无标签块（段前导语句）归 SECTION 头单元，其余带标签块各成 paragraph 单元。
    section_order 保留不变（SECTION 级路径继续用它），proc_order 是其带体超集。"""
    proc_order: list[tuple] = []
    for s in program.sections:
        sec = s.name.upper()
        sec_body: list[str] = []
        para_units: list[tuple] = []
        for lbl, body in split_paragraphs(s.lines):
            if lbl is None:
                sec_body += body                       # 段前导无标签块 → 归 SECTION 头
            else:
                para_units.append((lbl.upper(), "paragraph", sec, body))
        proc_order.append((sec, "section", sec, sec_body))   # SECTION 头作该段第一个单元
        proc_order += para_units
    return proc_order


def build_body_ctx(program) -> tuple[_rules.Ctx, list[str]]:
    """CobolProgram → (rules.Ctx, ws_field_names)。ws_field_names 仅含 WORKING-STORAGE 字段（用于 wsaa. 前缀）。"""
    # field_type_map 用 WS+LINKAGE 全量（同 pipeline，供规则判型）；前缀集只取 WS（LINKAGE 是方法入参，裸名）
    field_type_map = build_field_type_map(resolve(program.working_storage + program.linkage_vars))
    ws_field_names = [f.java_name for f in resolve(program.working_storage)]
    state = {
        "copy_refs": list(program.copy_refs),
        "linkage_using": list(program.linkage_using),
        "sections_meta": [{"name": s.name, "lines": s.lines, "calls": s.calls} for s in program.sections],
    }
    reg = build_struct_registry(state)
    io = _load_io_maps()
    ctx = _rules.Ctx(
        field_type_map=field_type_map,
        section_to_method=_section_to_method,
        known_sections={s.name.upper() for s in program.sections},
        section_order=[s.name.upper() for s in program.sections],
        proc_order=_build_proc_order(program),   # 步骤13 §2.1：paragraph 级 THRU 区间解析的数据基座
        io_struct_prefixes=reg["prefixes"], struct_objects=reg["objects"],
        struct_classes=reg["classes"], struct_getter=reg["getter"],
        struct_setter=reg["setter"], struct_default_suffix=reg["default_suffix"],
        io_programs=io["io_programs"], date_programs=io["date_programs"],
        system_programs=io["system_programs"], io_default_pattern=io["io_default_pattern"],
    )
    return ctx, ws_field_names


def reset_section(ctx: _rules.Ctx) -> None:
    """重置段级状态，避免叶子编号/循环标签/结构体功能码跨段串号。"""
    ctx.leaves = []
    ctx._counter = [0]
    ctx.flow_label = None
    ctx.flow_paragraphs = set()
    ctx.struct_function = {}


def _postprocess_body(body: str, ws_field_names: list[str], call_args: str,
                      known_methods: set[str]) -> str:
    """主线瘦后处理（步骤07 决策 A=方案B / B=B1）：数组下标 + this.X() 补实参 + wsaa. 前缀。"""
    body = fix_array_subscripts(body)
    # B1：指向本类 SECTION 方法的无参 this.X() → this.X(wsaa, <using…>)
    if call_args:
        def _route(m: "re.Match") -> str:
            return f"this.{m.group(1)}({call_args});" if m.group(1) in known_methods else m.group(0)
        body = re.sub(r"\bthis\.(\w+)\(\)\s*;", _route, body)
    # 方案B：WORKING-STORAGE 字段加 wsaa. 前缀（字符串字面量外）
    if ws_field_names:
        alt = "|".join(re.escape(n) for n in sorted(set(ws_field_names), key=len, reverse=True))
        field_re = re.compile(rf"(?<![.\w])({alt})\b")
        body = _prefix_fields_outside_strings(body, field_re, prefix="wsaa.")
    return body


def _translate_paragraphs_body_legacy(paras_raw: list, ctx: _rules.Ctx, ws_field_names: list[str],
                                      call_args: str, known_methods: set[str], force_sm: bool = False) -> str:
    """已切好的 [(label, body_lines), …] → Java 方法体（确定性，无 LLM）。
    步骤14 §2.1：合成区间方法走此入口，**不经 split_paragraphs 的有损往返**，标签直传，
    让 build_section 重见区间内 paragraph 边界、按状态机精确路由区间内 GO TO。
    force_sm（D14-3=a）：合成区间方法置 True，区间内前向 GO TO 亦建状态机精确跳转。
    （translate_section_body 先 split 再委托本函数，二者共用同一翻译核，零重复。）"""
    reset_section(ctx)
    try:
        paras = [(lbl, segment(b)) for lbl, b in paras_raw]
        body = "\n".join(_rules.build_section(paras, ctx, force_sm=force_sm))
    except Exception as e:
        commented = "\n".join(f"// {ln}" for _lbl, b in paras_raw for ln in b)
        return f"// TODO 段翻译失败（{e}）；原 COBOL：\n{commented}"
    for lid, leaf in ctx.leaves:
        lines, matched = _rules.translate_leaf(leaf, ctx)
        raw = (leaf.raw or " ".join(leaf.tokens)).strip()
        fill = "\n".join(lines) if matched else f"// TODO 叶子待译: {raw}"
        body = body.replace(f"/*__LEAF_{lid}__*/", fill)
    body = re.sub(r"/\*__LEAF_\d+__\*/", "// TODO: 未翻译叶子", body)   # 防御
    # 步骤13 §2.3 缺口2：本段翻译中 _perform_range 可能已登记合成区间方法名，并入 known_methods，
    # 则 B1 自动把段内 this.aThruB(); 补成 this.aThruB(wsaa, using…);（无需 _perform_range 感知 call_args）。
    methods = set(known_methods) | set(ctx.pending_range_methods)
    return _postprocess_body(body, ws_field_names, call_args, methods)


def _translate_paragraphs_body_legacy_fallback(paras_raw: list, ctx: _rules.Ctx, ws_field_names: list[str],
                                               call_args: str, known_methods: set[str],
                                               force_sm: bool = False) -> str:
    """Legacy SECTION renderer retained only for ASG failure fallback and diff/reference tests."""
    return _translate_paragraphs_body_legacy(paras_raw, ctx, ws_field_names, call_args, known_methods, force_sm)


def _translate_paragraphs_body_asg(paras_raw: list, ctx: _rules.Ctx, ws_field_names: list[str],
                                   call_args: str, known_methods: set[str], force_sm: bool = False) -> str:
    from asg import SectionJavaVisitor, build_asg_paragraphs

    reset_section(ctx)
    paragraphs = build_asg_paragraphs(paras_raw, ctx)
    body = "\n".join(SectionJavaVisitor(ctx, force_sm=force_sm).render_paragraphs(paragraphs))
    methods = set(known_methods) | set(ctx.pending_range_methods)
    return _postprocess_body(body, ws_field_names, call_args, methods)


def _record_asg_fallback(ctx: _rules.Ctx, exc: Exception, paras_raw: list, force_sm: bool) -> None:
    labels = [lbl for lbl, _body in paras_raw if lbl is not None]
    ctx.asg_fallback_events.append({
        "exception_type": type(exc).__name__,
        "message": str(exc),
        "paragraph_labels": labels,
        "force_sm": force_sm,
    })


def asg_fallback_summary(ctx: _rules.Ctx) -> dict:
    events = list(getattr(ctx, "asg_fallback_events", []))
    return {"count": len(events), "events": events}


def translate_paragraphs_body(paras_raw: list, ctx: _rules.Ctx, ws_field_names: list[str],
                              call_args: str, known_methods: set[str], force_sm: bool = False) -> str:
    """Pre-split paragraphs -> Java body. Mainline now uses ASG SectionJavaVisitor, with legacy fallback."""
    try:
        return _translate_paragraphs_body_asg(paras_raw, ctx, ws_field_names, call_args, known_methods, force_sm)
    except Exception as exc:
        _record_asg_fallback(ctx, exc, paras_raw, force_sm)
        return _translate_paragraphs_body_legacy_fallback(
            paras_raw, ctx, ws_field_names, call_args, known_methods, force_sm
        )


def translate_section_body(body_lines: list[str], ctx: _rules.Ctx, ws_field_names: list[str],
                           call_args: str, known_methods: set[str]) -> str:
    """单个 SECTION 段体 → Java 方法体（确定性，无 LLM）。先 split_paragraphs 切段，
    再委托 translate_paragraphs_body（共用翻译核）。规则兜不住的叶子落 // TODO 叶子待译。"""
    return translate_paragraphs_body(split_paragraphs(body_lines), ctx, ws_field_names, call_args, known_methods)


def render_pending_range_methods(ctx: _rules.Ctx, ws_field_names: list[str],
                                 call_args: str, known_methods: set[str]) -> dict[str, str]:
    """drain ctx.pending_range_methods，逐条把**带标签单元序列** [(label, body), …] 经
    translate_paragraphs_body 翻成合成区间方法体（步骤14 §2.1：保标签让区间内 GO TO 走状态机；
    步骤13 §2.3 缺口3：编排下沉 body_context，避免 rules→body_context 成环）。
    返回 {合成方法名: Java 方法体}，供 render_skeleton 发射为类级方法。
    设计思路：合成体本身可能再含 PERFORM…THRU 登记新的嵌套区间方法，故按工作集循环至稳定。"""
    rendered: dict[str, str] = {}
    while True:
        todo = {n: paras for n, paras in ctx.pending_range_methods.items() if n not in rendered}
        if not todo:
            return rendered
        for name, paras_raw in todo.items():
            # force_sm=True：合成区间方法内前向 GO TO 亦走状态机精确跳转（D14-3=a，仅作用于区间方法）。
            rendered[name] = translate_paragraphs_body(paras_raw, ctx, ws_field_names, call_args,
                                                       known_methods, force_sm=True)
