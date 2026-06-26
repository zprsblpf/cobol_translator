"""
相3 叶子翻译公用底座 —— LeafCtx 上下文契约（窄协议）。

对应设计：docs/详细设计/步骤18-绞杀项3①MOVE迁visitor设计.md §3.2。
设计思路：叶子译器（translate_move 及表达式底座）只读取 ctx 的若干「判型/结构体命名」字段，
不依赖 rules.Ctx 的 skeleton 层状态（new_leaf/leaves/flow_label…）。故用 typing.Protocol
声明窄契约——rules.Ctx 与 body_context.build_body_ctx 产物均结构化（duck-type）满足它，
两路（旧 rules / 相3 visitor）共用同一份叶子翻译逻辑而无需共享整个 Ctx。
"""
from __future__ import annotations

from typing import Protocol


class LeafCtx(Protocol):
    """叶子译器读取的上下文契约（见 expr.py / move.py 的 ctx 取值）。"""
    field_type_map: dict          # java 基名 → {type: int/long/BigDecimal/String, ...}（判型）
    io_struct_prefixes: set       # 结构体（拷贝簿）前缀大写集
    struct_objects: dict          # 前缀 → Java 对象名
    struct_classes: dict          # 前缀 → Java 类名
    struct_getter: str            # 字段读取访问器前缀（默认 "get"）
    struct_setter: str            # 字段写入访问器前缀（默认 "set"）
    struct_default_suffix: str    # 无显式类名映射时的兜底后缀（默认 "Params"）
    struct_function: dict         # 运行时跟踪：前缀 → 最近功能码（MOVE …TO X-FUNCTION 写入）
    # ── CALL 散点兜底翻译读取的 IO 子程序映射（步骤21 绞杀项3④；由 io_mappings.yaml 驱动）──
    io_programs: dict             # CALL 'xxxIO' 映射，名 → info（合并 io_programs+io_programs2）
    io_default_pattern: dict      # *IO 查表派生范式（class_suffix / operations 等）
    date_programs: dict           # 日期子程序映射，名 → info
    system_programs: dict         # 系统子程序映射（SYSERR 等），名 → info
