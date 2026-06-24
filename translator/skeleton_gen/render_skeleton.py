"""
主类骨架装配（步骤05 §6.2 / §7〇 / §8）。

用途：把 SkeletonModel + CopyResolution 装配为主类 Java 源码：
      package + COPY 依赖（服务字段/实体引用注释）+ 入口方法（USING→入参）+
      每 SECTION 一个方法（带 wsaa 上下文参数、空体 + TODO + PERFORM→调用注释）。
对应设计：docs/详细设计/步骤05-cob到Java翻译引擎详细设计.md。

设计思路（§8 全局变量策略）：WS 容器**非 static、无单例**；入口方法内 new 一个实例，
      作为上下文对象在各 SECTION 方法间显式传参（方法签名带 wsaa）。本轮方法体留空（TODO 待译）。
"""
from __future__ import annotations

from config import spec_loader
from translator.skeleton_gen.program_model import build_model
from translator.skeleton_gen.copy_resolver import resolve
from translator.skeleton_gen.body_context import (
    build_body_ctx, translate_section_body, render_pending_range_methods,
)


def _using_params(model) -> list[tuple[str, str]]:
    """USING 名 → (Java 类型, 字段名)：type=class_name(名)、field=field_name(名)（§2-7）。"""
    return [(spec_loader.class_name(u), spec_loader.field_name(u)) for u in model.using]


def _sig(wsaa_class: str, using: list[tuple[str, str]]) -> str:
    """SECTION 方法签名参数串：wsaa 上下文 + USING 入参。"""
    return ", ".join([f"{wsaa_class} wsaa"] + [f"{t} {f}" for t, f in using])


def _args(using: list[tuple[str, str]]) -> str:
    """方法调用实参串：wsaa + USING 字段名。"""
    return ", ".join(["wsaa"] + [f for _, f in using])


def _header(model, res) -> list[str]:
    """package + 主类 doc 注释（含全局变量策略、实体引用、常量登记）。"""
    out = [f"package {model.package};", "", "/**",
           f" * COBOL 程序 {model.program_id} 主类骨架（确定性翻译，无 LLM）。",
           " * 由 scripts/translate_skeleton.py 生成，对应 docs/详细设计/步骤05-cob到Java翻译引擎详细设计.md。",
           f" * 全局变量策略：WORKING-STORAGE → {model.wsaa_class} 容器；非 static、无单例，",
           " *   每次调用 new 一个实例，作为上下文对象在各 SECTION 方法间显式传参（线程封闭）。"]
    if res.entities:
        out.append(" * 引用实体类（COPY 记录，本轮仅引用不生成实体本体）：")
        out += [f" *   {cob} → {cls}" for cob, cls in res.entities.items()]
    if res.constants:
        out.append(" * 常量拷贝簿（保持字面量，不建数据名）：" + ", ".join(res.constants))
    out.append(" */")
    return out


def _services_and_ctor(model, res) -> list[str]:
    """服务依赖 → final 字段 + 构造器（无 Spring 注解）；无服务则不生成构造器。"""
    if not res.services:
        return []
    out = ["", "    // ── 服务依赖（处理逻辑拷贝簿 → 服务类，构造器注入）──"]
    out += [f"    private final {cls} {fld};" for cls, fld in res.services]
    params = ", ".join(f"{cls} {fld}" for cls, fld in res.services)
    out += ["", f"    public {model.class_name}({params}) {{"]
    out += [f"        this.{fld} = {fld};" for _, fld in res.services]
    out += ["    }"]
    return out


def _entry(model, using) -> list[str]:
    """主入口 execute：USING→入参，方法内 new WS 容器（§8）。"""
    params = ", ".join(f"{t} {f}" for t, f in using)
    out = ["", "    /**",
           f"     * 主入口：对应 PROCEDURE DIVISION USING {' '.join(model.using)}。",
           "     */",
           f"    public void execute({params}) {{",
           f"        {model.wsaa_class} wsaa = new {model.wsaa_class}();"]
    if model.sections:
        first = model.sections[0]
        out.append(f"        // TODO 入口控制流待译：COBOL 主体从首个 SECTION 开始 "
                   f"→ {first.method}({_args(using)});")
    else:
        out.append("        // TODO 入口控制流待译")
    out.append("    }")
    return out


def _section_method(model, using, s, ctx, ws_field_names, known_methods) -> list[str]:
    """单个 SECTION → 方法签名（带 wsaa）+ 确定性翻译方法体（步骤07，接 rules 引擎，无 LLM）。"""
    out = ["", f"    void {s.method}({_sig(model.wsaa_class, using)}) {{",
           f"        // COBOL SECTION: {s.cobol_name} (行 {s.line_start}-{s.line_end})"]
    if s.go_tos:
        out.append("        // TODO-GOTO: 含 GO TO 语句，控制流需人工核对")
    body = translate_section_body(s.body_lines, ctx, ws_field_names, _args(using), known_methods)
    # 方法体缩进到方法内层（8 空格基准）
    out += [("        " + ln if ln.strip() else "") for ln in body.split("\n")]
    out.append("    }")
    return out


def _range_method(model, using, name, body) -> list[str]:
    """单个合成区间方法（步骤13 §2.3 路线b：PERFORM A THRU B 的 paragraph 区间）→ 方法签名 + 翻译体。
    签名与 SECTION 方法同款（带 wsaa + USING），故段内 this.aThruB(wsaa, using…) 调用可直达。"""
    out = ["", f"    void {name}({_sig(model.wsaa_class, using)}) {{",
           "        // 合成区间方法（步骤13 §2.3：PERFORM…THRU paragraph 区间，区间内各单元体按源序拼接翻译）"]
    out += [("        " + ln if ln.strip() else "") for ln in body.split("\n")]
    out.append("    }")
    return out


def render_skeleton(program) -> str:
    """CobolProgram → 主类骨架 Java 源码字符串（含确定性翻译的 SECTION 方法体，步骤07）。"""
    model = build_model(program)
    res = resolve(model.copies)
    using = _using_params(model)
    ctx, ws_field_names = build_body_ctx(program)        # 程序级算一次，各 SECTION 复用
    known_methods = {s.method for s in model.sections}   # 本类 SECTION 方法名集（B1 补实参用）
    lines = _header(model, res)
    lines += [f"public class {model.class_name} {{"]
    lines += _services_and_ctor(model, res)
    lines += _entry(model, using)
    seen: set[str] = set()                  # 方法名去重（§9.2/§9.4），避免重复 Java 方法
    for s in model.sections:
        if s.method in seen:
            # 同名 SECTION（多为 !!!!!! 停用/重定义的旧版本）：跳过，仅留注释（不臆测）
            lines += ["", f"    // 重复 SECTION 跳过（疑似停用/重定义）: {s.cobol_name} → {s.method}()"]
            continue
        seen.add(s.method)
        lines += _section_method(model, using, s, ctx, ws_field_names, known_methods)
    # 步骤13 §2.3 缺口2 step3：所有 SECTION 发射后，drain pending 区间方法、翻译并发射为类级合成方法。
    rendered = render_pending_range_methods(ctx, ws_field_names, _args(using), known_methods)
    for name, body in rendered.items():
        lines += _range_method(model, using, name, body)
    lines += ["}", ""]
    return "\n".join(lines)
