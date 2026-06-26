# 步骤23　绞杀项3⑥ 控制流动词 EVALUATE/GOTO 迁 visitor 操作记录

状态：🟢已实现（2026-06-26）
对应设计：`../详细设计/步骤23-绞杀项3⑥控制流动词EVALUATE-GOTO迁visitor设计.md`（✅已认可，单文件 control.py）

---

## 1. 讨论与决策脉络（Why）

- 承步骤18–22 同范式第六刀，迁控制流动词。探查结论（设计 §3.1 留痕）：`_sk_control`/`_sk_evaluate` 属
  **骨架层** `(st,ctx,indent)` 形态，其中 **GO dispatch / EXIT dispatch** 读 `flow_label`/`flow_paragraphs`
  骨架装配态——`LeafCtx` 契约明令不纳 skeleton 层状态（context.py docstring）→ dispatch 守界留骨架刀。
- 用户认可方案 + 选**单文件 `control.py`**（`translate_control` + `translate_evaluate` + `evaluate_case_label`）。
- 决定固化于设计 §2、§9。

## 2. 执行步骤与产物（How）

1. 新建 `translator/leaf/control.py`（~75 行）；`leaf/__init__.py` 增导出 3 名；`context.py` LeafCtx 扩 `known_sections`/`section_to_method`。
2. `rules.py`：`_sk_evaluate` subject/case 委托 `translate_evaluate`/`evaluate_case_label`；`_sk_control` flow_label-无关分支委托 `translate_control`，**dispatch 分支先判保留**；顶部 import 3 名。
3. `asg/nodes.py`：`GotoStmt` 加 `tokens`；`asg/builder.py`：`_lift` 填 `tokens`。
4. `asg/visitor.py`：加 `visit_EvaluateStmt`、`visit_GotoStmt` 改委托、`visit_Leaf` 兜底再试 `translate_control`、`GotoJavaVisitor` 退役；`asg/__init__.py` 删其导出与 docstring 示例。
5. `scripts/diff_asg_vs_legacy.py`：加 `--verb CONTROL`（`_legacy_control`/`_ControlCollector`/`_asg_control` + `_eval_shell`）。
6. `test_translation.py`：新增 16 条（`TestLeafControlExtract`/`TestAsgControlVisitor`/`TestDiffAsgVsLegacyControl`）；`TestAsgGotoVisitor`（步骤17 demo）改用 `LeafJavaVisitor.visit_GotoStmt`（§7 预期迁移）。
7. 回填设计 §9、项目总览、本操作记录。

产物：`translator/leaf/control.py`（新建）；`rules.py`/`context.py`/`leaf/__init__.py`/`asg/nodes.py`/`asg/builder.py`/`asg/visitor.py`/`asg/__init__.py`/`scripts/diff_asg_vs_legacy.py`/`test_translation.py`（改）；
中间快照 `scratchpad/s23_before.json` / `s23_after.json`（零 diff 证据）。

## 3. 校验结果（逐项）

- **硬闸①旧路径零影响**：`python -m unittest test_translation` → `Ran 151 tests OK (skipped=2)`（迁前 135，+16 新）。
- **硬闸②config 快照零 diff**：`regress_config_snapshot.py` before（git stash -u 取 HEAD）/after `[ZERO-DIFF OK]`。
- **比对闸 CONTROL**：`TestDiffAsgVsLegacyControl` 内联程序（EVALUATE + GO TO 嵌套于 EVALUATE/IF + CONTINUE + EXIT，≥4 条）两路壳逐字符一致。
- **守界**：dispatch 模式（`__pc`/`continue FLOW`）未迁、未入 LeafCtx；`translate_control` 复刻 flow_label=None 分支，比对仅在 flow_label=None ctx。
- 文件体量：control.py 逻辑行 < 200（§17）。

## 4. 关键回显

```
Ran 151 tests in 0.249s
OK (skipped=2)
=== CONTROL-specific (含退役迁移 TestAsgGotoVisitor) ===
Ran 19 tests in 0.080s
OK
[ZERO-DIFF OK]   # s23_before.json vs s23_after.json
```

落地中两处自查修复（小步即验）：① 比对脚本 asg 侧 `translate_control(...)` 返回 `(lines,bool)`，应取 `[0]` 与 legacy `_sk_control` 裸行对齐；② 单测 `Leaf` 在方法内被后置 import 致 UnboundLocal，提前 import 修正。

## 5. Token 使用分析

- **主要消耗**：① 读 `rules.py` 控制流区段（`_sk_control`/`_sk_evaluate`/状态机 ~160 行）+ `visitor.py` 全文（142 行）+ `nodes.py`/`builder.py`/`context.py` 片段定位边界；② GotoJavaVisitor 退役的全仓引用 grep + 既有用例迁移；③ 比对脚本两处 bug 的 2 轮跑测回显。
- **节流**：Grep 先定位再精读，未全文重读 rules.py（~1280 行）；新文件 Write 一次成型；快照 before/after 用 git stash 取基线、PYTHONIOENCODING=utf-8 规避 gbk 崩溃。
- **量级**：中等偏上（控制流跨 rules/asg/visitor/builder/script/test 六处，单步骤改动面较前几刀大）。工具轮数约 40；最大单次回显为 151 测试与 _sk_control/_sk_evaluate 原文回放。
