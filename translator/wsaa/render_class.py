"""
WsNode 森林 → 完整 Java 类（确定性组装）。

对应设计：docs/详细设计/步骤03-WSAA块翻译设计.md。

设计思路：深度遍历森林，按祖先 OCCURS 累计数组维度；叶子→字段（render_field），
重叠组/REDEFINES→视图（render_view），88→布尔方法（render_condition）。重名字段消歧
（步骤12 §4：父组名前缀改名保留 + TODO，不再静默丢）；畸形层级（带 PIC 又带子项）尽力平铺并标 TODO。
最后拼 package/imports/类体。
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


def _disambiguate(jn: str, parent_jn: str, seen: set[str]) -> str:
    """命名碰撞消歧（步骤12 §4，N-1①）：优先用父组名作前缀（parentJn + Pascal(jn)），
    仍冲突则追加序号兜底，保证全局唯一。无父组名时退化 jn_2/jn_3…。"""
    cand = (parent_jn + jn[0].upper() + jn[1:]) if parent_jn else f"{jn}_2"
    i = 2
    while cand in seen:
        cand = f"{jn}_{i}"
        i += 1
    return cand


def _handle(node: WsNode, dims: list[int], acc: _Acc, idx: dict, vg: set, arr: set,
            parent_jn: str = ""):
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
        child_parent = parent_jn if node.is_filler else java_name(node.name)
        for c in node.children:
            _handle(c, newdims, acc, idx, vg, arr, child_parent)
        return
    # 叶子
    mydims = dims + ([node.occurs] if node.occurs else [])
    if not node.is_filler:
        jn = java_name(node.name)
        if jn in acc.seen:
            # 命名碰撞（步骤12 §4）：不再静默丢字段，改名保留 + 标 TODO，引用处人工核对
            dis = _disambiguate(jn, parent_jn, acc.seen)
            acc.fields.append(
                f"    // TODO 命名碰撞: {node.name} 的 Java 名 {jn} 已被占用 → 改名 {dis}"
                f"（步骤12 §4 N-1①）；若与同名字段实为不同项，引用处需按 COBOL OF/IN 限定人工核对")
            acc.seen.add(dis)
            acc.fields.extend(render_field(node, mydims, name_override=dis))
        else:
            acc.seen.add(jn)
            acc.fields.extend(render_field(node, mydims))
    if node.children:                       # 畸形：带 PIC 又带子项
        acc.fields.append(f"    // TODO 畸形层级: {node.name} 同时带 PIC 与子项，下列子项尽力平铺")
        child_parent = parent_jn if node.is_filler else java_name(node.name)
        for c in node.children:
            _handle(c, mydims, acc, idx, vg, arr, child_parent)


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
        f" * 假设（步骤12 §3）：本类每次调用 new 一个实例，不保留 WORKING-STORAGE 的跨 CALL 持久值。",
        f" *   若原程序依赖「首次调用初始化、后续复用」之类持久语义，此处需人工改为容器复用/外部持久化。",
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
