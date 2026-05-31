#!/usr/bin/env python3
"""
拆解结果校验脚本（对应设计文档 docs/详细设计/步骤01-拆解与存库设计.md §7）。

对 scripts/decompose.py 的产物做自检，逐项打印通过情况：
- 块数统计（META + WORKING-STORAGE + N×SECTION）
- 入参、COPY 分类
- SECTION 名无重复、切片文件名唯一
- 每个 SECTION 的 manifest.raw_text 与切片文件内容逐字一致
- 切片中不含 '!!!!!!' 停用行（应为 0）、保留了 '*' 注释（应 > 0）
- SECTION 文档预留字段（params_in/out, calls, logic, java_code）均为 null

用法
    python scripts/verify_decompose.py --out /home/zp/Documents/cob/ZPOLDWNM
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from collections import Counter

SLICE_SUBDIR = "拆解"   # 切片子目录（与 decompose/manifest.py 保持一致）


def verify(out_dir: str) -> bool:
    slice_dir = os.path.join(out_dir, SLICE_SUBDIR)
    m = json.load(open(os.path.join(out_dir, "manifest.json"), encoding="utf-8"))
    docs = m["documents"]
    secs = m["sections"]
    ok = True

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        ok = ok and cond
        mark = "✅" if cond else "❌"
        print(f"{mark} {label}{(' — ' + detail) if detail else ''}")

    # 1. 块数统计
    bt = dict(Counter(x["block_type"] for x in docs))
    check("块数统计", m["total_blocks"] == m["section_count"] + 2,
          f"total={m['total_blocks']} section={m['section_count']} types={bt}")

    # 2. 入参
    check("入参 = [LETCMNT-PARAMS, PMSPNT-PARAMS]",
          m["params_in"] == ["LETCMNT-PARAMS", "PMSPNT-PARAMS"],
          str(m["params_in"]))

    # 3. COPY 分类
    cc = {k: len(v) for k, v in m["copies"].items()}
    check("COPY 分类已登记", sum(cc.values()) > 0, str(cc))

    # 4. SECTION 名无重复
    dup = [k for k, v in Counter(s["block_name"] for s in secs).items() if v > 1]
    check("SECTION 名无重复", not dup, str(dup))

    # 5. 切片文件名唯一
    files = [s["file"] for s in secs]
    check("切片文件名唯一", len(files) == len(set(files)), f"files={len(files)}")

    # 6. raw_text == 文件内容
    mismatch = []
    for doc in docs:
        if doc["block_type"] != "SECTION":
            continue
        sec = next(s for s in secs
                   if s["block_name"] == doc["block_name"]
                   and s["block_index"] == doc["block_index"])
        fc = open(os.path.join(slice_dir, sec["file"]), encoding="utf-8").read().rstrip("\n")
        if doc["raw_text"] != fc:
            mismatch.append(doc["block_name"])
    check("manifest.raw_text 与切片文件逐字一致", not mismatch,
          f"mismatch={len(mismatch)} {mismatch[:5]}")

    # 7. 停用行已丢弃 / 注释已保留
    slices = glob.glob(os.path.join(slice_dir, "*.cob"))
    with_deact = sum(1 for f in slices if "!!!!!!" in open(f, encoding="utf-8").read())
    with_cmt = sum(1 for f in slices
                   if any(l.startswith("*") for l in open(f, encoding="utf-8").read().splitlines()))
    check("切片不含 !!!!!! 停用行", with_deact == 0, f"{with_deact} 个文件含停用行")
    check("切片保留 * 注释", with_cmt > 0, f"{with_cmt} 个文件含注释")

    # 8. 预留字段均为 null
    reserved = ["params_in", "params_out", "calls", "logic", "java_code"]
    nonnull = sum(1 for x in docs if x["block_type"] == "SECTION"
                  for r in reserved if x.get(r) is not None)
    check("SECTION 预留字段均为 null", nonnull == 0, f"非空 {nonnull}")

    print("\n" + ("全部通过 ✅" if ok else "存在失败项 ❌"))
    return ok


def main() -> None:
    ap = argparse.ArgumentParser(description="校验 decompose.py 的拆解产物")
    ap.add_argument("--out", required=True, help="拆解输出目录")
    args = ap.parse_args()
    raise SystemExit(0 if verify(args.out) else 1)


if __name__ == "__main__":
    main()
