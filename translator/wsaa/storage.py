"""
定宽存储串（fixed-width storage string）构造：COBOL 共享存储的本质抽象。

对应设计：docs/详细设计/步骤04-WSAA遗留补全设计.md §3；决策 D8–D12 / 假设 A1、A2。

任一节点都有「W 字符定宽存储串」表示，所有 REDEFINES / 重叠视图建在它之上，
改子↔改父经同一 backing（数值变量或字符目标）双向同步：
- 字符标量 X(w)            → 读 name              / 写 name = v
- 数值标量 9../S9../S9..V9.. → 读 _toDigits(<BigDecimal>,w,scale) / 写 name = parse(v)
- 组（子项全为上述标量）    → 子项读表达式按偏移拼接 / 按偏移切片写回（FILLER 占位不写）
不支持（OCCURS / 编辑型 / COMP-3 / 嵌套组）→ 返回 None，调用方退化为带原因的 TODO。

用法：`acc = storage_accessor(tnode)`；`read, write_fn, W = acc`；
`write_fn(strvar)` 返回把 W 宽字符串变量 strvar 写回 backing 的语句行。
"""
from __future__ import annotations

import re

from parser.ws.model import WsNode
from translator.wsaa.render_field import java_name

_NUMERIC = ("int", "long", "BigDecimal")

# 数值 ↔ 定宽数字串 辅助方法（随视图按需输出，类似 render_view.PAD_HELPER）
NUM_HELPER = [
    "    /** 数值 → 定宽数字串：取绝对值（假设 A1），scale 位低位小数，左补 0 / 高位截断到 n。 */",
    "    private static String _toDigits(BigDecimal v, int n, int scale) {",
    "        if (v == null) v = BigDecimal.ZERO;",
    "        String s = v.movePointRight(scale).abs().toBigInteger().toString();",
    "        if (s.length() > n) return s.substring(s.length() - n);",
    "        StringBuilder b = new StringBuilder();",
    "        while (b.length() < n - s.length()) b.append('0');",
    "        return b.append(s).toString();",
    "    }",
    "    /** 定宽数字串 → BigDecimal（scale 位小数）；空串按 0。 */",
    "    private static BigDecimal _fromDigits(String s, int scale) {",
    "        s = (s == null ? \"\" : s.trim());",
    "        if (s.isEmpty()) s = \"0\";",
    "        return new BigDecimal(new java.math.BigInteger(s)).movePointLeft(scale);",
    "    }",
]


def scale_of(pic: str) -> int:
    """PIC 中 V 之后的 9 位数（小数位）；无 V 返回 0。"""
    u = pic.upper().replace(" ", "")
    m = re.search(r"V(.*)$", u)
    if not m:
        return 0
    tail = m.group(1)
    total = sum(int(n) for n in re.findall(r"9\((\d+)\)", tail))
    return total + re.sub(r"9\(\d+\)", "", tail).count("9")


def _is_comp(n: WsNode) -> bool:
    return "COMP" in (n.comp or "").upper()


def _scalar_ok(n: WsNode) -> bool:
    """可建定宽存储串的标量：非 OCCURS、非编辑型、非 COMP、宽度有效。"""
    return not n.occurs and not n.is_edited and not _is_comp(n) and n.byte_len > 0


def num_to_digits(java_expr: str, jtype: str, w: int, scale: int) -> str:
    """java 数值表达式 → 定宽数字串表达式。"""
    val = java_expr if jtype == "BigDecimal" else f"BigDecimal.valueOf({java_expr})"
    return f"_toDigits({val}, {w}, {scale})"


def num_from_digits(str_expr: str, jtype: str, scale: int) -> str:
    """定宽数字串表达式 → java 数值表达式（按 backing 类型）。"""
    if jtype == "BigDecimal":
        return f"_fromDigits({str_expr}, {scale})"
    if jtype == "long":
        return f"Long.parseLong({str_expr}.trim())"
    return f"Integer.parseInt({str_expr}.trim())"


def _group_accessor(g: WsNode):
    """组目标 → (读表达式, 写函数, 总宽)；含不支持子项返回 None。"""
    terms, writes, off = [], [], 0
    for ch in g.children:
        w = ch.byte_len
        if w <= 0 or ch.occurs or ch.is_group or ch.is_edited or _is_comp(ch):
            return None
        if ch.is_filler:
            terms.append(f'_pad("", {w})')
        elif ch.java_type == "String":
            cn = java_name(ch.name)
            terms.append(f"_pad({cn}, {w})")
            writes.append((off, w, cn, "String", 0))
        elif ch.java_type in _NUMERIC:
            cn, sc = java_name(ch.name), scale_of(ch.pic)
            terms.append(num_to_digits(cn, ch.java_type, w, sc))
            writes.append((off, w, cn, ch.java_type, sc))
        else:
            return None
        off += w

    def write_fn(v: str, _w=writes) -> list[str]:
        out = []
        for o, w, cn, jt, sc in _w:
            seg = f"{v}.substring({o}, {o + w})"
            rhs = seg if jt == "String" else num_from_digits(seg, jt, sc)
            out.append(f"        {cn} = {rhs};")
        return out

    return " + ".join(terms), write_fn, off


def storage_accessor(tnode: WsNode):
    """目标节点 → (读表达式→W 宽串, 写函数(strvar)->语句行, W)；不支持返回 None。"""
    if tnode.is_group:
        return _group_accessor(tnode)
    if not _scalar_ok(tnode):
        return None
    name, w = java_name(tnode.name), tnode.byte_len
    if tnode.java_type == "String":
        return name, (lambda v: [f"        {name} = {v};"]), w
    if tnode.java_type in _NUMERIC:
        sc, jt = scale_of(tnode.pic), tnode.java_type
        read = num_to_digits(name, jt, w, sc)
        return read, (lambda v: [f"        {name} = {num_from_digits(v, jt, sc)};"]), w
    return None
