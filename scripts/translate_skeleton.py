"""
瘦入口：把主 cob 程序翻译为 Java 主类骨架（确定性，无 LLM）。

对应设计：docs/详细设计/步骤05-cob到Java翻译引擎详细设计.md。
只做参数解析 + 调用 parser.cobol_parser.parse → translator.skeleton_gen.render_skeleton → 写 .java，
不含业务逻辑（rule 17）。参数化、可复用于任意程序（rule 12）。

用法：
  python scripts/translate_skeleton.py \
      --in  /home/zp/Documents/cob/ZPOLDWNM/ZPOLDWNM.cob \
      --out /home/zp/Documents/cob/ZPOLDWNM/拆解/Zpoldwnm.java

  # 快速冒烟（只翻前 N 段）：
  python scripts/translate_skeleton.py \
      --in  tests/fixtures/minimal.cob \
      --out /tmp/Minismoke.java --limit 1 --stats
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from parser.cobol_parser import parse
from translator.skeleton_gen import render_skeleton


def _count_todo(java: str) -> int:
    """统计 Java 产物中的 TODO 标记数。"""
    return len(re.findall(r"//\s*TODO", java))


def _count_fallback_calls(java: str) -> int:
    """统计 Java 产物中的 LLM fallback 调用标记。"""
    return len(re.findall(r"processWithLlm|llm_fallback|LLM", java, re.IGNORECASE))


def _count_raw_tokens(java: str) -> int:
    """粗略统计代码行长度的 TODO/LEAF/RAW 行数。"""
    return len(re.findall(r"TODO-LEAF|TODO-CALL|TODO-PERFORM|TODO-IF|TODO-EVALUATE|TODO-GOTO|TODO-RAW", java))


def _print_stats(program, java: str, limit: int | None):
    """输出翻译统计。"""
    total_lines = java.count("\n") + 1
    todo_total = _count_todo(java)
    fallback_calls = _count_fallback_calls(java)
    raw_todo = _count_raw_tokens(java)
    sections_used = limit if limit else len(program.sections)

    print(f"  程序          : {program.program_id}")
    print(f"  SECTION 数    : {len(program.sections)}{' (限制: ' + str(limit) + ')' if limit else ''}")
    print(f"  已翻卷段数    : {sections_used}")
    print(f"  产物行数      : {total_lines}")
    print(f"  TODO 总数     : {todo_total}")
    print(f"  叶子 TODO     : {raw_todo}")
    print(f"  LLM 调用      : {fallback_calls}")
    print(f"  USING 入参    : {program.linkage_using}")
    print(f"  COPY 引用     : {len(program.copy_refs)}")


def main() -> int:
    ap = argparse.ArgumentParser(description="cob → Java 主类骨架（确定性）")
    ap.add_argument("--in", dest="infile", required=True, help="主 cob 程序 .cob 路径")
    ap.add_argument("--out", dest="outfile", required=True, help="输出 .java 路径")
    ap.add_argument("--limit", type=int, default=None,
                    help="限制翻译前 N 个 SECTION（用于大文件快速冒烟）")
    ap.add_argument("--stats", action="store_true",
                    help="输出详细统计（TODO 计数/叶子 TODO/LLM 调用数）")
    args = ap.parse_args()

    program = parse(args.infile)

    # 如果有限制，截断 SECTION 列表
    if args.limit is not None and args.limit > 0:
        original = list(program.sections)
        program.sections = original[:args.limit]

    java = render_skeleton(program)

    # 恢复完整 SECTION 列表（供统计用）
    if args.limit is not None and args.limit > 0:
        program.sections = original

    out_path = Path(args.outfile)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(java, encoding="utf-8")

    print(f"OK generated {args.outfile} ({java.count(chr(10)) + 1} lines)")
    if args.stats:
        _print_stats(program, java, args.limit)
    else:
        print(f"  程序          : {program.program_id}")
        print(f"  SECTION 数    : {len(program.sections)}"
              f"{' (限制: ' + str(args.limit) + ')' if args.limit else ''}")
        print(f"  USING 入参    : {program.linkage_using}")
        print(f"  COPY 引用     : {len(program.copy_refs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
