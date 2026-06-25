# 步骤15 · 单条 PERFORM paragraph 调用落地操作记录（C-3）

状态：🟢已实现（2026-06-25）
对应设计：`../详细设计/步骤15-单条PERFORM-paragraph调用落地设计.md`（✅已认可 → 本次落地）
配套正本：`config/specs/skeleton_spec.yaml`（block_grammar.perform.single）

---

## 0. 接续点与决策

步骤14（THRU 区间内 GO TO）落地并提交（分支 `feat/step14-thru-goto`，commit e0f5087）。用户「提交，再继续」。
§5 余下 C-3（单条 PERFORM paragraph）与 UNTIL/VARYING；C-3 是现存 bug（静默坏调用），优先。出 `步骤15` 设计 → 用户「认可」→ 落地。
D15-1/2/3 均按设计推荐。

## 1. 根因诊断（探查留痕）

只读探查（精读 `_sk_perform`/`_perform_range`/`_proc_call`）：单条 `PERFORM X`（无 THRU、无循环、无 children）
→ `_perform_range` 无 THRU 分支直接 `_proc_call(target)` → `this.<section_to_method(target)>();`，**不分 SECTION/paragraph**。
paragraph 在 `build_section` 内联进所属 SECTION 方法体、**无同名方法** → 调到不存在的方法、不可编译。
步骤13 已把全部 paragraph 收进 `proc_order`（带体）、步骤13/14 已有「登记 pending→drain 译为类级方法」机制 → C-3 可直接复用。

## 2. 执行脉络（TDD 红-绿）

1. **RED-1**：3 测——`synthesizes_method`（断言登记单单元 pending）/ `section_unchanged`（SECTION 零回归）/ `unknown_conservative`（兜不住出 TODO）。
   跑：synthesizes 红（KeyError 无 pending）、unknown 红（无 TODO、静默坏调用）；section_unchanged 即时绿（既有行为正确，作回归锁）。
2. **GREEN-1**：新增 `_perform_single_paragraph(target, ctx, indent)`：SECTION→维持 `_proc_call`；paragraph（proc_order 恰一次、
   非 SECTION、`section_to_method(target)` 不撞已有 SECTION 方法名）→登记 `pending_range_methods[pXxx]=[(target,body)]`（幂等）+ 返回 `this.pXxx();`；
   兜不住→`this.pXxx()` + 前置可见 TODO。`_perform_range` 无 THRU 分支改调之。`TestPerformThru` 13 测绿、全量 51 绿。
3. **补 §6 余测**：`idempotent`（同段多次→一次合成）+ `renders_method`（drain 渲染合成方法体含译文）。全量 53 绿。
4. **正本同步**：skeleton_spec `block_grammar.perform` 加 `single.section/paragraph/unresolved` 三态。再跑 53 绿（YAML 加载无碍）。

## 3. 关键实现取舍

- **复用为主**：渲染/B1 补实参/命名全沿用步骤13/14，零新增渲染或命名代码。调用点 `this.pXxx();` 不变，只「补出」缺失方法定义。
- **保守边界（D15-2）**：合成名撞 SECTION 方法名、proc_order 重名、全程序不存在 → 一律 `this.pXxx()` + 可见 TODO，把**静默坏调用**变显式可核对，不臆造。
- **C-3 影响面**：改动落在所有单条 PERFORM 的统一入口，但 `target in known_sections` 短路保证 `PERFORM <SECTION>` 零回归（全量 51→53 验证）。

## 4. 端到端校验（SMOKE15）

最小程序 `PERFORM 2000-CALC`（2000-CALC 为 `2000-WORK` 段下 paragraph）。真实 `scripts/translate_skeleton.py` 产出：

```
void main1000(Smoke15Wsaa wsaa) { … this.calc2000(wsaa); … }   // 调用点，B1 补 wsaa 实参
void calc2000(Smoke15Wsaa wsaa) {                              // 之前不存在的方法，现已补出
    // paragraph 2000-CALC
    wsaa.wsaaN = 7;
}
```

判读：单条 PERFORM paragraph 不再调到不存在方法（步骤15 前 `this.calc2000()` 无定义、不可编译）。
注：2000-CALC 在 `work2000()` 段方法内仍内联一份、又作 `calc2000()` 独立一份——路线b 体复制权衡，与步骤13 一致，正确。
脚本末 `print("✓ …")` GBK 报错发生在写盘后，产物正确，属既有范围外脚本疵，本步不动。

## 5. 验证结论

- 单测：步骤15 新增 5 测 + 步骤13/14 全用例 + 全量 53 测绿（skipped=2＝本地 vLLM 未起）。
- 端到端：SMOKE15 产出符合 D15-1/2/3。
- 设计 §6 用例：synthesizes/section_unchanged/idempotent/unknown_conservative/renders_method 全覆盖。

## Token 使用分析

- **主要消耗**：① 设计阶段落点精读（`_sk_perform`/`_perform_range`/`_proc_call`，均 grep 定位 + offset 精读，未全文读 rules.py）；② 设计 + 操作记录撰写；③ 一次端到端 SMOKE15。
- **量级**：低。工具轮数约 18；无大文件全文读、无 LLM、无长日志；复用步骤13/14 机制使代码改动与测试脚手架成本都很小。
- **节流**：C-3 复用既有 pending/render/命名，仅新增一个小工具函数 + 一处分支改调；端到端用 14 行最小 .cob。
