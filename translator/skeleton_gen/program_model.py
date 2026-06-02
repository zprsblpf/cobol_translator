"""
骨架要素抽取：CobolProgram → SkeletonModel（步骤05 §6.2）。

用途：把解析器产出的 CobolProgram 收敛为骨架引擎需要的最小要素
      （program_id、类名、包名、USING 入参、COPY 清单、各 SECTION 名/方法名/行号/PERFORM）。
对应设计：docs/详细设计/步骤05-cob到Java翻译引擎详细设计.md。

设计思路：渲染层只依赖本数据模型，不直接碰 CobolProgram 的全部字段，降低耦合；
          SECTION→方法名复用既有 translator.skeleton._section_to_method（去重安全，见 §2-7）。
"""
from __future__ import annotations

from dataclasses import dataclass

from config import spec_loader
from translator.skeleton import _section_to_method


@dataclass
class SectionModel:
    """一个 SECTION 的骨架要素。"""
    cobol_name: str          # COBOL SECTION 原名（如 1000-INITIALISE）
    method: str              # Java 方法名（如 initialise1000）
    performs: list[str]      # 本段 PERFORM 目标（COBOL 名）
    line_start: int          # 原文件起始行
    line_end: int            # 原文件结束行
    go_tos: list[str]        # GO TO 目标（高风险，渲染时标注）
    body_lines: list[str]    # 段体原始代码行（去行号前缀），步骤07 方法体翻译用


@dataclass
class SkeletonModel:
    """整个 cob 程序的骨架模型。"""
    program_id: str          # PROGRAM-ID
    class_name: str          # 主类名（Zpoldwnm）
    wsaa_class: str          # WS 容器类名（ZpoldwnmWsaa）
    package: str             # Java 包名（程序名小写）
    using: list[str]         # PROCEDURE DIVISION USING 入参（COBOL 名）
    copies: list[str]        # COPY 引用清单
    sections: list[SectionModel]


def build_model(program) -> SkeletonModel:
    """从 CobolProgram 抽取骨架要素，组装为 SkeletonModel。"""
    base = spec_loader.class_name(program.program_id)
    sections = [
        SectionModel(
            cobol_name=s.name,
            method=_section_to_method(s.name),
            performs=list(s.performs),
            line_start=s.line_start,
            line_end=s.line_end,
            go_tos=list(s.go_tos),
            body_lines=list(s.lines),
        )
        for s in program.sections
    ]
    return SkeletonModel(
        program_id=program.program_id,
        class_name=base,
        wsaa_class=f"{base}Wsaa",
        package=program.program_id.lower(),
        using=list(program.linkage_using),
        copies=list(program.copy_refs),
        sections=sections,
    )
