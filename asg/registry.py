"""
相2 ASG —— 过程注册表 ProcRegistry + 符号表 SymbolTable（引用解析的数据基座）。

对应设计：docs/详细设计/步骤17-旁路建相2-ASG设计.md §2.2。
复用：translator.skeleton_gen.body_context._build_proc_order（步骤13 四元，只读调用，不改其源）。

用法：
    from asg.registry import build
    proc, sym = build(program)            # program = parser.cobol_parser.CobolProgram
    ref = proc.resolve("3190-EXIT")       # → ProcRef(name, unit)
    units = proc.resolve_thru("A", "B")   # → [ProcUnit, ...] 闭区间
"""
from __future__ import annotations

from dataclasses import dataclass

from translator.skeleton_gen.body_context import _build_proc_order


@dataclass
class ProcUnit:
    """一个可被 PERFORM/GO TO 的过程单元（proc_order 四元的对象化，步骤13 转正）。"""
    name: str        # 大写过程名
    kind: str        # section | paragraph
    section: str     # 所属 SECTION（大写）
    order: int       # 在 proc_order 中的物理序号（供 THRU 区间按序取）


@dataclass
class ProcRef:
    """引用解析结果：名 + 解析到的单元（解析失败 unit=None，兜底不臆测）。"""
    name: str
    unit: ProcUnit | None = None


class ProcRegistry:
    """过程注册表：按名/按 THRU 区间解析 PERFORM、GO TO 目标。

    设计思路：相2 把「全程序过程拓扑」一次性算清，相3 visitor 只查表，
    不再像 rules 那样到处临时建索引（初步设计 §1/§6）。"""

    def __init__(self, units: list[ProcUnit]):
        self._units = units
        self._by_name: dict[str, ProcUnit] = {}
        for u in units:
            self._by_name.setdefault(u.name, u)   # 同名取首现（与源码物理顺序一致）

    def resolve(self, name: str | None) -> ProcRef:
        """按名解析单个过程目标；查不到 unit=None。"""
        key = name.upper() if name else ""
        return ProcRef(name=key, unit=self._by_name.get(key))

    def resolve_thru(self, a: str | None, b: str | None) -> list[ProcUnit]:
        """PERFORM a THRU b → 按 order 取 [a..b] 闭区间过程单元（THRU 区间一次算清）。

        a 解析不到 → []；b 缺失/早于 a → 退化为单元 [a]（保守，不臆测区间）。"""
        ua = self._by_name.get(a.upper()) if a else None
        if ua is None:
            return []
        ub = self._by_name.get(b.upper()) if b else None
        if ub is None or ub.order < ua.order:
            return [ua]
        return [u for u in self._units if ua.order <= u.order <= ub.order]

    @property
    def units(self) -> list[ProcUnit]:
        return list(self._units)


class SymbolTable:
    """符号表：数据名 → 变量定义项(DDE)，供相3 判型/前缀（本步先建表，单点 visitor 暂不用）。

    作用域决定（§9-Q3）：COBOL WS/LINKAGE 程序级全局 → 单层扁平表、大小写不敏感；
    GROUP 嵌套 / REDEFINES 别名视图留后续（§7-Q1）。"""

    def __init__(self, variables: list):
        self._by_name: dict[str, object] = {}
        for v in variables:
            self._by_name.setdefault(v.name.upper(), v)

    def lookup(self, name: str | None):
        return self._by_name.get(name.upper()) if name else None


def build(program) -> tuple[ProcRegistry, SymbolTable]:
    """CobolProgram → (ProcRegistry, SymbolTable)。复用 _build_proc_order 四元 + Variable 列表。"""
    quad = _build_proc_order(program)   # [(name, kind, section, body_lines), ...]
    units = [ProcUnit(name=n, kind=k, section=s, order=i)
             for i, (n, k, s, _body) in enumerate(quad)]
    proc = ProcRegistry(units)
    sym = SymbolTable(list(program.working_storage) + list(program.linkage_vars))
    return proc, sym
