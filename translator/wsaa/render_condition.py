"""
88 条件项 → Java 布尔方法。

对应设计：docs/详细设计/步骤03-WSAA块翻译设计.md。

设计思路：88 描述「某字段取某些值时为真」（IF IS-6PWB → wsaaVal28Prd ∈ {'6PWB'}）。
固化为 `public boolean is6pwb(){ return wsaaVal28Prd.equals("6PWB"); }`，多值用 || 串联。
INDICATOR 布尔（VALUE B'0'/B'1'）：holder 为 boolean[] 数组（indexed）时生成带下标布尔访问器
`indOn(int i)`/`indOff(int i)`（COBOL OCCURS 从 1，数组用 i-1）；非数组退化 TODO。
"""
from __future__ import annotations

from parser.ws.model import WsNode, Condition
from translator.wsaa.render_field import java_name


def render_conditions(holder: WsNode, indexed: bool = False) -> list[str]:
    """渲染挂在 holder 上的全部 88 条件方法。indexed=holder 处数组上下文（boolean[]）。"""
    field = java_name(holder.name)
    out: list[str] = []
    for c in holder.conditions:
        out.extend(_render_one(field, c, indexed))
    return out


def _render_one(field: str, c: Condition, indexed: bool) -> list[str]:
    mname = java_name(c.name)
    if c.is_boolean:
        if not indexed:
            return [f"    // TODO 88(INDICATOR) {c.name}: holder {field} 非数组，需人工核对 "
                    f"(B'{int(c.bool_value)}')"]
        expr = f"{field}[i - 1]" if c.bool_value else f"!{field}[i - 1]"
        return [f"    public boolean {mname}(int i) {{ return {expr}; }}"]
    if not c.values:
        return [f"    // TODO 88 {c.name}: 无取值"]
    checks = " || ".join(f'{field}.equals("{v}")' for v in c.values)
    return [f"    public boolean {mname}() {{ return {checks}; }}"]
