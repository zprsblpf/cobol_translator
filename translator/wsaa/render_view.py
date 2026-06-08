"""
重叠组 / REDEFINES → 派生视图方法（普通字段 + 视图，保证双向同步）。

对应设计：docs/详细设计/步骤03-WSAA块翻译设计.md、步骤04-WSAA遗留补全设计.md。

设计思路（普通字段 + REDEFINES 派生视图方法，建在「定宽存储串」上，见 storage.py）：
- 叶子字段为 backing（真实存储）；视图无独立存储，get/set 均落到 backing → 天然同步。
- 「重叠组」（子项全字符、无 OCCURS）→ getX()/setX(String) 定宽拼接/切分（render_group_view）。
- 「REDEFINES」→ 对目标定宽存储串切片，按 alias 子项类型生成 get/set：
  字符子项→String 切片；数值子项→int/long/BigDecimal 解析回写；字符数组子项→带下标访问器；
  alias 自身为标量（如 9(03) over 组）→ 整段视图。
- 目标被停用 / 不在块内（拆解丢弃 !!!!!! 目标）→ render_primary 按 alias 自身 PIC 当主定义渲染。
- 数组上下文 / 目标含 OCCURS/编辑型/COMP-3 / 嵌套子组 → 退化 TODO（标明原因，不臆测）。
"""
from __future__ import annotations

from parser.ws.model import WsNode
from translator.wsaa.render_field import java_name, render_field
from translator.wsaa.storage import storage_accessor, scale_of, num_to_digits, num_from_digits

_NUMERIC = ("int", "long", "BigDecimal")

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


def _todo_plain(node: WsNode, msg: str) -> list[str]:
    """退化：普通字段（非真正别名）+ TODO 标注（数组上下文 / 不支持目标）。"""
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


def render_primary(node: WsNode) -> list[str]:
    """目标被停用/不在块内：alias 是该存储唯一存活定义，按其自身 PIC 当主定义渲染（D12）。"""
    out = [f"    // 原 REDEFINES 目标 {node.redefines} 已停用/不在块内，按主定义渲染（D12）"]
    if node.is_group and node.children:
        for ch in node.children:
            if not ch.is_filler:
                out += render_field(ch, [ch.occurs] if ch.occurs else [])
    else:
        out += render_field(node, [])
    return out


def _setter(p: str, vtype: str, read: str, W: int, rebuilt: str, wf) -> list[str]:
    """统一 setter 骨架：取目标存储串 _s → 重建 _n → 经 wf 写回 backing。"""
    return ([f"    public void set{p}({vtype} v) {{",
             f"        String _s = _pad({read}, {W});",
             f"        String _n = {rebuilt};"] + wf("_n") + ["    }"])


def _slice_view(ch: WsNode, off: int, w: int, read: str, wf, W: int) -> list[str]:
    """alias 标量子项（字符 / 数值）→ 按偏移 [off,off+w) 的 get/set 视图。"""
    p = _pascal(java_name(ch.name))
    seg = f"_pad({read}, {W}).substring({off}, {off + w})"
    if ch.java_type in _NUMERIC:
        sc = scale_of(ch.pic)
        getter = f"    public {ch.java_type} get{p}() {{ return {num_from_digits(seg, ch.java_type, sc)}; }}"
        vexpr, vtype = num_to_digits("v", ch.java_type, w, sc), ch.java_type
    else:
        getter = f"    public String get{p}() {{ return {seg}; }}"
        vexpr, vtype = f"_pad(v, {w})", "String"
    rebuilt = f"_s.substring(0, {off}) + {vexpr} + _s.substring({off + w})"
    return [getter] + _setter(p, vtype, read, W, rebuilt, wf)


def _array_view(ch: WsNode, off: int, w: int, read: str, wf, W: int) -> list[str]:
    """alias 字符数组子项（X(w) OCCURS n，对齐）→ 带下标 get(i)/set(i,String)（D9）。"""
    if ch.java_type != "String":
        return [f"    // TODO REDEFINES 子项 {ch.name} 为数值数组，需人工核对"]
    p = _pascal(java_name(ch.name))
    base = f"{off} + (i - 1) * {w}"
    getter = (f"    public String get{p}(int i) {{ "
              f"return _pad({read}, {W}).substring({base}, {base} + {w}); }}")
    rebuilt = f"_s.substring(0, {base}) + _pad(v, {w}) + _s.substring({base} + {w})"
    setter = ([f"    public void set{p}(int i, String v) {{",
               f"        String _s = _pad({read}, {W});",
               f"        String _n = {rebuilt};"] + wf("_n") + ["    }"])
    return [getter] + setter


def _scalar_view(node: WsNode, read: str, wf, W: int) -> list[str]:
    """alias 自身为标量（如 9(03) over 组）→ 整段 W 宽存储串视图。"""
    p = _pascal(java_name(node.name))
    if node.java_type in _NUMERIC:
        sc = scale_of(node.pic)
        getter = f"    public {node.java_type} get{p}() {{ return {num_from_digits(f'_pad({read}, {W})', node.java_type, sc)}; }}"
        setter = ([f"    public void set{p}({node.java_type} v) {{",
                   f"        String _n = {num_to_digits('v', node.java_type, W, sc)};"] + wf("_n") + ["    }"])
    else:
        getter = f"    public String get{p}() {{ return _pad({read}, {W}); }}"
        setter = [f"    public void set{p}(String v) {{", f"        String _n = _pad(v, {W});"] + wf("_n") + ["    }"]
    return [getter] + setter


def render_redefines(node: WsNode, name_index: dict, view_groups: set[str],
                     arrayed: set[str]) -> list[str]:
    """REDEFINES 节点 → 视图方法（或退化 TODO）。目标缺失由调用方走 render_primary。"""
    tnode = name_index.get(node.redefines.upper())
    if tnode is None:
        return render_primary(node)
    if node.redefines.upper() in arrayed or node.name.upper() in arrayed:
        return _todo_plain(node, f"REDEFINES {node.redefines}: 处于 OCCURS 数组上下文，"
                                 f"定宽视图不适用，需人工核对")
    acc = storage_accessor(tnode)
    if acc is None:
        return _todo_plain(node, f"REDEFINES {node.redefines}: 目标含 OCCURS/编辑型/COMP-3 "
                                 f"或嵌套组，定宽视图不适用，需人工核对")
    read, wf, W = acc
    out = [f"    // ── REDEFINES {node.name} → 视图 over {node.redefines}（双向同步；有符号数值末位 overpunch 保号，步骤12 §1）──"]
    if not node.is_group:
        return out + _scalar_view(node, read, wf, W)
    off = 0
    for ch in node.children:
        w = ch.byte_len
        if ch.is_filler:
            off += w
        elif ch.is_group:
            out.append(f"    // TODO REDEFINES 子项 {ch.name} 为嵌套组，需人工核对")
            off += w * (ch.occurs or 1)
        elif ch.occurs:
            out += _array_view(ch, off, w, read, wf, W)
            off += w * ch.occurs
        else:
            out += _slice_view(ch, off, w, read, wf, W)
            off += w
    return out
