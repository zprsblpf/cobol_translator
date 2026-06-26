"""
相3 叶子翻译公用底座 —— 控制流动词（EVALUATE switch 壳 + GO/GOBACK/STOP/EXIT/CONTINUE/NEXT）。

对应设计：docs/详细设计/步骤23-绞杀项3⑥控制流动词EVALUATE-GOTO迁visitor设计.md §3。
设计思路：rules 骨架层 `_sk_control` 的 **flow_label-无关分支** 与 `_sk_evaluate` 的 **switch 壳判定**
自 translator/rules.py **原样迁址**（逻辑零改），下沉为 leaf 形态纯函数——rules 委托、相3 visitor
（visit_GotoStmt/visit_EvaluateStmt/visit_Leaf）共调 → 两路产物逐字符一致（绞杀项3 比对闸基础）。

**守界（设计 §1 非目标）**：dispatch 模式（`__pc="x"; continue FLOW` / `break FLOW`，依赖
flow_label/flow_paragraphs 骨架装配态）**不在本层**——`translate_control` 复刻 flow_label=None 分支，
比对只在 flow_label=None ctx 下成立；dispatch 留骨架装配迁 visitor 刀。

leaf 形态：产**裸行**（无缩进），缩进由调用方（visitor `_body` / rules `_ind`）各自施加。
复用 leaf.expr 的 `_operand`；ctx 读 `known_sections`/`section_to_method`（步骤23 扩入 LeafCtx 契约）。
依赖单向：rules / asg.visitor → leaf.control → leaf.expr，无环。
"""
from __future__ import annotations

from translator.leaf.context import LeafCtx
from translator.leaf.expr import _operand


def translate_control(tokens: list[str], ctx: LeafCtx) -> tuple[list[str], bool]:
    """控制流叶子词译器（复刻 rules._sk_control 的 flow_label-无关分支）：

      · GO TO target：target…EXIT → return；known_section → TODO-GOTO + proc_call + return；
        未知段 → TODO-GOTO + return；无 target → return。
      · GOBACK/STOP → return；EXIT（非 dispatch）→ return; // EXIT；CONTINUE → ; // CONTINUE；NEXT → ; // NEXT SENTENCE。
      · 非控制词 → ([], False)。含 try/except (ValueError, IndexError) 兜底，与旧 _dispatch 同形。

    裸行输出（无 _ind）；dispatch 分支（flow_label 真）不在本函数，由 rules._sk_control 保留处理。
    """
    if not tokens:
        return [], False
    toks = [t.upper() for t in tokens]
    first = toks[0]
    try:
        if first == "GO":
            target = None
            for t in toks:
                if t not in ("GO", "TO"):
                    target = t
                    break
            if target and target.endswith("EXIT"):
                return [f"return;  // GO TO {target}"], True
            if target:
                line = f"// TODO-GOTO: 跳转 {target}，需人工核对控制流"
                if target in ctx.known_sections:
                    return [line, f"this.{ctx.section_to_method(target)}();", "return;"], True
                return [line, "return;"], True
            return ["return;"], True
        if first in ("GOBACK", "STOP"):
            return ["return;"], True
        if first == "EXIT":
            return ["return;  // EXIT"], True
        if first == "CONTINUE":
            return [";  // CONTINUE"], True
        if first == "NEXT":
            return [";  // NEXT SENTENCE"], True
    except (ValueError, IndexError):
        return [], False
    return [], False


def translate_evaluate(subject_tokens: list[str], ctx: LeafCtx) -> str | None:
    """EVALUATE switch 主体判定（复刻 rules._sk_evaluate 的 subject 段）：

    单 token 且非 TRUE → `f"{_operand(tok)}.trim()"`（供 `switch (…) {`）；
    多 token / EVALUATE TRUE / 空 → None（交 LLM，_sk_evaluate 既有边界）。
    """
    if not subject_tokens:
        return None
    if " ".join(subject_tokens).strip().upper() in ("TRUE", ""):
        return None
    if len(subject_tokens) != 1:
        return None
    return f"{_operand(subject_tokens[0], ctx)}.trim()"


def evaluate_case_label(cond_tokens: list[str], ctx: LeafCtx) -> str:
    """EVALUATE 单条 WHEN 的 case 标签（复刻 _sk_evaluate WHEN 分支）：
    OTHER/空 → `default`；否则 `case {_operand(cond[0])}`。供 visitor 与 rules 共渲、逐字符一致。"""
    if " ".join(cond_tokens).upper() in ("OTHER", ""):
        return "default"
    val = _operand(cond_tokens[0], ctx) if cond_tokens else '""'
    return f"case {val}"
