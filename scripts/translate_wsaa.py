"""
瘦入口：把拆解出的 WORKING-STORAGE 块翻译为 Java（确定性，无 LLM）。

对应设计：docs/详细设计/步骤03-WSAA块翻译设计.md。
只做参数解析 + 调用 parser.ws.parse_ws → translator.wsaa.render_wsaa → 写 .java，
不含业务逻辑（rule 17）。参数化、可复用于任意程序（rule 12）。

用法：
  python scripts/translate_wsaa.py --program ZPOLDWNM \
      --in  /home/zp/Documents/cob/ZPOLDWNM/拆解/ZPOLDWNMWSAA.cob \
      --out /home/zp/Documents/cob/ZPOLDWNM/拆解/ZpoldwnmWsaa.java
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from parser.ws import parse_ws
from translator.wsaa import render_wsaa


def _stats(roots) -> dict:
    def walk(n):
        yield n
        for c in n.children:
            yield from walk(c)
    alln = [x for r in roots for x in walk(r)]
    return {
        "01级根": len(roots),
        "节点总数": len(alln),
        "组项": sum(1 for n in alln if n.is_group),
        "叶子": sum(1 for n in alln if not n.is_group),
        "88条件持有项": sum(1 for n in alln if n.conditions),
        "88条件总数": sum(len(n.conditions) for n in alln),
        "REDEFINES": sum(1 for n in alln if n.redefines),
        "OCCURS": sum(1 for n in alln if n.occurs),
        "编辑PIC": sum(1 for n in alln if n.is_edited),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="WORKING-STORAGE 块 → Java（确定性）")
    ap.add_argument("--program", required=True, help="COBOL 程序名，如 ZPOLDWNM")
    ap.add_argument("--in", dest="infile", required=True, help="WSAA 拆解块 .cob 路径")
    ap.add_argument("--out", dest="outfile", required=True, help="输出 .java 路径")
    args = ap.parse_args()

    roots = parse_ws(args.infile)
    java = render_wsaa(roots, args.program)
    Path(args.outfile).write_text(java, encoding="utf-8")

    print(f"✓ 已生成 {args.outfile}（{java.count(chr(10)) + 1} 行）")
    print("自检统计：")
    for k, v in _stats(roots).items():
        print(f"  {k:14s}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
