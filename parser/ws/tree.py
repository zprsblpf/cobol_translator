"""
按层级号建 WORKING-STORAGE 树 + 回填类型/宽度。

对应设计：docs/详细设计/步骤03-WSAA块翻译设计.md。

设计思路：
- build_tree(): 用栈按 level 建父子关系；88 行解析为 Condition 挂到前一兄弟数据项；
- backfill(): 自底向上算 java_type / is_edited / byte_len（组长度 = 子项跨度之和，
  子项跨度 = 单次宽度 × OCCURS）。byte_len 供重叠组 / REDEFINES 派生视图定宽切片。
"""
from __future__ import annotations

from config.yaml_cache import load as _load_yaml   # 唯一 YAML 加载入口（步骤09）
from parser.ws.model import WsNode
from parser.ws import entry as _entry
from parser.ws import conditions as _cond
from parser.ws import pic as _pic


def _type_rules() -> list[dict]:
    return _load_yaml("type_mappings.yaml").get("pic_rules", [])


def build_tree(entries: list[str]) -> list[WsNode]:
    """合并后的定义行列表 → WsNode 森林（01 级为根）。"""
    roots: list[WsNode] = []
    stack: list[WsNode] = []
    last_data: WsNode | None = None
    for e in entries:
        if _cond.is_condition(e):
            if last_data is not None:
                last_data.conditions.append(_cond.parse_condition(e))
            continue
        node = _entry.parse_entry(e)
        if node is None:
            continue
        while stack and stack[-1].level >= node.level:
            stack.pop()
        (stack[-1].children if stack else roots).append(node)
        stack.append(node)
        last_data = node
    return roots


def _span(node: WsNode) -> int:
    """节点占位跨度 = 单次宽度 × OCCURS。"""
    return node.byte_len * (node.occurs or 1)


def backfill(node: WsNode, rules: list[dict]) -> None:
    """递归回填 java_type / is_edited / byte_len。"""
    if node.is_group:
        for c in node.children:
            backfill(c, rules)
        node.byte_len = sum(_span(c) for c in node.children)
    else:
        node.java_type, node.is_edited = _pic.java_type(node.pic, node.comp, rules)
        node.byte_len = _pic.char_width(node.pic, node.comp)
        for c in node.children:          # 畸形：叶子（带 PIC）下仍挂了子项，一并回填
            backfill(c, rules)


def build(entries: list[str]) -> list[WsNode]:
    """构树 + 回填，对外统一入口。"""
    rules = _type_rules()
    roots = build_tree(entries)
    for r in roots:
        backfill(r, rules)
    return roots
