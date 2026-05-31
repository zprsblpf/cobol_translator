"""
WORKING-STORAGE 结构模型（确定性翻译用）。

对应设计：docs/详细设计/步骤03-WSAA块翻译设计.md。
本模块只定义数据结构，不含解析逻辑：
- `Condition`：一个 88 条件名 + 其取值列表（IF 条件式的来源）。
- `WsNode`：WORKING-STORAGE 层级树的一个节点（01/03/05/07/09 数据项或组）。
  字段含义见各属性注释；树由 parser.ws.tree 按 level 建立，长度/类型回填后供渲染。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Condition:
    """一个 88 条件名。code 用法：IF <name> → <cobol_var> 属于 values 之一。"""
    name: str                       # 88 条件名（COBOL 原名）
    values: list[str]               # 取值字面量列表（已去引号），如 ['6PWB']
    is_boolean: bool = False        # VALUE B'0'/B'1'（INDICATOR 布尔条件）
    bool_value: bool = False        # is_boolean 时的目标布尔值


@dataclass
class WsNode:
    """WORKING-STORAGE 层级树节点（数据项 / 组项）。"""
    level: int                      # 01/03/05/07/09…
    name: str                       # COBOL 原名（FILLER 亦保留，用于占位/偏移）
    pic: str = ""                   # PIC 字符串（组项为空）
    comp: str = ""                  # COMP / COMP-3 / ""
    occurs: int = 0                 # OCCURS n，0=无
    redefines: str = ""             # REDEFINES 目标 COBOL 名，""=无
    value_raw: str = ""             # VALUE 子句原文（去 PIC/前导关键字），未含值=""
    has_value: bool = False         # 是否带 VALUE 子句
    is_filler: bool = False         # FILLER 占位符
    is_indicator: bool = False      # INDICATOR（PIC 1）
    raw: str = ""                   # 合并后的原始定义行（调试/注释用）

    conditions: list[Condition] = field(default_factory=list)  # 挂在本项上的 88
    children: list["WsNode"] = field(default_factory=list)     # 子项（组）

    # ── 回填字段（由 pic/tree 计算）──
    java_type: str = "String"       # String/int/long/BigDecimal/boolean
    is_edited: bool = False         # 数字编辑 PIC（Z/*/插入字符）→ 显示串
    byte_len: int = 0               # 单次出现的字符宽度（视图切片用）

    @property
    def is_group(self) -> bool:
        return not self.pic

    @property
    def is_condition_holder(self) -> bool:
        return bool(self.conditions)
