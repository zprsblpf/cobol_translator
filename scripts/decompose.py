#!/usr/bin/env python3
"""
COBOL 拆解器 —— 瘦入口（只解析参数 + 调用，不含业务逻辑）。

业务逻辑见 decompose/ 功能包；本文件仅做 CLI 编排。
对应设计文档：docs/详细设计/步骤02-MongoDB入库实现与输出目录调整设计.md（§2b 包结构）。

输出布局（--out 指向「程序目录」）
    <out>/拆解/*.cob        各 SECTION 切片 + {PROGRAM}WSAA.cob
    <out>/manifest.json     入库数据源（含全部字段）
    <out>/manifest.md       人读清单

用法
    # 纯文件模式（零依赖）
    python scripts/decompose.py --cob /path/ZPOLDWNM.cob --program ZPOLDWNM \
        --out /home/zp/Documents/cob/ZPOLDWNM
    # Mongo 就绪后补入库
    python scripts/decompose.py --import-only --out /home/zp/Documents/cob/ZPOLDWNM \
        --mongo-uri "mongodb://.../" --db cobol
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from decompose.core import decompose          # noqa: E402
from decompose.importer import import_mongo    # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="COBOL 拆解器（拆解+写文件，入库后补）")
    ap.add_argument("--cob", help="cob 源文件路径")
    ap.add_argument("--program", default=None, help="程序名（缺省取 PROGRAM-ID）")
    ap.add_argument("--out", required=True, help="输出目录（程序目录）")
    ap.add_argument("--import-only", action="store_true",
                    help="跳过拆解，仅把已有 manifest.json 导入 MongoDB")
    ap.add_argument("--mongo-uri", default=None, help="MongoDB 连接串（提供则入库）")
    ap.add_argument("--db", default="cobol", help="MongoDB 库名")
    ap.add_argument("--coll", default=None, help="集合名（缺省=程序名）")
    args = ap.parse_args()

    out_dir = Path(args.out)

    if not args.import_only:
        if not args.cob:
            ap.error("拆解模式需要 --cob")
        stats = decompose(Path(args.cob), args.program, out_dir)
        print("=== 拆解完成（文件）===")
        print(json.dumps(stats, ensure_ascii=False, indent=2))

    if args.mongo_uri:
        manifest_path = out_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        coll = args.coll or manifest["program"]
        print(f"=== 入库 MongoDB（{args.db}.{coll}）===")
        print(json.dumps(import_mongo(manifest_path, args.mongo_uri, args.db, coll),
                         ensure_ascii=False, indent=2))
    else:
        print("（未提供 --mongo-uri，跳过入库；manifest.json 已含全部入库字段，"
              "Mongo 就绪后用 --import-only --mongo-uri 导入）")


if __name__ == "__main__":
    main()
