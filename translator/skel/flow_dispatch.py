"""
相3 骨架装配公用底座 —— 段内 GO TO dispatch 状态机降级（回跳 → FLOW/__pc/continue FLOW）。

来源：原 translator/rules.py `build_section` 的**状态机部分**（label 规范化 + 跳转探测 +
      扁平拼接 / FLOW while-switch 降级 + flow_label/flow_paragraphs 副作用）**原样迁址**，
      与 `_sk_control` 的 GO/EXIT dispatch 两行（→ dispatch_goto / dispatch_exit）。逻辑零改。
      `_rewrite_begn_loops`（BEGN for-each 改写）属步骤24C，**不**迁，仍留旧 build_section（设计 §3.2）。
对应设计：docs/详细设计/步骤24B-绞杀项4骨架装配②GOTO-dispatch状态机迁visitor设计.md §4.2 / §3.3 / §3.4。
设计思路：段级装配的输入是**结构化 paragraph**，旧路 Stmt 与新路 ASG 节点类型异构，无法纯 token 共用
      （对比 24A 裸 token）。故装配逻辑路径中立单份，把节点相关动作外包三回调
      （render_body / collect_gotos / ends_transfer），两路各传自有遍历器 → 壳 + flow 副作用逐字符一致。
      **关键时序**：必须先设 ctx.flow_label/flow_paragraphs 再调 render_body——段体内 GO TO 经
      dispatch_goto 读这两字段，故 render_body 必为回调（不可预渲染）。

用法示例：
    from translator.skel import render_flow_dispatch, dispatch_goto, dispatch_exit
    lines = render_flow_dispatch(paras, ctx, indent,
                                 render_body=lambda s, i: build_skeleton(s, ctx, i),
                                 collect_gotos=_collect_gotos, ends_transfer=_ends_with_transfer)
"""
from __future__ import annotations

from config import grammar_loader                 # 控制流降级策略正本（步骤08）
from translator.skel.context import SkelCtx


def _ind(n: int) -> str:
    return "    " * n


def render_flow_dispatch(paras: list, ctx: SkelCtx, indent: int, *,
                         render_body, collect_gotos, ends_transfer,
                         force_sm: bool = False) -> list[str]:
    """段内控制流降级（= 旧 rules.build_section 的状态机部分，零改；begn 改写除外，留旧 build_section）。

    paras = [(label_or_None, stmts_opaque), …]；stmts 仅经三回调消费，本函不识其类型（路径中立）。
    - 无内部跳转、或正本关状态机降级 → 扁平拼接各 paragraph 骨架（前向 GO TO→EXIT/return，行为不变）。
    - 存在回跳（target paragraph 索引 ≤ 当前）或 force_sm 下任一指向内部标签的 GO TO（含前向）
      → 带标签 while(true)+switch 状态机降级，并设 ctx.flow_label="FLOW"/flow_paragraphs=labels（收尾复位）。
    回调：render_body(stmts, indent)→Java 行；collect_gotos(stmts)→GO TO 目标(大写)；
          ends_transfer(stmts)→末尾是否无条件跳转（决定是否补 fall-through）。"""
    # 首段若无标签，赋合成入口名
    norm: list[tuple] = [
        (lbl or f"__ENTRY_{i}", stmts) for i, (lbl, stmts) in enumerate(paras)
    ]
    labels = [l for l, _ in norm]
    label_index = {l: i for i, l in enumerate(labels)}

    # 触发状态机的「区间内跳转」：默认仅回跳（j<=i）；force_sm 下任一指向内部标签的 GO TO（含前向）。
    has_jump = False
    for i, (_lbl, stmts) in enumerate(norm):
        for tgt in collect_gotos(stmts):
            j = label_index.get(tgt)
            if j is not None and (force_sm or j <= i):
                has_jump = True
                break
        if has_jump:
            break

    # 控制流降级策略取自正本：无内部跳转、或正本关闭状态机降级 → 扁平拼接（默认开，行为不变）
    if not has_jump or not grammar_loader.back_edge_state_machine():
        ctx.flow_label = None
        ctx.flow_paragraphs = set()
        out: list[str] = []
        for lbl, stmts in norm:
            if not lbl.startswith("__ENTRY_"):
                out.append(f"{_ind(indent)}// paragraph {lbl}")
            out.extend(render_body(stmts, indent))
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
        out.extend(render_body(stmts, indent + 2))
        if not ends_transfer(stmts):
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


def dispatch_goto(target_upper, ctx: SkelCtx, indent: int) -> list[str] | None:
    """状态机内 GO TO 目标命中段内标签 → __pc 路由行（= 旧 _sk_control GO 分支，零改）；否则 None。"""
    if target_upper and ctx.flow_label and target_upper in ctx.flow_paragraphs:
        return [f'{_ind(indent)}__pc = "{target_upper}"; continue {ctx.flow_label};  // GO TO {target_upper}']
    return None


def dispatch_exit(tokens: list, ctx: SkelCtx, indent: int) -> list[str] | None:
    """状态机内 EXIT → break FLOW（= 旧 _sk_control EXIT 分支，零改）；非 EXIT/非状态机态 → None。"""
    first = tokens[0].upper() if tokens else ""
    if first == "EXIT" and ctx.flow_label:
        return [f"{_ind(indent)}break {ctx.flow_label};  // EXIT"]
    return None
