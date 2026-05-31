"""
重叠组 / REDEFINES → 派生视图方法（普通字段 + 视图，保证双向同步）。

对应设计：docs/详细设计/步骤03-WSAA块翻译设计.md。

设计思路（用户决定：普通字段 + REDEFINES 派生视图方法）：
- 叶子字段为 backing（真实存储）；
- 「重叠组」（子项即父缓冲分段，全为字符型、无 OCCURS）→ 生成 getX()/setX(String)
  按定宽拼接 / 切分，改子↔改父双向同步；
- 「REDEFINES」→ 别名字段不单独存储，而是对被重定义目标的字符视图做切片 get/set；
  目标非字符型 / 含 OCCURS / 不在本块（copybook）→ 退化为普通字段 + TODO（如实标注）。
"""
from __future__ import annotations

from parser.ws.model import WsNode
from translator.wsaa.render_field import java_name, render_field

PAD_HELPER = [
    "    /** 定宽右填充空格（视图切片用）：截断或补足到 n 字符。 */",
    "    private static String _pad(String s, int n) {",
    "        if (s == null) s = \"\";",
    "        if (s.length() >= n) return s.substring(0, n);",
    "        StringBuilder b = new StringBuilder(s);",
    "        while (b.length() < n) b.append(' ');",
    "        return b.toString();",
    "    }",
]


def _pascal(jn: str) -> str:
    return jn[0].upper() + jn[1:] if jn else jn


def can_group_view(node: WsNode) -> bool:
    """重叠组视图资格：组、非 REDEFINES、子项全为字符型标量、无 OCCURS。"""
    if not node.is_group or node.redefines or not node.children:
        return False
    for c in node.children:
        if c.is_group or c.occurs or c.byte_len <= 0:
            return False
        if not c.is_filler and c.java_type != "String":
            return False
    return True


def render_group_view(node: WsNode) -> list[str]:
    """组 → getX()/setX(String) 定宽拼接/切分视图。"""
    gn = java_name(node.name)
    p = _pascal(gn)
    get_terms, set_lines, off = [], [], 0
    for ch in node.children:
        w = ch.byte_len
        if ch.is_filler:
            get_terms.append(f'_pad("", {w})')
        else:
            cn = java_name(ch.name)
            get_terms.append(f"_pad({cn}, {w})")
            set_lines.append(f"        {cn} = v.substring({off}, {off + w});")
        off += w
    lines = [f"    public String get{p}() {{ return {' + '.join(get_terms)}; }}",
             f"    public void set{p}(String v) {{",
             f"        v = _pad(v, {node.byte_len});"]
    lines.extend(set_lines)
    lines.append("    }")
    return lines


def _string_accessor(tnode: WsNode, view_groups: set[str]):
    """目标 → (读表达式, 写模板含{v}, 总宽)；不可用返回 None。"""
    tn = java_name(tnode.name)
    if tnode.is_group:
        if tn in view_groups:
            p = _pascal(tn)
            return f"get{p}()", f"set{p}({{v}});", tnode.byte_len
        return None
    if tnode.java_type == "String":
        return tn, f"{tn} = {{v}};", tnode.byte_len
    return None


def _todo_plain(node: WsNode, msg: str) -> list[str]:
    """退化：普通字段（非真正别名）+ TODO 标注。"""
    out = [f"    // TODO {msg}"]
    if node.is_group and node.children:
        for ch in node.children:
            if ch.is_filler:
                continue
            if ch.is_group:
                for g in ch.children:
                    if not g.is_filler:
                        out += render_field(g, [ch.occurs, g.occurs] if g.occurs else
                                            ([ch.occurs] if ch.occurs else []))
            else:
                out += render_field(ch, [ch.occurs] if ch.occurs else [])
    else:
        out += render_field(node, [])
    return out


def render_redefines(node: WsNode, name_index: dict, view_groups: set[str],
                     arrayed: set[str]) -> list[str]:
    """REDEFINES 节点 → 视图方法或退化普通字段。"""
    tnode = name_index.get(node.redefines.upper())
    if tnode is None:
        return _todo_plain(node, f"REDEFINES 目标 {node.redefines} 未在本块定义（可能在 copybook）")
    if node.redefines.upper() in arrayed or node.name.upper() in arrayed:
        return _todo_plain(node, f"REDEFINES {node.redefines}: 处于 OCCURS 数组上下文，"
                                 f"定宽视图不适用，需人工核对")
    acc = _string_accessor(tnode, view_groups)
    if acc is None:
        return _todo_plain(node, f"REDEFINES {node.redefines}: 目标非字符型/无视图，需人工核对")
    getexpr, setfmt, W = acc
    out = [f"    // ── REDEFINES {node.name} → 视图 over {node.redefines} ──"]

    def slice_view(ch: WsNode, off: int, w: int) -> list[str]:
        p = _pascal(java_name(ch.name))
        getter = (f"    public String get{p}() {{ "
                  f"return _pad({getexpr}, {W}).substring({off}, {off + w}); }}")
        rebuilt = f"_s.substring(0,{off})+_pad(v,{w})+_s.substring({off + w})"
        setter = (f"    public void set{p}(String v) {{ String _s = _pad({getexpr}, {W}); "
                  f"{setfmt.format(v=rebuilt)} }}")
        return [getter, setter]

    if node.is_group:
        off = 0
        for ch in node.children:
            w = ch.byte_len
            if ch.is_filler:
                off += w
                continue
            if ch.is_group or ch.occurs:
                out.append(f"    // TODO REDEFINES 子项 {ch.name} 含组/OCCURS，需人工核对")
                off += w
                continue
            out += slice_view(ch, off, w)
            off += w
    else:
        out += slice_view(node, 0, node.byte_len or W)
    return out
