"""
88 条件项 → Java 布尔方法。

对应设计：docs/详细设计/步骤03-WSAA块翻译设计.md。

设计思路：88 描述「某字段取某些值时为真」（IF IS-6PWB → wsaaVal28Prd ∈ {'6PWB'}）。
固化为 `public boolean is6pwb(){ return wsaaVal28Prd.equals("6PWB"); }`，多值用 || 串联。
INDICATOR 布尔（VALUE B'0'/B'1'）需结合数组下标，暂留 TODO。
"""
from __future__ import annotations

from parser.ws.model import WsNode, Condition
from translator.wsaa.render_field import java_name


def render_conditions(holder: WsNode) -> list[str]:
    """渲染挂在 holder 上的全部 88 条件方法。"""
    field = java_name(holder.name)
    out: list[str] = []
    for c in holder.conditions:
        out.extend(_render_one(field, c))
    return out


def _render_one(field: str, c: Condition) -> list[str]:
    mname = java_name(c.name)
    if c.is_boolean:
        return [f"    // TODO 88(INDICATOR) {c.name}: 需结合 {field} 下标判断 "
                f"(B'{int(c.bool_value)}')"]
    if not c.values:
        return [f"    // TODO 88 {c.name}: 无取值"]
    checks = " || ".join(f'{field}.equals("{v}")' for v in c.values)
    return [f"    public boolean {mname}() {{ return {checks}; }}"]
