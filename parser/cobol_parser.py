"""
COBOL 解析器：将 .cob 文件拆分为结构化数据，无需 LLM。
支持 AS/400 COBOL 格式（固定列格式，列7-72为代码区）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from parser import cobol_columns
from preprocess.line_stream import CleanSource, build as _build_clean


# ── 数据结构 ──────────────────────────────────────────────────────────────────

@dataclass
class Variable:
    level: int               # 01, 03, 05...
    name: str                # 变量名（原始 COBOL 名）
    pic: str                 # PIC 字符串，如 X(08) / S9(15)V9(2)
    comp: str                # COMP-3 / COMP / ""
    occurs: int              # OCCURS n TIMES，0 表示无
    redefines: str           # REDEFINES 的目标变量名，"" 表示无
    is_group: bool           # 是否为 GROUP（无 PIC）
    children: list[Variable] = field(default_factory=list)
    raw_line: str = ""


@dataclass
class CobolSection:
    name: str                # SECTION 名，如 "1000-INIT"
    lines: list[str]         # 原始代码行（去掉行号前缀）
    performs: list[str]      # 本 SECTION 中的 PERFORM 目标
    calls: list[str]         # CALL 'XXXIO' 列表
    go_tos: list[str]        # GO TO 目标（高风险）
    line_start: int          # 在原文件中的起始行号
    line_end: int            # 结束行号


@dataclass
class CobolProgram:
    program_id: str
    source_file: str
    working_storage: list[Variable]
    linkage_vars: list[Variable]
    linkage_using: list[str]         # PROCEDURE DIVISION USING 后的参数名
    sections: list[CobolSection]
    copy_refs: list[str]
    total_lines: int

    def get_section(self, name: str) -> CobolSection | None:
        name_upper = name.upper()
        for s in self.sections:
            if s.name.upper() == name_upper:
                return s
        return None

    def summary(self) -> dict:
        risk_sections = [s for s in self.sections if s.go_tos]
        redefines_vars = [v for v in self.working_storage if v.redefines]
        return {
            "program_id": self.program_id,
            "total_lines": self.total_lines,
            "sections": len(self.sections),
            "variables": len(self.working_storage),
            "linkage_params": self.linkage_using,
            "copy_refs": len(self.copy_refs),
            "risk_go_to_sections": len(risk_sections),
            "redefines_count": len(redefines_vars),
        }


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _strip_cobol_line(raw: str) -> str:
    """净化一物理行 —— 薄委托相1 `CleanSource.strip_line`（步骤15 绞杀接线，逻辑不变）。

    停用('!!!!!!')/注释('* /')/调试('D')行返回 ''，其余取代码区（第7列起）。
    """
    return CleanSource.strip_line(raw)


def _clean_lines(raw_lines: list[str]) -> list[tuple[int, str]]:
    """返回 (原始行号, 净化后的代码) 列表 —— 薄委托相1 `build(...).as_pairs()`（步骤15，逻辑不变）。"""
    return _build_clean(raw_lines).as_pairs()


# ── 变量解析 ──────────────────────────────────────────────────────────────────

_PIC_RE = re.compile(
    r"PIC(?:TURE)?\s+(S?9[\d()\s]*V?9?[\d()\s]*|X[\d()\s]*|[XA9]+)",
    re.IGNORECASE,
)
_LEVEL_RE = re.compile(r"^\s*(\d{2})\s+(\S+)", re.IGNORECASE)
_OCCURS_RE = re.compile(r"OCCURS\s+(\d+)", re.IGNORECASE)
_REDEFINES_RE = re.compile(r"REDEFINES\s+(\S+)", re.IGNORECASE)
_COMP_RE = re.compile(r"(COMP(?:-3)?)", re.IGNORECASE)


def _parse_variable_line(line: str) -> Variable | None:
    """解析单个变量定义行（可能跨多行，调用前需先合并续行）。"""
    m = _LEVEL_RE.match(line)
    if not m:
        return None
    level = int(m.group(1))
    name = m.group(2).rstrip(".")

    if name.upper() in ("FILLER", "88"):
        return None

    pic_m = _PIC_RE.search(line)
    pic = pic_m.group(1).replace(" ", "") if pic_m else ""

    occurs_m = _OCCURS_RE.search(line)
    occurs = int(occurs_m.group(1)) if occurs_m else 0

    redefines_m = _REDEFINES_RE.search(line)
    redefines = redefines_m.group(1) if redefines_m else ""

    comp_m = _COMP_RE.search(line)
    comp = comp_m.group(1).upper() if comp_m else ""

    return Variable(
        level=level,
        name=name,
        pic=pic,
        comp=comp,
        occurs=occurs,
        redefines=redefines,
        is_group=(not pic),
        raw_line=line.strip(),
    )


def _parse_variables(lines: list[str]) -> list[Variable]:
    """解析 WORKING-STORAGE / LINKAGE SECTION 中的变量定义。"""
    # 合并续行（以数字开头的新变量声明才是新行）
    merged: list[str] = []
    current = ""
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # 新变量行：以两位数字开头
        if re.match(r"^\s*\d{2}\s+", line):
            if current:
                merged.append(current)
            current = stripped
        else:
            current += " " + stripped
    if current:
        merged.append(current)

    variables = []
    for line in merged:
        var = _parse_variable_line(line)
        if var:
            variables.append(var)
    return variables


# ── SECTION 解析 ──────────────────────────────────────────────────────────────

_SECTION_RE = re.compile(
    r"^\s*([A-Z0-9][A-Z0-9\-]*)\s+SECTION\s*\.",
    re.IGNORECASE,
)
_PERFORM_RE = re.compile(
    r"\bPERFORM\s+([A-Z0-9][A-Z0-9\-]+)(?:\s+THRU\s+[A-Z0-9][A-Z0-9\-]+)?",
    re.IGNORECASE,
)
_CALL_RE = re.compile(r"\bCALL\s+'([^']+)'", re.IGNORECASE)
_GOTO_RE = re.compile(r"\bGO\s+TO\s+([A-Z0-9][A-Z0-9\-]+)", re.IGNORECASE)


def _parse_sections(
    raw_lines: list[str],
    proc_start: int,
) -> list[CobolSection]:
    """从 PROCEDURE DIVISION 开始，解析所有 SECTION。"""
    sections: list[CobolSection] = []
    current_name = ""
    current_lines: list[str] = []
    current_start = proc_start

    def flush(end_line: int):
        if not current_name:
            return
        section_code = "\n".join(current_lines)
        performs = list({m.group(1).upper() for m in _PERFORM_RE.finditer(section_code)})
        calls = list({m.group(1).upper() for m in _CALL_RE.finditer(section_code)})
        go_tos = list({m.group(1).upper() for m in _GOTO_RE.finditer(section_code)})
        sections.append(CobolSection(
            name=current_name,
            lines=current_lines[:],
            performs=performs,
            calls=calls,
            go_tos=go_tos,
            line_start=current_start,
            line_end=end_line,
        ))

    for i, raw in enumerate(raw_lines[proc_start:], proc_start + 1):
        clean = _strip_cobol_line(raw)
        if not clean.strip():
            continue

        m = _SECTION_RE.match(clean)
        if m:
            flush(i - 1)
            current_name = m.group(1).upper()
            current_lines = []
            current_start = i
        else:
            current_lines.append(clean)

    flush(len(raw_lines))
    return sections


# ── 主入口 ────────────────────────────────────────────────────────────────────

def parse(cob_file: str | Path) -> CobolProgram:
    """解析 COBOL 文件，返回结构化 CobolProgram。"""
    path = Path(cob_file)
    with open(path, encoding="utf-8", errors="replace") as f:
        raw_lines = f.readlines()

    total_lines = len(raw_lines)
    upper_lines = [l.upper() for l in raw_lines]

    # 1. 提取 PROGRAM-ID
    program_id = "UNKNOWN"
    for line in upper_lines[:20]:
        m = re.search(r"PROGRAM-ID\.\s+(\S+)", line)
        if m:
            program_id = m.group(1).rstrip(".")
            break

    # 2. 定位各 DIVISION 的起始行
    def find_division(keyword: str) -> int:
        for i, line in enumerate(upper_lines):
            if re.search(rf"\b{keyword}\s+DIVISION\b", line):
                return i
        return -1

    ws_start = -1
    linkage_start = -1
    proc_start = -1

    for i, line in enumerate(upper_lines):
        # DIVISION/SECTION 标记必须在代码区判定：注释区(第7列 '*')里出现的 "procedure division"
        # 等字样是英文散文、非语法标记。复用定列正本 cobol_columns 剔除注释/停用行后再匹配，
        # 否则 proc_start 会被注释行误命中 → 数据段被当过程段（架构演进初步设计 §7 / 步骤14 §1）。
        if cobol_columns.is_comment(raw_lines[i]) or cobol_columns.is_deactivated(raw_lines[i]):
            continue
        if re.search(r"\bWORKING-STORAGE\s+SECTION\b", line) and ws_start < 0:
            ws_start = i + 1
        if re.search(r"\bLINKAGE\s+SECTION\b", line) and linkage_start < 0:
            linkage_start = i + 1
        if re.search(r"\bPROCEDURE\s+DIVISION\b", line) and proc_start < 0:
            proc_start = i

    # 3. 解析 WORKING-STORAGE
    ws_end = linkage_start if linkage_start > 0 else (proc_start if proc_start > 0 else total_lines)
    ws_lines = [_strip_cobol_line(raw_lines[i]) for i in range(ws_start, ws_end)]
    working_storage = _parse_variables(ws_lines)

    # 4. 解析 LINKAGE SECTION
    linkage_end = proc_start if proc_start > 0 else total_lines
    if linkage_start > 0:
        linkage_lines = [_strip_cobol_line(raw_lines[i]) for i in range(linkage_start, linkage_end)]
        linkage_vars = _parse_variables(linkage_lines)
    else:
        linkage_vars = []

    # 5. 提取 PROCEDURE DIVISION USING 参数
    linkage_using: list[str] = []
    if proc_start >= 0:
        proc_line = " ".join(
            _strip_cobol_line(raw_lines[j]) for j in range(proc_start, min(proc_start + 3, total_lines))
        )
        using_m = re.search(r"\bUSING\b(.+?)(?:\.|$)", proc_line, re.IGNORECASE)
        if using_m:
            linkage_using = [t.strip() for t in using_m.group(1).split() if t.strip()]

    # 6. 解析所有 SECTION
    sections = _parse_sections(raw_lines, proc_start) if proc_start >= 0 else []

    # 7. 收集 COPY 引用
    copy_refs: list[str] = []
    for line in upper_lines:
        if cobol_columns.is_deactivated(line):   # 跳过 '!!!!!!' 停用行的 COPY
            continue
        m = re.search(r"\bCOPY\s+(\S+)", line)
        if m:
            copy_refs.append(m.group(1).rstrip("."))

    return CobolProgram(
        program_id=program_id,
        source_file=str(path),
        working_storage=working_storage,
        linkage_vars=linkage_vars,
        linkage_using=linkage_using,
        sections=sections,
        copy_refs=list(dict.fromkeys(copy_refs)),  # 去重保序
        total_lines=total_lines,
    )


if __name__ == "__main__":
    import sys, json

    if len(sys.argv) < 2:
        print("用法: python cobol_parser.py <file.cob>")
        sys.exit(1)

    prog = parse(sys.argv[1])
    summary = prog.summary()
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if "--sections" in sys.argv:
        for s in prog.sections[:10]:
            print(f"\n[{s.name}] ({s.line_start}-{s.line_end}) "
                  f"PERFORM={s.performs[:3]} CALL={s.calls} GOTO={s.go_tos}")
