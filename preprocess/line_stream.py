"""
相1 预处理产物：「干净行流」CleanSource（带原始行号回溯）。

对应设计：docs/详细设计/步骤15-相1预处理独立成相设计.md §2.2。

职责：把 COBOL 物理行流净化为「去注释/停用/空行后的有效行流」，并保留每行的原始物理行号，
作为相1 对外的核心产物，供旧 cobol_parser / 后续相2 消费、回溯。逻辑搬自原
`parser/cobol_parser.py` 的 `_strip_cobol_line` / `_clean_lines`，仅把产物从裸 tuple 升级为对象。
"""
from __future__ import annotations

from dataclasses import dataclass

from preprocess import columns, dialect


@dataclass
class CleanLine:
    """一条有效代码行的回溯单元：原始物理行号（1-based）+ 净化后代码区文本。"""
    lineno: int
    code: str


@dataclass
class CleanSource:
    """相1 对一份源文件的完整产物。

    - raw_lines：原始物理行（保留，供仍需原始索引的旧逻辑回溯，是「零行为变化」的关键）；
    - clean_lines：去注释/停用/空行后的有效行流（即旧 `_clean_lines` 产物，升级为对象）；
    - total_lines：物理总行数。
    """
    raw_lines: list[str]
    clean_lines: list[CleanLine]
    total_lines: int

    @staticmethod
    def strip_line(raw: str) -> str:
        """净化一物理行：停用('!!!!!!')/注释('* /')/调试('D')行返回 ''，其余取代码区并做方言归一。

        列处理复用相1 正本 columns.*；代码行再过 dialect.normalize（GO→GO TO 等，规则源自 config，
        步骤16）。停用/注释/调试行不进归一（注释里的散文不受影响）。
        """
        if columns.is_deactivated(raw) or columns.is_comment(raw) or columns.is_debug(raw):
            return ""
        return dialect.normalize(columns.clean_line(raw))

    def as_pairs(self) -> list[tuple[int, str]]:
        """把 clean_lines 摊回 (原始行号, 代码) 元组列表，为旧调用方提供零改动适配。"""
        return [(cl.lineno, cl.code) for cl in self.clean_lines]


def build(raw_lines: list[str]) -> CleanSource:
    """遍历物理行，逐行 strip_line，非空者收为 CleanLine，组装 CleanSource。

    等价搬自原 cobol_parser._clean_lines（返回 (行号, 代码)），仅产物升级为对象。
    """
    clean: list[CleanLine] = []
    for i, raw in enumerate(raw_lines, 1):
        code = CleanSource.strip_line(raw)
        if code.strip():
            clean.append(CleanLine(lineno=i, code=code))
    return CleanSource(raw_lines=list(raw_lines), clean_lines=clean, total_lines=len(raw_lines))
