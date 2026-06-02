"""
扫描一个 WORKING-STORAGE 拆解块，穷举其中出现的 COBOL 构造 / 类型并去重统计。

对应设计：docs/详细设计/步骤04-WSAA遗留补全设计.md（§类型清单来源）。
目的：用脚本一次性读出「WSAA 部分到底有哪些类型」，保证 COBOL→Java 映射目录不遗漏；
只打印紧凑汇总（不回显大段源码 / 产物），节省 token（协作规范六-22）。

复用（rule 15）：parser.ws.parse_ws 解析；translator.wsaa.render_class._index_and_groups
判定 REDEFINES 目标 / 数组上下文，与翻译线口径一致。

用法：
  python scripts/scan_ws_types.py --in /home/zp/Documents/cob/ZPOLDWNM/拆解/ZPOLDWNMWSAA.cob
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from parser.ws import parse_ws
from translator.wsaa.render_class import _index_and_groups
from translator.wsaa.render_view import can_group_view

_EXPAND = re.compile(r"([A-Z9*])\((\d+)\)")


def pic_signature(pic: str) -> str:
    """把 PIC 归一为规范签名（999→9(3)、XX→X(2)），用于去重统计。"""
    u = pic.upper().replace(" ", "")
    if not u:
        return "(组)"
    u = _EXPAND.sub(lambda m: m.group(1) * int(m.group(2)), u)   # 展开 (n)
    out, i = [], 0
    while i < len(u):                                            # 再按 run 折叠
        c, j = u[i], i
        while j < len(u) and u[j] == c:
            j += 1
        out.append(c if j - i == 1 else f"{c}({j - i})")
        i = j
    return "".join(out)


def _all_nodes(roots):
    def walk(n):
        yield n
        for c in n.children:
            yield from walk(c)
    return [x for r in roots for x in walk(r)]


def _redefines_kind(node, idx, arrayed) -> str:
    """粗分 REDEFINES 子类（与步骤04 处理分支对应）。"""
    t = idx.get(node.redefines.upper())
    if t is None:
        return "目标缺失(停用/copybook)→当主定义"
    if node.name.upper() in arrayed or node.redefines.upper() in arrayed:
        return "数组上下文(留TODO)"
    node_num = (not node.is_group) and node.java_type != "String"
    tgt_num = (not t.is_group) and t.java_type != "String"
    if node_num and not tgt_num:
        return "数值 over 字符"
    if tgt_num:
        return "字符/数值子项 over 数值"
    return "字符 over 字符/组"


def scan(infile: str) -> None:
    roots = parse_ws(infile)
    idx, _vg, arrayed = _index_and_groups(roots)
    nodes = _all_nodes(roots)
    leaves = [n for n in nodes if not n.is_group and not n.is_filler]

    # 1) PIC 类型分布：签名 → (次数, java类型, 字节宽, 编辑?, 示例)
    sig_stat: dict[str, dict] = {}
    for n in leaves:
        sig = pic_signature(n.pic) + (f" {n.comp}".rstrip() if n.comp else "")
        s = sig_stat.setdefault(sig, {"n": 0, "jt": n.java_type, "w": n.byte_len,
                                      "ed": n.is_edited, "ex": n.name})
        s["n"] += 1

    print(f"=== PIC 类型分布（去重 {len(sig_stat)} 种 / 叶子 {len(leaves)}）===")
    print(f"{'COBOL PIC 签名':28s} {'Java':10s} {'宽':>3s} {'编辑':>4s} {'次数':>4s}  示例")
    for sig, s in sorted(sig_stat.items(), key=lambda kv: -kv[1]["n"]):
        print(f"{sig:28s} {s['jt']:10s} {s['w']:>3d} {('是' if s['ed'] else ''):>4s} "
              f"{s['n']:>4d}  {s['ex']}")

    # 2) 构造统计
    occ = Counter("二维" if sum(1 for a in _ancestors(n, roots) if a.occurs) else "一维"
                  for n in nodes if n.occurs)
    cond = Counter("INDICATOR(B'0/1')" if c.is_boolean else "取值列表"
                   for n in nodes for c in n.conditions)
    print("\n=== 构造统计 ===")
    print(f"  01级根:{len(roots)}  节点:{len(nodes)}  组:{sum(n.is_group for n in nodes)}  "
          f"叶子:{len(leaves)}  FILLER:{sum(n.is_filler for n in nodes)}")
    print(f"  OCCURS: {dict(occ)}    可重叠视图组(全字符): "
          f"{sum(1 for n in nodes if can_group_view(n))}")
    print(f"  VALUE: {sum(1 for n in nodes if n.has_value)}    "
          f"INDICATOR(PIC 1): {sum(1 for n in nodes if n.is_indicator)}")
    print(f"  88 条件: {dict(cond)}")

    # 3) REDEFINES 子类分布
    reds = [n for n in nodes if n.redefines]
    kinds: dict[str, list] = defaultdict(list)
    for n in reds:
        kinds[_redefines_kind(n, idx, arrayed)].append(n.name)
    print(f"\n=== REDEFINES 子类（共 {len(reds)}）===")
    for k, names in sorted(kinds.items(), key=lambda kv: -len(kv[1])):
        print(f"  {k:32s} {len(names):>2d}  {', '.join(names[:4])}"
              f"{' …' if len(names) > 4 else ''}")


def _ancestors(node, roots):
    """返回 node 的祖先链（含自身之上）；用于判定二维 OCCURS。"""
    path = []

    def walk(n, chain):
        if n is node:
            path.extend(chain)
            return True
        for c in n.children:
            if walk(c, chain + [n]):
                return True
        return False

    for r in roots:
        if walk(r, []):
            break
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="扫描 WORKING-STORAGE 块的 COBOL 类型分布")
    ap.add_argument("--in", dest="infile", required=True, help="WSAA 拆解块 .cob 路径")
    args = ap.parse_args()
    scan(args.infile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
