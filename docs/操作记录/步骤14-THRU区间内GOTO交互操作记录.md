# 步骤14 · THRU 区间内 GO TO 交互操作记录

状态：🟢已实现（2026-06-25）
对应设计：`../详细设计/步骤14-THRU区间内GOTO交互设计.md`（✅已认可 → 本次落地）
配套正本：`config/specs/skeleton_spec.yaml`（perform.thru.goto_*）

---

## 0. 接续点与决策

步骤13（paragraph 级 THRU 区间，路线b 合成方法）已实现并合入。其 §5 列「THRU 区间内含 GO TO」为范围外。
用户在「认可继续」后于 §5 三候选（C-3 单条 PERFORM / 区间内 GO TO / UNTIL-VARYING）中点选 **「THRU 区间内 GO TO 交互」**。
按设计先行：先出 `步骤14` 详细设计（🔶待认可）→ 用户「认可」→ 落地。D14-3（前向 GO TO 是否强制状态机）取设计推荐**方案 a**。

## 1. 根因诊断（探查留痕，静态代码路径追踪）

设计阶段先定位「为什么区间内 GO TO 现在是坏的」，纯只读探查（grep `GO TO|__pc|switch`、精读 rules.py 段内控制流 + body_context 合成路径 + segmenter.split_paragraphs）：

- `split_paragraphs`（segmenter.py:198）检测到标签行后 `continue`，**标签行不入 body**，仅作返回元组首元；
- `_build_proc_order` 各 paragraph 单元 `u[3]` 体不含标签 → `_perform_range_paragraph` 合成 `merged += u[3]` **标签全丢**；
- 合成体经 `translate_section_body` 再 `split_paragraphs(merged)` → 无标签 → 整体成一个无标签 paragraph，`build_section` 看不到区间内边界、`flow_paragraphs` 空；
- 区间内 `GO TO X` 落 `_sk_control` 末路 → EXIT→误退、否则 `// TODO-GOTO + return;`，**回跳循环报废**。

结论：主体是「把标签结构还给 build_section」，而非新造控制流引擎。诊断写入设计 §1。

## 2. 执行脉络（TDD 红-绿，小步落地）

1. **RED-1**：`test_thru_paragraph_registers_labeled_units` 断言登记值为 `[(label, body),…]` → 红（当前存扁平 `list[str]`）。
2. **GREEN-1**：`_perform_range_paragraph` 登记改 `[(u[0], u[3]) for u in rng]`；同步两条 step-13 旧断言到带标签契约。`TestPerformThru` 10 测绿、全量 44 绿。
3. **RED-2（命门）**：`test_thru_goto_back_edge_loop`（区间内 `PARA-B → PARA-A` 回跳）经 `render_pending_range_methods` 应出 `switch(__pc)` → 红（render 仍按扁平契约，撞 `'tuple' object has no attribute 'strip'`、落翻译失败 TODO）。
4. **GREEN-2**：抽 `translate_paragraphs_body`（跳过 split 直喂带标签 paras，共用翻译核）；`translate_section_body` 重构为其薄封装；`render_pending_range_methods` 改调之。命门绿、全量 45 绿。
5. **RED-4**：`test_thru_goto_forward_intra_state_machine`（前向 `PARA-A → PARA-C`，无回跳）→ 红（扁平模式落 TODO-GOTO+return，未跳过中间单元）。另两测 out_of_range / no_goto 即时绿（既有保守行为正确）。
6. **GREEN-4（D14-3=a）**：`build_section` 加形参 `force_sm`，`has_back_edge`→`has_jump`、`force_sm` 下 `j is not None` 即触发状态机；经 `translate_paragraphs_body(force_sm)` 仅在合成区间方法路径置 True。`TestThruRangeGoto` 4 测绿、全量 48 绿。
7. **正本同步**：skeleton_spec `perform.thru` 加 `goto_intra_range/goto_range_exit/goto_out_of_range` + 回跳 sample。再跑 48 绿（YAML 加载无碍）。

## 3. 关键实现取舍（force_sm 作用域，校正留痕）

设计 §2.3 方案 a 原拟扩 `build_section` 的**通用** `has_back_edge` 判定，明列会波及普通 SECTION 的前向 `GO TO …-EXIT` 惯用法渲染（回归面大）。
落地改用**作用域标志 `force_sm`**：精确行为仅施加于合成区间方法，普通 SECTION 默认 `False`、渲染零变化。
既达成 D14-3=a 认可的「区间内前向 GO TO 精确跳转」，又把回归面收敛到零（更稳、符合 §17 最小爆炸半径）。已回填设计「实现回填·校正」。

E1/E2/E3 落点分类**未新增分支**：标签保留 + `force_sm` 后 `ctx.flow_paragraphs` 自动含区间标签，`_sk_control` 既有逻辑即完成
E1 状态机跳转 / E2 EXIT·GOBACK→return / E3 区间外→TODO-GOTO，零新增代码。

## 4. 端到端校验（SMOKE14）

最小程序 `PERFORM 2000-PA THRU 2000-PC`，区间内 `2000-PB` 含 `IF WSAA-N < 3 GO TO 2000-PA`（回跳）。
真实 `scripts/translate_skeleton.py` 产出合成方法：

```
void pa2000ThruPc2000(Smoke14Wsaa wsaa) {
    String __pc = "2000-PA"; FLOW: while (true) { switch (__pc) {
    case "2000-PA": { wsaa.wsaaN = 1; __pc = "2000-PB"; continue FLOW; }
    case "2000-PB": { wsaa.wsaaN += 1;
        if (wsaa.wsaaN < 3) { __pc = "2000-PA"; continue FLOW; }   // GO TO 2000-PA（回跳=循环）
        __pc = "2000-PC"; continue FLOW; }
    case "2000-PC": { wsaa.wsaaN = 9; break FLOW; }
    default: break FLOW; } }
}
```

判读：区间内回跳精确还原为状态机循环（步骤14 前退化为 `// TODO-GOTO + return;`、循环报废）。
注：脚本末 `print("✓ …")` 在 Windows GBK 控制台抛 `UnicodeEncodeError`，发生在 .java 写盘**之后**，产物正确，属步骤13 已记的范围外脚本疵，本步不动。

## 5. 验证结论

- 单测：`TestThruRangeGoto` 4 + `TestPerformThru.test_thru_paragraph_registers_labeled_units` 1 + 步骤13 全用例（带标签契约同步后）+ 全量 48 测绿（skipped=2＝本地 vLLM 未起）。
- 端到端：SMOKE14 产出符合 D14-1/D14-2/D14-3=a/D14-4。
- 设计 §6 用例：back_edge_loop（命门）/ forward_intra / out_of_range / no_goto 全覆盖；E2 出口 return 由命门状态机的 `break FLOW` 子路径与 SMOKE14 顺带验证。

## Token 使用分析

- **主要消耗**：① 设计阶段落点精读（rules.py 段内控制流 1040-1316 分段读、body_context 合成路径、segmenter.split_paragraphs）——grep 定位 + offset 精读，未全文读 rules.py(1280+)。② 设计文档 + 操作记录撰写。③ 一次端到端 SMOKE14 渲染。
- **量级**：中等偏低。工具轮数约 30；无大文件全文读、无 LLM、无长日志回显；TDD 四步 RED 均一次到位、GREEN 分步收敛。
- **节流**：复用步骤13 测试脚手架与 SMOKE 套路；E1/E2/E3 复用既有 `_sk_control` 零新增；force_sm 作用域化避免普通 SECTION 回归排查成本。
