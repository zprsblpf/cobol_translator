"""
相3 骨架装配公用底座 —— out-of-line PERFORM 的调用体生成（含 THRU 合成区间 + proc_order 路由）。

来源：原 translator/rules.py `_perform_range` / `_perform_single_paragraph` /
      `_perform_range_paragraph` / `_proc_call` **原样迁址**（逻辑零改，仅 ctx 注解 rules.Ctx → SkelCtx）。
对应设计：docs/详细设计/步骤24A-绞杀项4骨架装配①out-of-line-PERFORM迁visitor设计.md §4.3。
设计思路：旧 rules._sk_perform 的 target 分支与相3 asg.visitor.visit_PerformStmt 的 out-of-line 分支
      共调本模块 render_perform_call（同 header token + 同 ctx）→ 调用体行 + pending_range_methods
      登记副作用逐字符/逐项一致（绞杀项4① 比对闸基础）。token-based、不走 ASG 已解析 ref（设计 §3.3）。

用法示例：
    from translator.skel.perform_call import render_perform_call
    lines = render_perform_call(header, hu, target, ctx, indent)
"""
from __future__ import annotations

from config import spec_loader                   # 命名正本（步骤13 §2.4：合成区间方法名）
from translator.skel.context import SkelCtx


def _ind(n: int) -> str:
    return "    " * n


def _proc_call(target: str, ctx: SkelCtx) -> str:
    method = ctx.section_to_method(target)
    return f"this.{method}();"


def _perform_single_paragraph(target: str, ctx: SkelCtx, indent: int) -> list[str]:
    """单条 PERFORM <target>（无 THRU、无循环）的落地（步骤15 C-3）：
    - target 是已知 SECTION → 维持 this.<sec>()（真实方法已在，零回归）。
    - target 是 paragraph（proc_order 中恰一次、kind=paragraph，且合成名不与已有 SECTION 方法撞名）
      → 登记单单元 pending 方法 [(target, 该单元体)]、返回 this.pXxx()（渲染期补出方法定义，B1 补实参）。
    - 兜不住（不在 proc_order / 重名 / 撞 SECTION 方法名，D15-2 保守）→ this.pXxx() + 前置可见 TODO，不臆造。"""
    call = _ind(indent) + _proc_call(target, ctx)
    if target in ctx.known_sections:
        return [call]
    order = getattr(ctx, "proc_order", None) or []
    units = [u for u in order if u[0] == target and u[1] == "paragraph"]
    mname = ctx.section_to_method(target)
    section_methods = {ctx.section_to_method(s) for s in ctx.known_sections}
    if len(units) == 1 and mname not in section_methods:
        if mname not in ctx.pending_range_methods:          # 幂等：同段多次 PERFORM 只合成一次
            ctx.pending_range_methods[mname] = [(target, units[0][3])]
        return [call]
    return [f"{_ind(indent)}// TODO 单条 PERFORM {target}：未解析到唯一过程单元（不在 proc_order/重名/撞 SECTION 方法名），"
            f"调用目标可能不存在，需人工核对（步骤15 §2.1 兜不住保守，不臆造）", call]


