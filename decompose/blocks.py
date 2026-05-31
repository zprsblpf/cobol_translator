"""
构块（设计文档 §3.2）。

职责：把 PROCEDURE DIVISION 切成 SECTION 块，并构建 WORKING-STORAGE 块、META 汇总块，
以及为切片生成唯一文件名。产出 decompose/models.py 的 Block 列表。
依赖 decompose/lines.py（清洗）与 decompose/models.py（Block）；被 decompose/core.py 调用。
"""
from __future__ import annotations

import re

from .lines import _effective, clean_block
from .models import Block

_SECTION_RE = re.compile(r"^\s*([A-Z0-9][A-Z0-9\-]*)\s+SECTION\s*\.", re.IGNORECASE)

# 这些 SECTION 属于 ENVIRONMENT/DATA/LINKAGE，不是 PROCEDURE 方法体，需排除
_NON_PROC_SECTIONS = {
    "CONFIGURATION", "INPUT-OUTPUT", "FILE", "WORKING-STORAGE", "LINKAGE",
}


def extract_sections(raw_lines: list[str], proc_start: int, program: str,
                     source_file: str) -> list[Block]:
    """从 PROCEDURE DIVISION 起，按有效 SECTION 头切块（设计文档 §3.2）。

    单趟扫描：遇到有效 SECTION 头记录边界；'!!!!!!' 开头的 SECTION 头不算边界。
    """
    # 1) 收集所有有效 SECTION 头的物理行号(0-based)与名字
    heads: list[tuple[int, str]] = []
    for i in range(proc_start, len(raw_lines)):
        eff = _effective(raw_lines[i])
        if eff is None:
            continue
        m = _SECTION_RE.match(eff)
        if not m:
            continue
        name = m.group(1).upper()
        if name in _NON_PROC_SECTIONS:
            continue
        heads.append((i, name))

    # 2) 按相邻头切区间，区间末 = 下一头前一行；最后一段到文件尾
    blocks: list[Block] = []
    for idx, (line_idx, name) in enumerate(heads):
        end_idx = heads[idx + 1][0] if idx + 1 < len(heads) else len(raw_lines)
        raw_text = clean_block(raw_lines, line_idx, end_idx)
        blocks.append(Block(
            program=program,
            source_file=source_file,
            block_index=idx + 1,           # SECTION 从 1 递增
            block_name=name,
            block_type="SECTION",
            start_line=line_idx + 1,        # 转 1-based
            end_line=end_idx,               # 1-based 含末行
            raw_text=raw_text,
        ))
    return blocks


def build_ws_block(raw_lines: list[str], ws_start: int, ws_end: int,
                   program: str, source_file: str) -> Block:
    """生成 WORKING-STORAGE 参数块，命名 {PROGRAM}WSAA（设计文档 §3 规则②）。"""
    raw_text = clean_block(raw_lines, ws_start, ws_end)
    return Block(
        program=program,
        source_file=source_file,
        block_index=0,
        block_name=f"{program}WSAA",
        block_type="WORKING-STORAGE",
        start_line=ws_start + 1,
        end_line=ws_end,
        raw_text=raw_text,
    )


def build_meta_block(program: str, source_file: str, divs: dict,
                     copies: dict, n_sections: int, total_lines: int) -> Block:
    """汇总 META 块：类名、入参、COPY 分类、参数块名等（设计文档 §3 规则①④③）。"""
    return Block(
        program=program,
        source_file=source_file,
        block_index=0,
        block_name="__META__",
        block_type="META",
        start_line=0,
        end_line=total_lines,
        raw_text="",
        extra={
            "class_name": program,
            "ws_block_name": f"{program}WSAA",
            "params_in": divs["using"],
            "copies": copies,
            "section_count": n_sections,
            "total_lines": total_lines,
        },
    )


def slug_filename(name: str, used: set[str]) -> str:
    """SECTION 名 → 唯一 .cob 文件名（冲突加 -2/-3 后缀）。"""
    base = name
    candidate = base
    n = 2
    while candidate in used:
        candidate = f"{base}-{n}"
        n += 1
    used.add(candidate)
    return f"{candidate}.cob"
