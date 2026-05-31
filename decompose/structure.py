"""
结构定位（设计文档 §3）。

职责：读取物理行，定位 DIVISION/SECTION 边界与 USING 入参，收集并分类 COPY。
依赖 decompose/lines.py 的有效行判定；被 decompose/core.py 调用。
"""
from __future__ import annotations

import re
from pathlib import Path

from .lines import _effective

_COPY_RE = re.compile(r"\bCOPY\s+([A-Za-z0-9][A-Za-z0-9\-]*)", re.IGNORECASE)


def read_raw_lines(path: Path) -> list[str]:
    """以 latin-1 按物理行读取（保留原始字节与列位，含末尾换行去除）。"""
    with open(path, encoding="latin-1") as f:
        return [ln.rstrip("\n").rstrip("\r") for ln in f]


def locate_divisions(raw_lines: list[str]) -> dict:
    """定位 PROGRAM-ID、WORKING-STORAGE / LINKAGE / PROCEDURE 起始行(0-based)及 USING 入参。

    只在有效代码行上匹配，避免被注释/停用行干扰。
    返回 dict：program_id, ws_start, linkage_start, proc_start, using[]
    """
    program_id = "UNKNOWN"
    ws_start = linkage_start = proc_start = -1
    using: list[str] = []

    for i, raw in enumerate(raw_lines):
        eff = _effective(raw)
        if eff is None:
            continue
        up = eff.upper()

        if program_id == "UNKNOWN":
            m = re.search(r"PROGRAM-ID\.\s+(\S+)", up)
            if m:
                program_id = m.group(1).rstrip(".")

        if ws_start < 0 and re.search(r"\bWORKING-STORAGE\s+SECTION\b", up):
            ws_start = i
        if linkage_start < 0 and re.search(r"\bLINKAGE\s+SECTION\b", up):
            linkage_start = i
        if proc_start < 0 and re.search(r"\bPROCEDURE\s+DIVISION\b", up):
            proc_start = i

    # 提取 PROCEDURE DIVISION USING 入参（可能跨多有效行直到遇到句点）
    if proc_start >= 0:
        collected: list[str] = []
        for raw in raw_lines[proc_start:]:
            eff = _effective(raw)
            if eff is None:
                continue
            collected.append(eff)
            if "." in eff:
                break
        joined = " ".join(collected)
        m = re.search(r"\bUSING\b(.+?)\.", joined, re.IGNORECASE)
        if m:
            using = [t.strip() for t in m.group(1).split() if t.strip()]

    return {
        "program_id": program_id,
        "ws_start": ws_start,
        "linkage_start": linkage_start,
        "proc_start": proc_start,
        "using": using,
    }


def extract_copies(raw_lines: list[str], ws_start: int, ws_end: int) -> list[str]:
    """收集 WORKING-STORAGE 范围内的有效 COPY 名（跳过停用/注释），保序去重。"""
    names: list[str] = []
    for i in range(ws_start, ws_end):
        eff = _effective(raw_lines[i])
        if eff is None:
            continue
        m = _COPY_RE.search(eff)
        if m:
            names.append(m.group(1).rstrip(".").upper())
    return list(dict.fromkeys(names))


def classify_copies(names: list[str]) -> dict:
    """COPY 分类（设计文档 §3 规则③）：rec_skm / varcom / other。"""
    rec_skm, varcom, other = [], [], []
    for n in names:
        if "VARCOM" in n:
            varcom.append(n)
        elif n.endswith("REC") or n.endswith("SKM"):
            rec_skm.append(n)
        else:
            other.append(n)
    return {"rec_skm": rec_skm, "varcom": varcom, "other": other}
