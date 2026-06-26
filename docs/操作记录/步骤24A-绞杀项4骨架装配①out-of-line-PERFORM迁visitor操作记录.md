# 步骤24A　绞杀项4 骨架装配① out-of-line PERFORM 迁 visitor 操作记录

状态：🟢已实现（2026-06-26）
对应设计：`../详细设计/步骤24A-绞杀项4骨架装配①out-of-line-PERFORM迁visitor设计.md`（✅已认可）

---

## 1. 讨论与决策脉络（Why）

- 绞杀项3（步骤18–23）迁完**所有有旧译器的叶子动词**后，确认旧 `rules.py` 还压着**骨架装配层**，
  新路 `LeafJavaVisitor` 仅做叶子级翻译、out-of-line PERFORM 落 `// TODO-PERFORM-CALL` 占位，
  **产不出与正本逐字符一致的整份程序**，故「下线旧 token 路径」（项4）不能直接做。
- 与用户对齐：项4 拆 **24A/B/C/D 四刀自底向上**，最后一刀 cutover+删除；本刀（24A）只切第一块
  ——out-of-line PERFORM 调用体（`_perform_range` 三件套 + `pending_range_methods` 登记）。
- 关键抉择（设计 §3，用户认可推荐项）：①落点新建 `translator/skel/`（骨架装配公用底座，与 `leaf/` 平行）；
  ②新 `SkelCtx` 窄协议（含可写 `pending_range_methods`），不污染 `LeafCtx`；
  ③**token-based 原样迁址**（非 ref-based）——因 `ProcRegistry.resolve_thru` 返回的 `ProcUnit` 不带段体，
  而合成区间登记需带标签段体，改 ref 需扩面，偏离最小风险；④比对闸扩 `--verb PERFORMCALL`。

## 2. 执行步骤与产物（How）

1. 新建 `translator/skel/__init__.py`（门面）、`context.py`（`SkelCtx` 协议）、`perform_call.py`
   （`render_perform_call`=旧 `_perform_range` + `_perform_single_paragraph`/`_perform_range_paragraph`/`_proc_call`/`_ind`，**原样迁址逻辑零改**，仅 ctx 注解 `rules.Ctx → SkelCtx`，~76 逻辑行）。
2. `rules.py`：删四函数体，改 `from translator.skel.perform_call import render_perform_call as _perform_range, _perform_single_paragraph, _perform_range_paragraph, _proc_call`（别名导回保 `rules.*` 公开面/`test_translation` 引用）；`_sk_perform` 调用点零改。
3. `asg/visitor.py`：`visit_PerformStmt` out-of-line 分支由 `// TODO-PERFORM-CALL` 占位改调 `render_perform_call(node.header, hu, node.target.name, self.ctx, 0)`（token-based，与旧路同源）；顶部 import。
4. `scripts/diff_asg_vs_legacy.py`：加 `--verb PERFORMCALL`（`_legacy_perform_calls`/`_PerformCallCollector`/`_asg_perform_calls` + `_perform_target`/`_pending_snapshot`）；两路各建独立 fresh ctx 隔离 pending 副作用，比对 `(调用体行, pending 快照)`。
5. `test_translation.py`：两条旧占位用例（`test_out_of_line_*_placeholder`）**占位转正**为 `*_migrated`（断言 == 旧 `_perform_range`）；新增 `TestSkelPerformCall`（4 条：单段/SECTION-THRU 展开/paragraph 合成+登记/兜不住 TODO）+ `TestDiffAsgVsLegacyPerformCall`（整程序两路全等）。
6. 回填设计 §7、项目总览、本操作记录。

产物：`translator/skel/{__init__,context,perform_call}.py`（新建）；`translator/rules.py`/`asg/visitor.py`/`scripts/diff_asg_vs_legacy.py`/`test_translation.py`（改）；样例 `scratchpad/sample_performcall.cob`。

## 3. 校验结果（逐项）

- **硬闸①旧路径零影响**：`python -m unittest test_translation` → `Ran 156 tests OK (skipped=2)`（迁前 151，净 +5：占位 2 条转正不计增、新增 5 条 - 改写 0）。
- **硬闸②config 快照零 diff**：`regress_config_snapshot.py` before（git stash -u 取 HEAD）/after 各 377 行 `[ZERO-DIFF OK]`。
- **比对闸 PERFORMCALL**：样例（paragraph 合成 + 单段 SECTION + SECTION 级 THRU 展开，3 条）两路 `(调用体行, pending 登记)` 逐字符/逐项一致。
- **未殃及**：同样例 `--verb PERFORM`（循环壳）仍 `[OK]`。
- 文件体量：`perform_call.py` 逻辑行 ~76（< 100，§17）。

## 4. 关键回显

```
Ran 156 tests in 0.036s
OK (skipped=2)
[ZERO-DIFF OK]   # snap_before(377) vs snap_after(377)
[OK] sample_performcall.cob [PERFORMCALL]：3 条 PERFORMCALL 两路逐字符一致
RAW: PERFORM 1100-PARA            →  this.para1100();          (pending: para1100)
RAW: PERFORM 2000-SUB            →  this.sub2000();
RAW: PERFORM 2000-SUB THRU 3000-END → // PERFORM…展开 2 段 / this.sub2000(); / this.end3000();
```

## 5. Token 使用分析

- **主要消耗**：① 项4 起步的架构摸底——读 `rules.py`（build_section/_sk_perform/_perform_range 三件套 ~200 行）+ `asg/visitor.py` 全文 + `registry.py`/`context.py`/diff 脚本片段，确认「骨架装配层未迁」这一硬发现；② 写两份文档（设计 + 操作记录）。
- **节流**：Grep 先定位再精读，未全文重读 rules.py（1103 行）；迁址用 Edit 整块替换、新文件 Write 一次成型；比对闸先在 scratchpad 手验通过再写正式用例。
- **量级**：中等。工具轮数约 30；最大单次回显为 156 测试与 _perform_range 三件套原文。
- **Context 提示**：本会话从「项4 方向决策」连贯走到 24A 落地，context 已偏中上。若续做 24B（GO 状态机），建议 `/clear` 后新开，避免多轮复利重算早期读入的大段源码。
