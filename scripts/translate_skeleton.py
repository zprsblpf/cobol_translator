"""
瘦入口：把主 cob 程序翻译为 Java 主类骨架（确定性，无 LLM）。

对应设计：docs/详细设计/步骤05-cob到Java翻译引擎详细设计.md。
只做参数解析 + 调用 parser.cobol_parser.parse → translator.skeleton_gen.render_skeleton → 写 .java，
不含业务逻辑（rule 17）。参数化、可复用于任意程序（rule 12）。

用法：
  python scripts/translate_skeleton.py \
      --in  /home/zp/Documents/cob/ZPOLDWNM/ZPOLDWNM.cob \
      --out /home/zp/Documents/cob/ZPOLDWNM/拆解/Zpoldwnm.java
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from parser.cobol_parser import parse
from translator.skeleton_gen import render_skeleton


def main() -> int:
    ap = argparse.ArgumentParser(description="cob → Java 主类骨架（确定性）")
    ap.add_argument("--in", dest="infile", required=True, help="主 cob 程序 .cob 路径")
    ap.add_argument("--out", dest="outfile", required=True, help="输出 .java 路径")
    args = ap.parse_args()

    program = parse(args.infile)
    java = render_skeleton(program)
    Path(args.outfile).write_text(java, encoding="utf-8")

    print(f"✓ 已生成 {args.outfile}（{java.count(chr(10)) + 1} 行）")
    print("自检统计：")
    print(f"  程序          : {program.program_id}")
    print(f"  SECTION 数    : {len(program.sections)}")
    print(f"  USING 入参    : {program.linkage_using}")
    print(f"  COPY 引用     : {len(program.copy_refs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
