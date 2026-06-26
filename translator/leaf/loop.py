"""
相3 叶子翻译公用底座 —— PERFORM 循环子句翻译（translate_perform_loop）。

对应设计：docs/详细设计/步骤20-绞杀项3③PERFORM循环子句迁visitor设计.md §3。
来源：原 translator/rules.py `_perform_loop` / `_has_test_after` / `_parse_varying_clauses`
      **原样迁址**（逻辑零改，仅把 ctx 注解由 rules.Ctx 改为 LeafCtx）。
被 PERFORM（asg.visitor.visit_PerformStmt）、rules（_sk_perform）共用同一份 → 循环壳产物逐字符一致
（绞杀项3 比对闸基础）。依赖单向 leaf.loop → leaf.expr / leaf.cond，不反向依赖 rules。

范围（设计 §1）：只切「循环子句翻译」——UNTIL/TIMES/VARYING/TEST AFTER → while/for/do-while/嵌套 for。
THRU 区间 / 目标解析（②）、BEGN foreach + struct_rebind（③）属骨架装配层，仍留 rules。
"""
from __future__ import annotations

from translator.leaf.context import LeafCtx
from translator.leaf.expr import _operand
from translator.leaf.cond import translate_condition as _try_condition


def _ind(n: int) -> str:
    return "    " * n


def _has_test_after(hu: list) -> bool:
    """WITH TEST AFTER 检测：TEST 紧跟 AFTER（区别于 VARYING 的 AFTER——后者前邻 UNTIL 条件）。"""
    return any(hu[i] == "TEST" and i + 1 < len(hu) and hu[i + 1] == "AFTER" for i in range(len(hu)))


def _parse_varying_clauses(header: list, hu: list, ctx: LeafCtx):
    """把 VARYING…AFTER… 切成子句序列 [(v, a, b, cond), …]（步骤16 §2.3，D16-2 任意层）。
    每子句 <var> FROM <a> BY <b> UNTIL <cond>，cond 自 UNTIL 后延至下一 AFTER/header 末。
    任一子句兜不住 → None（调用方落 LLM，all-or-nothing，D16-3）。"""
    starts = [i for i, t in enumerate(hu) if t in ("VARYING", "AFTER")] + [len(header)]
    clauses = []
    for s in range(len(starts) - 1):
        seg = header[starts[s] + 1: starts[s + 1]]   # VARYING/AFTER 关键字后到下一子句前
        su = [t.upper() for t in seg]
        try:
            v = _operand(seg[0], ctx)
            a = _operand(seg[su.index("FROM") + 1], ctx)
            b = _operand(seg[su.index("BY") + 1], ctx)
            cond = _try_condition(seg[su.index("UNTIL") + 1:], ctx)
        except (ValueError, IndexError):
            return None
        if cond is None:
            return None
        clauses.append((v, a, b, cond))
    return clauses


def _perform_loop(header: list, hu: list, ctx: LeafCtx, indent: int):
    """PERFORM 循环子句 → (open_lines, close_lines)。无循环 → ([], [])；兜不住 → None（落 LLM 叶子）。
    步骤16：WITH TEST AFTER→do-while（仅无 VARYING，D16-1）；VARYING…AFTER→嵌套 for（D16-2）；UNTIL/TIMES 基本形不变。"""
    test_after = _has_test_after(hu)
    if "VARYING" in hu:
        if test_after:
            return None                       # D16-1：VARYING+TEST AFTER 保守落 LLM，不臆造
        clauses = _parse_varying_clauses(header, hu, ctx)
        if clauses is None:
            return None
        open_lines, close_lines = [], []
        for k, (v, a, b, cond) in enumerate(clauses):
            open_lines.append(f"{_ind(indent + k)}for ({v} = {a}; !({cond}); {v} = {v} + {b}) {{")
            close_lines.insert(0, f"{_ind(indent + k)}}}")
        return open_lines, close_lines
    if "UNTIL" in hu:
        cond = _try_condition(header[hu.index("UNTIL") + 1:], ctx)
        if cond is None:
            return None
        if test_after:                        # do { … } while (!(cond));
            return [f"{_ind(indent)}do {{"], [f"{_ind(indent)}}} while (!({cond}));"]
        return [f"{_ind(indent)}while (!({cond})) {{"], [f"{_ind(indent)}}}"]
    if "TIMES" in hu:
        ti = hu.index("TIMES")
        cnt = _operand(header[ti - 1], ctx) if ti > 0 else "1"
        return [f"{_ind(indent)}for (int _i = 0; _i < {cnt}; _i++) {{"], [f"{_ind(indent)}}}"]
    return [], []


def translate_perform_loop(header: list, ctx: LeafCtx, indent: int):
    """公开门面：免传 hu（内部计算大写视图）。visitor / 比对闸调本函数，rules 直调 _perform_loop（保旧名）。"""
    hu = [h.upper() for h in header]
    return _perform_loop(header, hu, ctx, indent)
