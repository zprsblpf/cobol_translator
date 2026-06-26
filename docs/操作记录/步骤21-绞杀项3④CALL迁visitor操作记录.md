# 步骤21　绞杀项3④ CALL 迁 visitor 操作记录

对应设计：`../详细设计/步骤21-绞杀项3④CALL迁visitor设计.md`（🟢已实现）。
日期：2026-06-26。承步骤18（MOVE）/19（IF）/20（PERFORM）同范式，按动词顺序的**第四刀**。

## 1. 讨论与决策脉络（Why）

- 用户「继续 CALL 刀」→ 下一刀 CALL。探查发现 CALL 子系统含**三个关注点**：
  ① 散点 CALL 兜底翻译（`_t_call` + IO 映射解析 `resolve_io_info`/`derive_io_info`，纯函数）；
  ② setup+CALL+IF 结构吸收（步骤10/11，`_match_*_single`/`_render_*`/`_rewrite_begn_loops`，多语句窗口扫描 + `struct_function` 时序写入，骨架装配层）；
  ③ struct_rebind / BEGN foreach（步骤18 §8-Q1，混 IO 映射/骨架递归/叶子重绑定）。
- 沿用步骤18/19/20 A 案「抽公用、两路共调」：本刀**只切① 散点兜底**（与 MOVE/IF/PERFORM 同范式、可零 diff 抽公用）；②③留后续「IO 结构吸收迁 visitor」刀。
- 探查结论（留痕）：`_t_call` 闭包依赖 `_struct_obj`（已在 leaf.expr）、`resolve_io_info`/`derive_io_info`（rules 内**纯函数**，随迁）、`re`；ctx 读 `io_programs`/`io_default_pattern`/`date_programs`/`system_programs`（**LeafCtx 待扩**）+ `struct_function`（已在契约）。
- **两处与前三刀不同**（设计 §2 列为待确认，用户认可）：
  - **须动 nodes/builder**——`CallStmt` 仅存 name/using，缺 `_t_call` 所需原始 token 串 → 加 `tokens` 字段（镜像 `MoveStmt`）、`_lift` 填充。IF/PERFORM 当时所需 cond/header 已在节点，故未动。
  - **LeafCtx 首次扩契约**——增 4 字段；`rules.Ctx`/`build_body_ctx` 已具备，两路 ctx 零改造。
- 接线安全：`resolve_io_info`/`derive_io_info` 被 graph/nodes、main、translator/context、translator/skeleton、scripts/regress_config_snapshot 以 `rules.resolve_io_info` 引用 → 迁 leaf 后**再导入回 rules**，公开面零变化（grep 留痕 5 处）。
- 诚实边界（§4.2）：固化语义（findBy/save）依赖 `struct_function` 时序填充 + ② 结构吸收——本刀不重放、不比对，比对只在 `translate_call(toks,ctx)` 纯函数 `(lines,matched)` 层（两路同 ctx → 必然相等）；block 级一致待②③及全动词迁完（§5-项4）。

## 2. 执行步骤与产物（How）

| 步 | 动作 | 产物 |
|----|------|------|
| 1 | 抽公用 + 扩契约 | 新建 `translator/leaf/call.py`（`translate_call` 迁自 `_t_call` + `resolve_io_info`/`derive_io_info` 迁，逻辑零改）；`leaf/context.py` LeafCtx 扩 4 字段；`leaf/__init__.py` 门面增导出 |
| 2 | rules 委托 + 再导入 | 删 rules 三定义；顶部 `from translator.leaf.call import translate_call as _t_call, resolve_io_info, derive_io_info`（dispatch + 结构吸收 4 处 + 外部引用零改） |
| 3 | 节点补 token | `asg/nodes.CallStmt` 加 `tokens`；`asg/builder._lift` 填 `tokens=list(st.tokens)` |
| 4 | 相3 visit + 比对闸 | `asg/visitor.LeafJavaVisitor` 加 `visit_CallStmt`（matched=False→`// TODO-CALL`）；`scripts/diff_asg_vs_legacy.py` `--verb` 加 CALL + `_legacy_calls`/`_CallCollector`/`_asg_calls`，`_SAMPLERS` 增项 |
| 5 | 单测 | `test_translation.py` 加 3 类 7 测（`TestLeafCallExtract`/`TestAsgCallVisitor`/`TestDiffAsgVsLegacyCall`） |
| 6 | 回填 | 设计 §9、本记录、`架构索引/项目总览.md`（call.py 行 + LeafCtx 扩字段 + `CallStmt.tokens` + `visit_CallStmt` + 比对闸 `--verb CALL`） |

## 3. 校验结果（逐项）

- 步骤2 硬闸（旧路径零影响）：`python -m unittest test_translation` → **112 通过/2 skip/0 失败**（迁址+委托+再导入后，与步骤20 基线一致）；
  `PYTHONIOENCODING=utf-8 python scripts/regress_config_snapshot.py` → **exit 0**（`resolve_io_info` 快照不变，再导入接线完好）。
- 步骤3/4 后回归：visitor/节点新增不破前三刀比对。
- 步骤4 比对闸（临时样例 `scratchpad/sample_call.cob`，含 IO 固化 `AGNTIO`/非 IO `SOMESUB`/嵌套于 IF 的 `CLNTIO`/嵌套于 PERFORM 的 `CHDRENQIO`）：
  - `--verb CALL` → `[OK] 4 条 CALL 两路逐字符一致`，exit 0；
  - `--verb MOVE/IF/PERFORM` → 全 `[OK]` exit 0（前三刀回归未破）。
- 步骤5 新测：3 类 7 测全绿。
- 全量收尾：`python -m unittest test_translation` → **119 通过 / 2 skip / 0 失败**（旧 112 + 新 7）。

## 4. 关键回显

- `python -m unittest test_translation` → `Ran 119 tests … OK (skipped=2)`。
- `regress_config_snapshot.py` → `regress exit=0`。
- `diff_asg_vs_legacy.py sample_call.cob --verb CALL` → `[OK] …4 条 CALL 两路逐字符一致`，exit=0；
  `--verb MOVE` → `1 条`、`--verb IF` → `1 条`、`--verb PERFORM` → `1 条`，均 exit=0。

## 5. Token 使用分析

- **主要消耗**：① 探查——读 `_t_call` 闭包（含 `resolve_io_info`/`derive_io_info`/`_struct_obj`）+ grep `resolve_io_info`/`_t_call` 全仓引用（界定再导入公开面、确认接线安全）+ 读 `CallStmt`/`_lift`/`body_context`/比对脚本/既有 IO 单测，是本刀最大消耗；② 落地——call.py 原样搬（无重写）、rules 删改、context/nodes/builder/visitor/脚本/单测编辑；③ 校验——2 轮 unittest + 4 动词比对闸 CLI。
- **量级**：探查（含引用面排查）约 50%，落地编辑约 25%，校验回显约 10%，文档（设计 §9 + 操作记录 + 项目总览）约 15%。
- **省 Token 措施**：① 经范围决策**只切①**，避免在②③（结构吸收/重绑定，强耦合）上空耗；② call.py 复用 `leaf.expr._struct_obj`（步骤18 已迁）→ 无需重读/重写结构体命名逻辑；③ 再导入策略保 `rules.*` 公开面 → 外部 5 处引用零改、零验证轮；④ 比对脚本以 `_SAMPLERS` 字典分派复用前三刀主干，`_CallCollector` 依赖基类 `generic_visit` 默认递归（不写冗余容器 visit）；⑤ 单测复用既有 IO `_ctx` 形态。整体在单刀小步范围内。
