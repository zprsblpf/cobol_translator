# 步骤16 · PERFORM 循环复杂变体操作记录（TEST AFTER / VARYING…AFTER）

状态：🟢已实现（2026-06-25）
对应设计：`../详细设计/步骤16-PERFORM循环复杂变体设计.md`（✅已认可 → 本次落地）
配套正本：`config/specs/skeleton_spec.yaml`（block_grammar.perform.loop）

---

## 0. 接续点与决策

步骤15（单条 PERFORM paragraph，C-3）落地并 push 到 master（commit 78949dc）。用户「继续」→ §5 最后一项 UNTIL/VARYING 复杂变体。
出 `步骤16` 设计（🔶待认可）→ 用户「认可」→ 落地。D16-1/2/3 均按设计推荐。

## 1. 根因诊断（探查留痕）

只读探查（精读 `_sk_perform` 循环子句分支 + `_try_condition`/`_operand`/`_try_comparison` + 查现有 PERFORM 循环测试基线=无）：
- **TEST AFTER 被无视**：`_sk_perform` 仅按 VARYING/UNTIL/TIMES 发 test-before，`WITH`/`TEST`/`AFTER` 仅作 target 排除关键字，从不据其改 do-while → `WITH TEST AFTER` 语义错（应 do-while）。
- **VARYING AFTER 被吞**：VARYING 分支只取首个 `hu.index("UNTIL")`，`header[UNTIL+1:]` 把 `AFTER j … UNTIL cj` 一并当条件喂 `_try_condition`（多半失败落 LLM 或误译单层）→ 内层维度丢失。
两者同处 `_sk_perform`、该函数偏长 → 顺带按 §17 抽循环子句解析为独立小工具。诊断写入设计 §1。

## 2. 执行脉络（TDD 红-绿）

1. **RED**：`TestPerformLoop` 4 测——test_after（do-while）/ test_before（零回归）/ varying_after_nested（双层）/ varying_single（零回归）。
   跑：test_after 红（现发 `while` 无 `do {`）、varying_after_nested 红（只 1 个 `for (`，AFTER 被吞）；两条 unchanged 即时绿（回归锁）。
2. **GREEN**：新增 `_has_test_after`（TEST 紧跟 AFTER）+ `_parse_varying_clauses`（VARYING/AFTER 切子句序列，任一兜不住→None）
   + `_perform_loop`（→ open/close 行：TEST AFTER do-while【仅无 VARYING】/ VARYING AFTER 嵌套 for / UNTIL·TIMES 基本形 / 兜不住 None）；
   `_sk_perform` 重写改调之（`None`→落 LLM；`inner_indent = indent + len(open_lines)`；`open+body+close`）。4 测绿、全量 57 绿。
3. **补 §6 余测**：unparsable→LLM（88 条件名无关系符）+ varying_test_after_conservative（VARYING+TEST AFTER 保守落 LLM）。全量 59 绿。
4. **正本同步**：skeleton_spec `block_grammar.perform` 增 `loop.test_before/test_after/varying_after/conservative`。再跑 59 绿（YAML 加载无碍）。

## 3. 关键实现取舍

- **§17 抽函数**：循环子句解析从 `_sk_perform` 抽到 `_perform_loop`/`_parse_varying_clauses`/`_has_test_after`，`_sk_perform` 瘦身、逻辑可单测。
- **嵌套缩进**：`inner_indent = indent + len(open_lines)`（每层 open 行=一层嵌套），close 行逆序构建（内层在前）。do-while/while/单 for=1 层，嵌套 for=N 层，统一处理。
- **保守 all-or-nothing（D16-3）**：任一子句条件/操作数兜不住 → 整条 `_perform_loop` 返回 None → 落 LLM 叶子，绝不出半个/误译循环。VARYING+TEST AFTER 叠加同样保守落 LLM（D16-1）。
- **零回归**：基本形（单层 VARYING / 默认 TEST BEFORE / TIMES）输出与改前一致（全量 53→59 验证，含 _sk_perform 重写）。

## 4. 端到端校验（SMOKE16）

```
do {                                                  // PERFORM WITH TEST AFTER UNTIL WSAA-N > 3
    wsaa.wsaaN += 1;
} while (!(wsaa.wsaaN > 3));
for (wsaa.wsaaI = 1; !(wsaa.wsaaI > 2); wsaa.wsaaI = wsaa.wsaaI + 1) {   // VARYING … AFTER → 嵌套
    for (wsaa.wsaaJ = 1; !(wsaa.wsaaJ > 2); wsaa.wsaaJ = wsaa.wsaaJ + 1) {
        wsaa.wsaaN += 1;
    }
}
```

判读：TEST AFTER→do-while（先做一次再判）、VARYING AFTER→双层嵌套 for（内层 j 不丢）。步骤16 前两者皆错。
脚本末 `print("✓")` GBK 报错发生在写盘后，产物正确，属既有范围外脚本疵，本步不动。

## 5. 验证结论

- 单测：`TestPerformLoop` 6 测 + 全量 59 测绿（skipped=2＝本地 vLLM 未起）。
- 端到端：SMOKE16 产出符合 D16-1/2/3。
- 设计 §6 用例全覆盖（test_after/test_before/varying_after_nested/varying_single/unparsable→LLM/varying_test_after_conservative）。

## Token 使用分析

- **主要消耗**：① 设计阶段落点精读（`_sk_perform`/`_try_condition`/`_try_comparison`/`_operand`/`Stmt` 结构，grep 定位 + offset 精读）；② 设计 + 操作记录撰写；③ 一次端到端 SMOKE16。
- **量级**：中等偏低。工具轮数约 22；无大文件全文读、无 LLM、无长日志；测试脚手架首次需摸 Stmt/ctx 构造（多读了 _operand/字段助手几段）。
- **节流**：循环解析抽函数后可直接单测 `_sk_perform`，无需端到端即覆盖主路径；端到端用 18 行最小 .cob。
