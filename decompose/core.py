"""
顶层编排。

职责：串起「读取 → 结构定位 → 构块 → 写文件」的完整拆解流程，返回统计与 manifest 路径。
依赖 decompose/structure.py、decompose/blocks.py、decompose/manifest.py；被瘦入口 scripts/decompose.py 调用。
对应设计文档：步骤02 §2b.2 调用关系。
"""
from __future__ import annotations

from pathlib import Path

from .blocks import build_meta_block, build_ws_block, extract_sections
from .manifest import write_files
from .structure import (classify_copies, extract_copies, locate_divisions,
                        read_raw_lines)


def decompose(cob_path: Path, program: str | None, out_dir: Path) -> dict:
    """完整拆解流程：解析 → 构块 → 写文件。返回统计与 manifest 路径。"""
    raw_lines = read_raw_lines(cob_path)
    total_lines = len(raw_lines)
    divs = locate_divisions(raw_lines)
    program = program or divs["program_id"]
    source_file = cob_path.name

    ws_start = divs["ws_start"]
    ws_end = divs["linkage_start"] if divs["linkage_start"] > 0 else divs["proc_start"]
    if ws_end < 0:
        ws_end = total_lines

    copies = classify_copies(extract_copies(raw_lines, ws_start, ws_end))
    sections = extract_sections(raw_lines, divs["proc_start"], program, source_file)
    ws = build_ws_block(raw_lines, ws_start, ws_end, program, source_file)
    meta = build_meta_block(program, source_file, divs, copies,
                            len(sections), total_lines)

    stats = write_files(sections, meta, ws, out_dir)
    stats["program"] = program
    stats["params_in"] = divs["using"]
    stats["copies"] = {k: len(v) for k, v in copies.items()}
    stats["manifest"] = str(out_dir / "manifest.json")
    return stats
