# 步骤24B 操作记录　绞杀项4 骨架装配②：GO TO dispatch 状态机迁 visitor

执行日期：2026-06-26　状态：🟢已实现
对应设计：`../详细设计/步骤24B-绞杀项4骨架装配②GOTO-dispatch状态机迁visitor设计.md`（✅已认可 → 🟢落地）

---

## 1. 做了什么（按设计 §4 落地）

把段内回跳 GO TO 的**状态机降级**（`FLOW: while(true) switch(__pc)` + `__pc="x"; continue FLOW` / `break FLOW`）
从旧路 `rules.build_section` / `_sk_control` 迁进 visitor，旧/新两路共调同一份**路径中立装配函数**。

| 文件 | 动作 | 要点 |
|---|---|---|
| `translator/skel/flow_dispatch.py` | 新建（~50 逻辑行） | `render_flow_dispatch`（迁自 `build_section` 状态机部分，零改；三回调 `render_body`/`collect_gotos`/`ends_transfer` 外包节点遍历）+ `dispatch_goto`/`dispatch_exit`（迁自 `_sk_control` GO/EXIT 两行） |
| `translator/skel/context.py` | 改 | `SkelCtx` 扩可写 `flow_label`/`flow_paragraphs`（5→7 字段） |
| `translator/skel/__init__.py` | 改 | 导出 3 新符号 |
| `translator/rules.py` | 改 | `build_section` 删状态机/扁平体 → 委托 `render_flow_dispatch`（保 `_rewrite_begn_loops` 在前，24C 范围）；`_sk_control` GO/EXIT → `dispatch_goto`/`dispatch_exit`；调用点零改 |
| `asg/visitor.py` | 改 | 模块级 `_ind`/`_asg_collect_gotos`/`_asg_ends_transfer` + `visit_Section`/`_render_para_body`（首引段级入口，不单设 `visit_Paragraph`）；`visit_GotoStmt`/`visit_Leaf` 前置接 dispatch |
| `scripts/diff_asg_vs_legacy.py` | 改 | 扩 `--verb FLOW`（`_legacy_flows`/`_asg_flows`/`_flow_snapshot`/`_fill_legacy_leaves`，各建 fresh ctx 隔离；旧路占位叶子按同一 `translate_leaf` 回填以对齐 visitor 内联直译） |
| `test_translation.py` | 改 | `TestSkelFlowDispatch`（4 条）+ `TestDiffAsgVsLegacyFlow`（1 条） |
| `docs/架构索引/项目总览.md` | 改 | 同步 skel/flow_dispatch + visitor 段级入口 + 项4② 进度 + 详细设计链接 |

**守界**：`_rewrite_begn_loops`（BEGN foreach，③）留旧 `build_section`，visitor 本刀不做 → 含 begn 段两路暂分流，
`--verb FLOW` 选样回避（无 begn、段体动词均已迁），24C 抹平。

## 2. 关键命令与校验

```bash
# 硬闸①：旧路径零回归
python -m unittest test_translation          # Ran 161 OK (skipped=2)（迁前 156，+5 新）

# 硬闸②：config 快照 before/after 零 diff
python scripts/regress_config_snapshot.py > after.json
git stash push translator/rules.py translator/skel/context.py translator/skel/__init__.py
python scripts/regress_config_snapshot.py > before.json && git stash pop
diff before.json after.json                  # [ZERO-DIFF OK] 377 行

# 比对闸③：--verb FLOW（含回跳状态机/前向 GO TO dispatch/EXIT→break FLOW/段尾 transfer/扁平段）
python scripts/diff_asg_vs_legacy.py <sample>.cob --verb FLOW       # [OK] 两路逐字符一致
python scripts/diff_asg_vs_legacy.py <sample>.cob --verb CONTROL    # [OK]（证 _sk_control 委托无漂移）
python scripts/diff_asg_vs_legacy.py <sample>.cob --verb MOVE       # [OK]
```

## 3. 自检结论（逐项）

- ✅ 硬闸① `unittest` 161 OK（旧 156 全保 + 新 5 全绿）。
- ✅ 硬闸② config 快照 before/after `[ZERO-DIFF OK]` 377 行（本刀不触 config，纯代码迁址）。
- ✅ 比对闸③ `--verb FLOW`：2 SECTION 样例（状态机段 + 扁平段）两路 `(装配行, flow 复位快照)` 逐字符/逐项一致；
  防退化断言确认状态机段确实建机（`FLOW: while`/`break FLOW; // EXIT`/`continue FLOW; // GO TO 1100-LOOP`）。
- ✅ `--verb CONTROL`/`MOVE` 回归仍 `[OK]`，证 `_sk_control` 委托改造未影响 flow_label-无关分支。

## 4. 设计中途的实测发现（回填留痕）

**叶子渲染两趟 vs 一趟差异**：旧 `build_section` 把叶子留 `/*__LEAF_n__*/` 占位（二趟架构，渲染期回填），
visitor `_render_para_body` 一趟内联直译。直接比对会因占位 vs 实译产生伪差异。处置：`--verb FLOW` 旧路采样后
用**同一 `translate_leaf`** 回填占位（`_fill_legacy_leaves`），隔离 24B 段级装配的真比对——状态机壳 + dispatch
行 + flow 副作用三者逐字符一致即本刀目标，叶子本身一致性由前序绞杀刀（项3）保证。单行叶子原位替换不改缩进；
多行叶子非本闸选样形态（与旧 `_postprocess_body` 同口径）。

---

## Token 使用分析

- **主要消耗**：① 探查旧路 `build_section`/`_sk_control`/`_collect_gotos`/`_ends_with_transfer` + visitor/builder/nodes
  结构（精读 + 批量 grep，未全文读 rules.py 1100 行，靠 offset 精读关键段）；② 设计文档撰写（一次成稿，含路径中立
  装配 + 三回调的抉择留痕）；③ 实现后 3 轮硬闸校验 + 1 次 FLOW 比对 smoke 调试（发现叶子两趟差异并修 `_fill_legacy_leaves`）。
- **量级**：中等。读取以精读/grep 为主、回显克制（diff 输出只在 smoke 调试时打印一次）；无大文件全文读。
- **Context 状态**：本会话从 `/clear` 起，单刀完成，context 处于健康区间，无需预警。建议后续 24C（BEGN/IO 形态，
  涉及 `_rewrite_begn_loops` ~600 行）另起会话或先 `/clear`，避免叠加。
