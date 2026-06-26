# 步骤20　绞杀项3③ PERFORM 循环子句迁 visitor 操作记录

对应设计：`../详细设计/步骤20-绞杀项3③PERFORM循环子句迁visitor设计.md`（🟢已实现）。
日期：2026-06-26。承步骤18（MOVE）/19（IF）同范式，按动词顺序的**第三刀**。

## 1. 讨论与决策脉络（Why）

- 用户「继续」→ 下一刀 PERFORM。探查发现 PERFORM 是 rules 最大子系统，含**三个独立关注点**：
  ① 循环子句翻译（`_perform_loop` 三件套，纯函数）；② THRU 区间/目标解析（步骤12-15，读写 `proc_order`/`pending_range_methods`/`section_to_method` 等**骨架装配态**，超出 LeafCtx）；③ BEGN foreach + struct_rebind（步骤18 §8-Q1，混 IO 映射/骨架递归/叶子重绑定）。
- 经 **AskUserQuestion** 定本刀范围：用户选 **①循环子句翻译**（与 MOVE/IF 同范式、可零 diff 抽公用）；②③留后续「骨架装配迁 visitor」刀。
- 沿用步骤18/19 A 案「抽公用、两路共调」：`leaf/loop.py` 持 `translate_perform_loop`、rules 委托、`visit_PerformStmt` 共调 → 循环壳逐字符必然一致。
- 探查结论（留痕）：`_perform_loop` 闭包依赖（`_operand`/`translate_condition`/`_ind`）**已全在 leaf**（步骤18/19 已迁），ctx 只读 `field_type_map`（已在 LeafCtx）→ loop.py **零新依赖**。`PerformStmt`/`_lift_perform` 步骤17 已就位，本刀不动 `nodes.py`/`builder.py`。
- 诚实边界（§4.2）：PERFORM body（inline_body）旧占位 vs 新直译、out-of-line 目标旧区间合成 vs 新 `// TODO-PERFORM-CALL` 占位——本就不等（渐进迁移预期态），比对只在**循环壳**层；block 级一致待②③及全动词迁完（§5-项4）。

## 2. 执行步骤与产物（How）

| 步 | 动作 | 产物 |
|----|------|------|
| 1 | 抽公用 | 新建 `translator/leaf/loop.py`（`_perform_loop`+`_has_test_after`+`_parse_varying_clauses` 迁自 rules，逻辑零改 + `translate_perform_loop` 薄壳 + 本地 `_ind`）；`leaf/__init__.py` 门面增导出 |
| 2 | rules 委托 | 删 rules 三定义；顶部 `from translator.leaf.loop import _perform_loop`（`_sk_perform` 调用点零改） |
| 3 | 相3 visit | `asg/visitor.LeafJavaVisitor` 加 `visit_PerformStmt`（循环壳 + inline_body 递归 + out-of-line 占位 + loop=None 兜底）；import 增 `translate_perform_loop` |
| 4 | 比对闸 | `scripts/diff_asg_vs_legacy.py` `--verb` 加 PERFORM；新增 `_legacy_performs`/`_PerformCollector`/`_asg_performs`，`_SAMPLERS` 增项 |
| 5 | 单测 | `test_translation.py` 加 3 类 13 测（`TestLeafLoopExtract`/`TestAsgPerformVisitor`/`TestDiffAsgVsLegacyPerform`） |
| 6 | 回填 | 设计 §9、本记录、`架构索引/项目总览.md`（loop.py 行 + `visit_PerformStmt` + 比对闸 `--verb PERFORM`） |

## 3. 校验结果（逐项）

- 步骤2 硬闸（旧路径零影响）：`python -m unittest test_translation` → **99 通过/2 skip/0 失败**（迁址+委托后，与步骤19 基线一致）；
  `PYTHONIOENCODING=utf-8 python scripts/regress_config_snapshot.py` → **exit 0**（循环子句抽取未触碰 config）。
- 步骤3 后回归：单测仍 99 通过/2 skip（visitor 新增方法不破 MOVE/IF 比对）。
- 步骤4 比对闸（临时样例 `scratchpad/sample_perform.cob`，含 UNTIL / TIMES / VARYING…AFTER / out-of-line）：
  - `--verb PERFORM` → `[OK] 4 条 PERFORM 两路逐字符一致`，exit 0；
  - `--verb IF` → `[OK] 0 条 IF…` exit 0；`--verb MOVE` → `[OK] 4 条 MOVE…` exit 0（前两刀回归未破）。
- 步骤5 新测：3 类 13 测全绿。
- 全量收尾：`python -m unittest test_translation` → **112 通过 / 2 skip / 0 失败**（旧 99 + 新 13）。

## 4. 关键回显

- `python -m unittest test_translation` → `Ran 112 tests … OK (skipped=2)`。
- `diff_asg_vs_legacy.py sample_perform.cob --verb PERFORM` → `[OK] …4 条 PERFORM 两路逐字符一致 exit=0`。
- `--verb MOVE` → `[OK] …4 条 MOVE… exit=0`；`--verb IF` → `[OK] …0 条 IF… exit=0`。

## 5. Token 使用分析

- **主要消耗**：① 探查——读 PERFORM 全子系统（`_sk_perform`/`_perform_loop`/`_perform_range`/`_perform_range_paragraph`/`_perform_single_paragraph`/`_render_begn_foreach`/`_tag_rebind`/VARYING 解析，约 200 行）以界定三关注点边界，是本刀最大消耗（PERFORM 比 MOVE/IF 复杂）；② 范围决策——AskUserQuestion 一轮（避免误切②③大块）；③ 落地——loop.py 原样搬（无重写）、rules 删改、visitor/脚本/单测编辑；④ 校验——3 轮 unittest + 1 次三动词比对闸 CLI。
- **量级**：探查（含三关注点辨析）约 55%，落地编辑约 25%，校验回显约 5%，文档回填约 15%。
- **省 Token 措施**：① 经范围决策**只切①**，避免在②③（骨架装配层、强耦合）上空耗；② loop.py 复用 `leaf.expr`/`leaf.cond`（步骤18/19 已迁）→ 无需重读/重写表达式与条件逻辑；③ 比对脚本以 `_SAMPLERS` 字典分派复用前两刀主干，未重写比对循环；④ `PerformStmt`/`_lift_perform` 复用步骤17 成果，省 nodes/builder 改动与验证轮。整体在单刀小步范围内。
