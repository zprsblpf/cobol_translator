#!/usr/bin/env python3
"""
gen_stub_copybooks.py —— 为 ProLeap 解析生成「缺失拷贝簿」的最小桩（spike 用）

用途：
  ProLeap 预处理器对源里每个 ``COPY xxx`` 都要在拷贝簿目录找到对应文件，缺一即
  整程序解析失败。真实工程里大量 ``*SKM`` / ``*REC`` 等拷贝簿由主机数据字典在编译
  期生成、不随源码发布。本脚本扫描源中引用、与现有 ``.cob`` 资源比对，为每个缺失
  的 COPY 生成一个**最小合法 .cob 桩**，仅为喂饱预处理器、让解析跑通以提取
  PROCEDURE DIVISION 控制流；数据区不完整是可接受的（详见调研文档）。

对应设计文档：docs/调研/ProLeap解析器评估调研.md

设计思路：
  - 全程参数化（源文件 / 若干现有拷贝簿目录 / 桩输出目录），无硬编码；
  - 桩内容：每个缺失 COPY 生成一个同名 01 组项 + 单个 FILLER，定宽格式（code 自 col8）；
    01 名取拷贝簿名，使「按组名引用」能在 ASG 里解析为已定义元素；
  - 只写「缺失」者，已有 .cob 的不覆盖；可重复运行（幂等）。

用法：
  python3 gen_stub_copybooks.py <源.cob> <桩输出目录> <现有拷贝簿目录...>
"""
import re
import sys
from pathlib import Path

_COPY_RE = re.compile(r"\bCOPY\s+([A-Za-z0-9][A-Za-z0-9\-]*)", re.IGNORECASE)


def distinct_copy_names(src: Path) -> set[str]:
    """从源文件抽取去重的 COPY 名（大写）。"""
    text = src.read_text(encoding="utf-8", errors="replace")
    return {m.group(1).upper() for m in _COPY_RE.finditer(text)}


def existing_cob_basenames(dirs: list[Path]) -> set[str]:
    """收集若干目录下所有 .cob 的基名（大写），作为「已有」集合。"""
    have: set[str] = set()
    for d in dirs:
        if d.is_dir():
            for f in d.glob("*.cob"):
                have.add(f.stem.upper())
    return have


def stub_content(name: str) -> str:
    """生成一个最小合法拷贝簿桩（定宽格式，code 区自第 8 列）。"""
    return (
        f"      * stub copybook (ProLeap spike) for COPY {name}\n"
        f"       01  {name}.\n"
        f"           05  {name[:24]}-FILLER PIC X(01).\n"
    )


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print("用法: gen_stub_copybooks.py <源.cob> <桩输出目录> <现有拷贝簿目录...>",
              file=sys.stderr)
        return 2
    src = Path(argv[1])
    out_dir = Path(argv[2])
    have_dirs = [Path(p) for p in argv[3:]]

    refs = distinct_copy_names(src)
    have = existing_cob_basenames(have_dirs)
    missing = sorted(refs - have)

    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for name in missing:
        (out_dir / f"{name}.cob").write_text(stub_content(name), encoding="utf-8")
        written += 1

    print(f"引用 distinct={len(refs)} 已有.cob={len(refs & have)} "
          f"缺失={len(missing)} 生成桩={written} -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
