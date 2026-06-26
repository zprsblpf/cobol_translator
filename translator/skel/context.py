"""
相3 骨架装配公用底座 —— SkelCtx 上下文契约（窄协议）。

对应设计：docs/详细设计/步骤24A-绞杀项4骨架装配①out-of-line-PERFORM迁visitor设计.md §3.4 / §4.2。
设计思路：骨架装配函数读取「过程拓扑 + 命名 + 可写的合成方法登记表」，这些是 skeleton 层状态，
LeafCtx 明令不纳（其 docstring）。故另声明 SkelCtx（Protocol）窄契约——rules.Ctx 与
body_context.build_body_ctx 产物（同为 rules.Ctx）均结构化（duck-type）满足之，
旧 rules / 相3 visitor 共用同一份骨架装配逻辑而无需共享整个 Ctx。
"""
from __future__ import annotations

from typing import Protocol


class SkelCtx(Protocol):
    """骨架装配函数读取的上下文契约（见 perform_call.py 的 ctx 取值）。"""
    proc_order: list              # [(name, kind, section, body_lines), …]（带段体，THRU 合成区间登记用）
    section_order: list           # 全程序 SECTION 名顺序（大写）——SECTION 级 THRU 展开用
    known_sections: set           # 所有 SECTION 名（大写）
    section_to_method: object     # callable: 段/paragraph 名 → java 方法名
    pending_range_methods: dict   # 可写：合成区间方法登记表 {方法名: [(label, body), …]}
    flow_label: object            # 可写 str|None：状态机循环标签（"FLOW" / None）——24B GO TO dispatch
    flow_paragraphs: object       # 可写 set：本 SECTION paragraph 标签集（大写）——dispatch 路由判定用
