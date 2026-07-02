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
_INDEX_NAMES = ("i", "j", "k", "m", "n")

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


def _todo_plain(node: WsNode, msg: str, array_dims: dict[str, list[int]] | None = None) -> list[str]:
    """退化：普通字段（非真正别名）+ TODO 标注（数组上下文 / 不支持目标）。"""
    out = [f"    // TODO {msg}"]
    if node.is_group and node.children:
        for ch in node.children:
            if ch.is_filler:
                continue
            dims = (array_dims or {}).get(ch.name.upper())
            if ch.is_group:
                for g in ch.children:
                    if not g.is_filler:
                        gdims = (array_dims or {}).get(g.name.upper())
                        out += render_field(g, gdims if gdims is not None else
                                            ([ch.occurs, g.occurs] if g.occurs else
                                             ([ch.occurs] if ch.occurs else [])))
            else:
                out += render_field(ch, dims if dims is not None else ([ch.occurs] if ch.occurs else []))
    else:
        out += render_field(node, (array_dims or {}).get(node.name.upper(), []))
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


def _index_names(count: int) -> list[str]:
    if count <= len(_INDEX_NAMES):
        return list(_INDEX_NAMES[:count])
    return [f"i{n + 1}" for n in range(count)]


def _index_params(names: list[str]) -> str:
    return ", ".join(f"int {n}" for n in names)


def _indexed_name(name: str, names: list[str]) -> str:
    return name + "".join(f"[{n} - 1]" for n in names)


def _array_storage_accessor(tnode: WsNode, dims: list[int], index_names: list[str]):
    """Array-context backing accessor for one OCCURS ancestor element."""
    if not dims:
        return None

    def idx(cobol_name: str) -> str:
        return _indexed_name(java_name(cobol_name), index_names)

    if tnode.is_group:
        terms, writes, off = [], [], 0
        for ch in tnode.children:
            w = ch.byte_len
            if w <= 0 or ch.occurs or ch.is_group or ch.is_edited or "COMP" in (ch.comp or "").upper():
                return None
            if ch.is_filler:
                terms.append(f'_pad("", {w})')
            elif ch.java_type == "String":
                cn = idx(ch.name)
                terms.append(f"_pad({cn}, {w})")
                writes.append((off, w, cn, "String", 0))
            elif ch.java_type in _NUMERIC:
                cn, sc = idx(ch.name), scale_of(ch.pic)
                terms.append(num_to_digits(cn, ch.java_type, w, sc))
                writes.append((off, w, cn, ch.java_type, sc))
            else:
                return None
            off += w

        def write_fn(v: str, _writes=writes) -> list[str]:
            out = []
            for o, w, cn, jt, sc in _writes:
                seg = f"{v}.substring({o}, {o + w})"
                rhs = seg if jt == "String" else num_from_digits(seg, jt, sc)
                out.append(f"        {cn} = {rhs};")
            return out

        return " + ".join(terms), write_fn, off

    if tnode.occurs or tnode.is_edited or "COMP" in (tnode.comp or "").upper() or tnode.byte_len <= 0:
        return None
    name, w = idx(tnode.name), tnode.byte_len
    if tnode.java_type == "String":
        return name, (lambda v: [f"        {name} = {v};"]), w
    if tnode.java_type in _NUMERIC:
        sc, jt = scale_of(tnode.pic), tnode.java_type
        read = num_to_digits(name, jt, w, sc)
        return read, (lambda v: [f"        {name} = {num_from_digits(v, jt, sc)};"]), w
    return None


def _indexed_slice_view(ch: WsNode, off: int, w: int, read: str, wf, W: int,
                        names: list[str]) -> list[str]:
    p = _pascal(java_name(ch.name))
    params = _index_params(names)
    seg = f"_pad({read}, {W}).substring({off}, {off + w})"
    if ch.java_type in _NUMERIC:
        sc = scale_of(ch.pic)
        getter = f"    public {ch.java_type} get{p}({params}) {{ return {num_from_digits(seg, ch.java_type, sc)}; }}"
        vexpr, vtype = num_to_digits("v", ch.java_type, w, sc), ch.java_type
    else:
        getter = f"    public String get{p}({params}) {{ return {seg}; }}"
        vexpr, vtype = f"_pad(v, {w})", "String"
    rebuilt = f"_s.substring(0, {off}) + {vexpr} + _s.substring({off + w})"
    setter_params = f"{params}, {vtype} v" if params else f"{vtype} v"
    return ([getter, f"    public void set{p}({setter_params}) {{",
             f"        String _s = _pad({read}, {W});",
             f"        String _n = {rebuilt};"] + wf("_n") + ["    }"])


def _indexed_array_view(ch: WsNode, off: int, w: int, read: str, wf, W: int,
                        names: list[str]) -> list[str]:
    if ch.java_type != "String":
        return [f"    // TODO REDEFINES 子项 {ch.name} 为数值数组，需人工核对"]
    local = _index_names(len(names) + 1)[-1]
    all_names = names + [local]
    p = _pascal(java_name(ch.name))
    params = _index_params(all_names)
    base = f"{off} + ({local} - 1) * {w}"
    getter = (f"    public String get{p}({params}) {{ "
              f"return _pad({read}, {W}).substring({base}, {base} + {w}); }}")
    rebuilt = f"_s.substring(0, {base}) + _pad(v, {w}) + _s.substring({base} + {w})"
    return ([getter, f"    public void set{p}({params}, String v) {{",
             f"        String _s = _pad({read}, {W});",
             f"        String _n = {rebuilt};"] + wf("_n") + ["    }"])


def _array_redefines_view(node: WsNode, tnode: WsNode, target_dims: list[int],
                          alias_dims: list[int]) -> list[str] | None:
    if target_dims != alias_dims:
        return None
    names = _index_names(len(target_dims))
    acc = _array_storage_accessor(tnode, target_dims, names)
    if acc is None:
        return None
    read, wf, W = acc
    out = [f"    // ── REDEFINES {node.name} → indexed view over {node.redefines}（OCCURS 元素内双向同步）──"]
    if not node.is_group:
        return out + _indexed_slice_view(node, 0, node.byte_len, read, wf, W, names)
    off = 0
    for ch in node.children:
        w = ch.byte_len
        if ch.is_filler:
            off += w
        elif ch.is_group:
            out.append(f"    // TODO REDEFINES 子项 {ch.name} 为嵌套组，需人工核对")
            off += w * (ch.occurs or 1)
        elif ch.occurs:
            out += _indexed_array_view(ch, off, w, read, wf, W, names)
            off += w * ch.occurs
        else:
            out += _indexed_slice_view(ch, off, w, read, wf, W, names)
            off += w
    return out


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
                     arrayed: set[str], array_dims: dict[str, list[int]] | None = None) -> list[str]:
    """REDEFINES 节点 → 视图方法（或退化 TODO）。目标缺失由调用方走 render_primary。"""
    tnode = name_index.get(node.redefines.upper())
    if tnode is None:
        return render_primary(node)
    if node.redefines.upper() in arrayed or node.name.upper() in arrayed:
        target_dims = (array_dims or {}).get(node.redefines.upper(), [])
        alias_dims = (array_dims or {}).get(node.name.upper(), [])
        view = _array_redefines_view(node, tnode, target_dims, alias_dims)
        if view is not None:
            return view
        return _todo_plain(node, f"REDEFINES {node.redefines}: 处于 OCCURS 数组上下文，"
                                 f"定宽视图不适用，需人工核对", array_dims)
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
