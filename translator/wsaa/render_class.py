"""
WsNode 森林 → 完整 Java 类（确定性组装）。

对应设计：docs/详细设计/步骤03-WSAA块翻译设计.md。

设计思路：深度遍历森林，按祖先 OCCURS 累计数组维度；叶子→字段（render_field），
重叠组/REDEFINES→视图（render_view），88→布尔方法（render_condition）。重名字段去重
留注释；畸形层级（带 PIC 又带子项）尽力平铺并标 TODO。最后拼 package/imports/类体。
"""
from __future__ import annotations

from config import spec_loader
from parser.ws.model import WsNode
from translator.wsaa.render_field import java_name, render_field
from translator.wsaa.render_condition import render_conditions
from translator.wsaa import render_view as _view
from translator.wsaa import storage as _storage


def _index_and_groups(roots: list[WsNode]):
    """构建 名→节点 索引、可视图组 java 名集合、被数组化的 cob 名集合。

    arrayed：自身或任一祖先带 OCCURS（其 Java 字段是数组）。视图（定宽切片）只对
    非数组的标量/组成立，数组上下文的重叠/REDEFINES 退化为 TODO，避免生成非法 Java。
    """
    name_index: dict[str, WsNode] = {}
    view_groups: set[str] = set()
    arrayed: set[str] = set()

    def walk(n: WsNode, in_array: bool):
        if not n.is_filler:
            name_index.setdefault(n.name.upper(), n)
            if in_array:
                arrayed.add(n.name.upper())
        if not in_array and not n.occurs and _view.can_group_view(n):
            view_groups.add(java_name(n.name))
        child_in_array = in_array or bool(n.occurs)
        for c in n.children:
            walk(c, child_in_array)

    for r in roots:
        walk(r, False)
    return name_index, view_groups, arrayed


class _Acc:
    def __init__(self):
        self.fields: list[str] = []
        self.views: list[str] = []
        self.conds: list[str] = []
        self.seen: set[str] = set()


def _handle(node: WsNode, dims: list[int], acc: _Acc, idx: dict, vg: set, arr: set):
    if node.conditions:
        indexed = bool(dims) or bool(node.occurs)
        acc.conds.extend(render_conditions(node, indexed))
    if node.redefines:
        # 目标被停用/不在块内：alias 是唯一存活定义，按主定义渲染并入 fields（D12）
        if node.redefines.upper() not in idx:
            acc.fields.extend(_view.render_primary(node))
        else:
            acc.views.extend(_view.render_redefines(node, idx, vg, arr))
        return
    if node.is_group:
        if node.children:
            acc.fields.append(f"\n    // ── {node.level:02d} {node.name} ──")
        if not dims and not node.occurs and java_name(node.name) in vg:
            acc.views.extend(_view.render_group_view(node))
        newdims = dims + ([node.occurs] if node.occurs else [])
        for c in node.children:
            _handle(c, newdims, acc, idx, vg, arr)
        return
    # 叶子
    mydims = dims + ([node.occurs] if node.occurs else [])
    if not node.is_filler:
        jn = java_name(node.name)
        if jn in acc.seen:
            acc.fields.append(f"    // 重复名跳过: {node.name}")
        else:
            acc.seen.add(jn)
            acc.fields.extend(render_field(node, mydims))
    if node.children:                       # 畸形：带 PIC 又带子项
        acc.fields.append(f"    // TODO 畸形层级: {node.name} 同时带 PIC 与子项，下列子项尽力平铺")
        for c in node.children:
            _handle(c, mydims, acc, idx, vg, arr)


def render_wsaa(roots: list[WsNode], program: str) -> str:
    """森林 → Java 源码字符串。"""
    base = spec_loader.class_name(program)  # ZPOLDWNM → Zpoldwnm（经规范访问层）
    class_name = f"{base}Wsaa"             # 协作规范：{PROGRAM}WSAA
    package = program.lower()
    idx, vg, arr = _index_and_groups(roots)

    acc = _Acc()
    for r in roots:
        _handle(r, [], acc, idx, vg, arr)

    out: list[str] = [
        f"package {package};", "",
        "import java.math.BigDecimal;", "",
        f"/**",
        f" * COBOL 程序 {program} 的 WORKING-STORAGE 全局变量（确定性翻译，无 LLM）。",
        f" * 由 scripts/translate_wsaa.py 生成，对应 docs/详细设计/步骤03-WSAA块翻译设计.md。",
        f" * 下标说明：COBOL OCCURS 从 1 开始，Java 数组从 0 开始，访问时用 idx-1。",
        f" */",
        f"public class {class_name} {{",
    ]
    out.extend(acc.fields)
    if acc.views:
        out += ["", "    // ── 重叠组 / REDEFINES 派生视图（双向同步）──"]
        out += acc.views
        out += [""] + _view.PAD_HELPER
        # 仅当用到数值定宽串视图时输出 _toDigits/_fromDigits（避免无用私有方法）
        if any("_toDigits" in ln or "_fromDigits" in ln for ln in acc.views):
            out += _storage.NUM_HELPER
    if acc.conds:
        out += ["", "    // ── 88 条件 → 布尔方法 ──"]
        out += acc.conds
    out += ["}", ""]
    return "\n".join(out)