def render_perform_call(header: list, hu: list, target: str, ctx: SkelCtx, indent: int) -> list[str]:
    """out-of-line PERFORM 的调用体（= 旧 rules._perform_range，零改；实现跟随正本
    config/specs/skeleton_spec.yaml block_grammar.perform.thru；步骤12 §2）：
    - 无 THRU/THROUGH → 单调用 pA();（历史行为）。
    - PERFORM A THRU B：A、B 均为已知 SECTION 且 B 在 A 之后 → 按全程序段顺序展开区间内每段调用
      （COBOL THRU = 顺序执行 A..B 之间所有段；A==B 退化为单调用），不丢中间段。
    - 端点非已知 SECTION / 区间无法确定（B 在 A 之前等）→ 单调用 pA() + 可见 TODO，退化人工核对（P-1③），不臆测。
    """
    ti = next((i for i, t in enumerate(hu) if t in ("THRU", "THROUGH")), -1)
    if ti < 0 or ti + 1 >= len(header):
        return _perform_single_paragraph(target, ctx, indent)   # 步骤15 C-3：单条 PERFORM 落地
    a, b = target, header[ti + 1].upper()
    # ① SECTION 级（步骤12 §2，零回归）：A、B 均为已知 SECTION 且 B 在后 → 按段顺序展开每段调用。
    order = ctx.section_order
    if a in order and b in order and order.index(b) >= order.index(a):
        rng = order[order.index(a): order.index(b) + 1]
        if len(rng) == 1:
            return [_ind(indent) + _proc_call(a, ctx)]
        out = [f"{_ind(indent)}// PERFORM {a} THRU {b}（步骤12 §2：THRU 跨段，按段顺序展开 {len(rng)} 段）"]
        out += [_ind(indent) + _proc_call(s, ctx) for s in rng]
        return out
    # ② paragraph 级（步骤13 §2.2/§2.3 路线b）：端点为 paragraph 时在 proc_order 解析区间、合成区间方法。
    pr = _perform_range_paragraph(a, b, ctx, indent)
    if pr is not None:
        return pr
    # ③ 端点缺失/重名/区间无法确定（D3 保守）→ 退化 pA() + 可见 TODO，不臆测中间段。
    return [f"{_ind(indent)}// TODO PERFORM {a} THRU {b}：THRU 端点非已知过程单元或区间无法确定，"
            f"中间段/B 段可能漏翻，需人工核对（步骤12 §2 P-1③ / 步骤13 §2.2）",
            _ind(indent) + _proc_call(a, ctx)]


def _perform_range_paragraph(a: str, b: str, ctx: SkelCtx, indent: int) -> list[str] | None:
    """paragraph 级 PERFORM A THRU B 区间解析（步骤13 §2.2/§2.3 路线b）。
    在全程序 proc_order 中保守解析 A..B 区间（含跨 SECTION，D2），命中则**登记**合成区间方法、
    返回单次 `this.aThruB();`（实参由 body_context._postprocess_body 的 B1 自动补齐，凭 known_methods）；
    无法保守解析（proc_order 缺/端点缺失/重名/B 在 A 之前/单单元 C-3）→ 返回 None，交回 render_perform_call 的 TODO 退化。
    设计思路：render_perform_call 在段翻译中途被调，当场无处发射类级方法，故只「登记」不「落地」，落地下沉 render_skeleton。"""
    order = ctx.proc_order
    if not order:
        return None
    names = [u[0] for u in order]
    # 保守 D3：两端点须在 proc_order 各恰出现一次（重名→不臆测边界），且 B 不在 A 之前。
    if names.count(a) != 1 or names.count(b) != 1:
        return None
    ia, ib = names.index(a), names.index(b)
    if ib <= ia:
        return None  # B 在 A 之前 / 单单元（含 C-3 单条 PERFORM paragraph，§5 范围外）→ 退化
    rng = order[ia: ib + 1]
    if any(not u[0] for u in rng):       # 区间夹无名/畸形单元 → 保守退化
        return None
    # 合成方法名走 config 正本（§2.4），端点方法名复用 section_to_method（对 paragraph 名同样适用）。
    mname = spec_loader.perform_range_method(ctx.section_to_method(a), ctx.section_to_method(b))
    if mname not in ctx.pending_range_methods:   # 同区间重复 PERFORM 只合成一次（幂等）
        # 步骤14 §2.1：存**带标签**的单元序列 [(label, body), …]（不再拼平丢标签），
        # 使合成区间方法翻译时 build_section 能重见区间内 paragraph 边界、按状态机路由区间内 GO TO。
        ctx.pending_range_methods[mname] = [(u[0], u[3]) for u in rng]
    return [f"{_ind(indent)}// PERFORM {a} THRU {b}（步骤13 §2.3 路线b：合成区间方法，{len(rng)} 单元）",
            f"{_ind(indent)}this.{mname}();"]
