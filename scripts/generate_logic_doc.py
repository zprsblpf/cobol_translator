"""
CLI 入口：从 COBOL 程序生成逻辑文档（JSON + Markdown）。

用法：
    python scripts/generate_logic_doc.py --cob tests/fixtures/minimal.cob --out-dir output/logic-doc

依赖：parser 包（项目本地 COBOL 解析器）。
"""
from __future__ import annotations

import argparse
import sys
import os

# 确保项目根在 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logician import generate_and_save


def main():
    parser = argparse.ArgumentParser(
        description="从 COBOL 程序生成逻辑文档",
    )
    parser.add_argument("--cob", required=True, help="COBOL 源文件路径")
    parser.add_argument("--out-dir", default="output/logic-doc",
                        help="输出目录（默认 output/logic-doc）")
    parser.add_argument("--base-name", default=None,
                        help="输出文件名前缀（默认用 program_id）")
    args = parser.parse_args()

    cob_path = os.path.abspath(args.cob)
    if not os.path.isfile(cob_path):
        print(f"❌ 文件不存在: {cob_path}")
        sys.exit(1)

    # 解析 COBOL
    from parser.cobol_parser import parse
    print(f"📄 解析: {cob_path}")
    program = parse(cob_path)
    print(f"   PROGRAM-ID: {program.program_id}")
    print(f"   SECTION 数: {len(program.sections)}")

    # 生成逻辑文档（含 88 条件名展开）
    from parser.ws import parse_ws
    ws_tree = parse_ws(cob_path)
    print(f"🔧 生成逻辑文档...")
    doc, json_path, md_path = generate_and_save(
        program, args.out_dir, args.base_name, ws_tree=ws_tree,
    )
    print(f"✅ JSON: {json_path}")
    print(f"✅ MD:   {md_path}")
    print(f"   路径数: {len(doc.paths)}")
    print(f"   结果数: {len(doc.results)}")
    print(f"   节点数: {len(doc.nodes)}")


if __name__ == "__main__":
    main()
