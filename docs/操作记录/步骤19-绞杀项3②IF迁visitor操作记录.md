# 步骤19　绞杀项3② IF 迁 visitor 操作记录

对应设计：`../详细设计/步骤19-绞杀项3②IF迁visitor设计.md`（🟢已实现）。
日期：2026-06-26。承步骤18（MOVE 刀）同范式，按动词顺序的**第二刀**。

## 1. 讨论与决策脉络（Why）

- `/clear` 后据上一会话接续标记「下一刀按动词顺序是 IF」启动；用户两次「确认」——先认可**设计先行产出的 §1-9 设计**，再认可**按 §6 落地**。
- 沿用步骤18 的 **A 案「抽公用、两路共调」**：条件翻译下沉公用、rules 委托、`visit_IfStmt` 共调 → 条件产物逐字符必然一致，零 diff 风险（依据 §16/§17、初步设计 §0）。
- 落地步骤18 §8-Q3：条件翻译归 **`translator/leaf/cond.py`**（与 `move.py` 并列，不塞 `expr.py`——expr 是纯表达式、cond 是条件层）。
- 探查结论（留痕）：`_try_condition` 闭包（`→ _try_comparison → _negate_numeric`）的表达式依赖**已全在 `leaf.expr`**（步骤18 已迁）、ctx 只读 `field_type_map`（已在 `LeafCtx` 契约）→ cond.py **零新依赖**。`IfStmt` 节点与 `_lift` 提升**步骤17 已就位**，本刀不动 `nodes.py`/`builder.py`（比 MOVE 刀少一块改动）。
- 诚实边界（§4.2）：IF body 旧路是 `ctx.new_leaf` 占位、新路是 visitor 直译，**两路本就不等**（渐进迁移预期态），故比对只在**条件表达式**层；block 级一致待全动词迁完（§5-项4）。

## 2. 执行步骤与产物（How）

| 步 | 动作 | 产物 |
|----|------|------|
| 1 | 抽公用 | 新建 `translator/leaf/cond.py`（`translate_condition`+`_try_comparison`+`_negate_numeric`，迁自 rules，逻辑零改）；`leaf/__init__.py` 门面增导出 |
| 2 | rules 委托 | 删 rules.py:77-183 三定义；顶部 `from translator.leaf.cond import translate_condition as _try_condition`（4 处调用点零改） |
| 3 | 相3 visit | `asg/visitor.LeafJavaVisitor` 加 `visit_IfStmt`/`_body`/`visit_Leaf`；import 增 `translate_condition` |
| 4 | 比对闸 | `scripts/diff_asg_vs_legacy.py` `--verb` 加 IF；新增 `_legacy_ifs`/`_IfCollector`/`_asg_ifs`，`main` 按 `_SAMPLERS` 字典分派 |
| 5 | 单测 | `test_translation.py` 加 3 类 13 测（`TestLeafCondExtract`/`TestAsgIfVisitor`/`TestDiffAsgVsLegacyIf`） |
| 6 | 回填 | 设计 §9、本记录、`架构索引/项目总览.md`（cond.py 行 + `visit_IfStmt` + 比对闸 `--verb IF`） |

## 3. 校验结果（逐项）

- 步骤2 硬闸（旧路径零影响）：`python -m unittest test_translation` → **86 通过/2 skip/0 失败**（迁址+委托后，与基线一致）；
  `PYTHONIOENCODING=utf-8 python scripts/regress_config_snapshot.py` → **exit 0**（条件翻译抽取未触碰 config）。
- 步骤3 后回归：单测仍 86 通过/2 skip（visitor 新增方法不破 MOVE 比对）。
- 步骤4 比对闸（临时样例 `scratchpad/sample_if.cob`，含嵌套 IF / AND / OR / NOT）：
  - `--verb IF` → `[OK] 4 条 IF 两路逐字符一致`，exit 0；
  - `--verb MOVE` → `[OK] 4 条 MOVE 两路逐字符一致`，exit 0（MOVE 刀回归未破）。
- 步骤5 新测：3 类 13 测全绿。
- 全量收尾：`python -m unittest test_translation` → **99 通过 / 2 skip / 0 失败**（旧 86 + 新 13）。

## 4. 关键回显

- `python -m unittest test_translation` → `Ran 99 tests … OK (skipped=2)`。
- `diff_asg_vs_legacy.py sample_if.cob --verb IF` → `[OK] …4 条 IF 两路逐字符一致 exit=0`。
- `diff_asg_vs_legacy.py sample_if.cob --verb MOVE` → `[OK] …4 条 MOVE 两路逐字符一致 exit=0`。

## 5. Token 使用分析

- **主要消耗**：① 启动探查——读 MOVE 刀设计/操作记录（模板）+ `translator/leaf/{__init__,context,expr,move}.py` + rules 条件翻译段 + asg `nodes/builder/visitor` + 比对脚本（一次性并行读入，建立全貌，占比最大）；② 落地——cond.py 迁址（rules 既有源码原样搬，无重写）、rules 删改、visitor/脚本/单测编辑；③ 校验——3 轮 `unittest` + 2 次比对闸 CLI（回显短）。
- **量级**：探查（读 ~10 文件）约占 60%，落地编辑约 25%，校验回显约 5%，文档回填约 10%。
- **省 Token 措施**：cond.py 直接复用 `leaf.expr` 底座（步骤18 已迁）→ 无需重读/重写表达式逻辑；比对脚本以 `_SAMPLERS` 字典分派复用 MOVE 主干，未重写比对循环；`IfStmt`/`_lift` 复用步骤17 成果，省去 nodes/builder 改动与验证轮。整体在单刀小步范围内，未触发大文件全文重读。
