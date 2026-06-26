# 步骤23　绞杀项3⑥ 控制流动词 EVALUATE/GOTO 迁 visitor 设计（rules 逐类迁 visitor·第六刀）

状态：✅已认可（2026-06-26 用户认可，文件结构取单文件 `control.py`；按 §6 落地中）

定位：落地 `架构演进-三相分层(预处理-ASG-visitor)初步设计.md` **§5 迁移分期第 3 项「rules 逐类迁 visitor」的第六刀**——
承步骤18–22 同范式。前五刀已把叶子动词（MOVE/IF/PERFORM/CALL/算术·赋值）迁入公用底座 + visitor 直译。
本刀把**控制流动词**两类迁入 visitor，清零其 ASG 侧占位/缺失：

| 类 | 现态 | rules 函数 | 本刀去向 |
|---|---|---|---|
| EVALUATE | `EvaluateStmt` 节点已在；visitor **无 `visit_EvaluateStmt`** → 未渲染 switch | `_sk_evaluate` | 公用 `translate_evaluate` 渲 switch 壳 + 新增 `visit_EvaluateStmt` |
| GO TO | `GotoStmt` 节点（无 tokens）；`GotoJavaVisitor` demo 只覆盖部分态 | `_sk_control`(GO 分支) | 公用 `translate_control` + `visit_GotoStmt` 改委托 |
| CONTINUE/STOP/EXIT/GOBACK/NEXT | builder 未 lift → 落 `Leaf` → `visit_Leaf` 占位 | `_sk_control`(其余分支) | 公用 `translate_control` + `visit_Leaf` 兜底再试 |

关联：
- 上位路线图：`架构演进…初步设计.md` §5-项3、§9-Q2（控制流刀）；本步对应步骤22 §8-Q2。
- 前序范式：`步骤21-…CALL迁visitor设计.md` §3（leaf 包结构、`CallStmt.tokens` 加字段先例）、`步骤22-…算术赋值…设计.md` §3（分派器 + try/except 兜底 + 统一入口）。
- 复用对象（只读复用）：`translator/leaf/expr.py`（`_operand` 已在）、`asg.nodes.EvaluateStmt`/`GotoStmt`（已在）、`asg.visitor`（`GotoJavaVisitor` 退役并入 `LeafJavaVisitor`）。
- 受改造现状（本步动）：`translator/leaf/`（新建 `control.py`）、`translator/rules.py`（`_sk_control`/`_sk_evaluate` 抽公用部分 + 委托）、`asg/nodes.py`（`GotoStmt` 加 `tokens` 字段，CallStmt 先例）、`asg/builder.py`（填 `GotoStmt.tokens`）、`asg/visitor.py`（加 `visit_EvaluateStmt`、`visit_GotoStmt` 改委托、`visit_Leaf` 兜底再试、`GotoJavaVisitor` 并入）、`translator/leaf/context.py`（`LeafCtx` 扩 2 字段）、`scripts/diff_asg_vs_legacy.py`（加 `--verb CONTROL`）。

---

## 1. 本步目标与非目标

**目标**：
1. **抽公用**：把 `_sk_evaluate` 的 **switch 壳判定**（subject→`switch(x.trim())`、each WHEN→`case val:`/`default:`、EVALUATE TRUE/复杂 subject→交 LLM）抽成
   leaf 形态纯函数 `translate_evaluate(subject_tokens, ctx) -> str | None`（返回 switch 主体表达式或 None）；
   把 `_sk_control` 的 **flow_label-无关分支**（GO TO→EXIT/known_section→proc_call/unknown/no-target；GOBACK/STOP→return；
   EXIT(非dispatch)→return；CONTINUE→`;`；NEXT→`;`）抽成 `translate_control(tokens, ctx) -> tuple[list[str], bool]`
   （含 try/except 兜底，非控制词→`([],False)`）。两者下沉新文件 `translator/leaf/control.py`，逻辑零改。
2. **rules 委托**：`_sk_evaluate` 改用 `translate_evaluate` 取 subject_java（其余渲染/递归 build_skeleton 保留在骨架层）；
   `_sk_control` 的 flow_label-无关分支改委托 `translate_control`，**dispatch 分支（flow_label 真）保留在 `_sk_control`**（骨架态，本刀不迁）。**行为零变化**，旧单测 + `regress_config_snapshot` 零 diff 硬闸。
3. **相3 visitor 迁入**：
   - 新增 `LeafJavaVisitor.visit_EvaluateStmt`：经 `translate_evaluate` 取 subject，渲染 `switch{…}`，WHEN 体递归 `_body`，与 `_sk_evaluate` 壳逐字符一致；subject=None → `// TODO-EVALUATE` 占位。
   - `visit_GotoStmt` 改委托 `translate_control`（GotoStmt 加 `tokens` 字段，builder 填，CallStmt 先例）；`GotoJavaVisitor` demo 退役、其能力并入 `LeafJavaVisitor`。
   - `visit_Leaf`：算术/赋值兜不住后**再试** `translate_control`（覆盖落 Leaf 的 CONTINUE/STOP/EXIT/GOBACK/NEXT），仍兜不住才 `// TODO-LEAF`。
4. **契约扩 2 字段**：`LeafCtx` 增 `section_to_method`（callable）+ `known_sections`（set）——GO TO known_section→proc_call 用，均为**稳定结构信息**（build_body_ctx 期已定），非骨架瞬态。
5. **比对闸扩 CONTROL**：`scripts/diff_asg_vs_legacy.py` 加 `--verb CONTROL`——在 **flow_label=None** ctx 下比 `translate_control`/`translate_evaluate` 壳与 `_sk_control`/`_sk_evaluate` 逐字符一致。

**非目标（本步明确不做）**：
- **不迁 dispatch 模式状态机**：`__pc="x"; continue FLOW` / `break FLOW`（依赖 `flow_label`/`flow_paragraphs` 骨架装配态）——
  `LeafCtx` 契约明令不纳 skeleton 层状态（见 `context.py` docstring），属**骨架装配迁 visitor 刀（Q3）**。
  本刀 `translate_control` 复刻的是 **flow_label=None 分支**；比对只在 flow_label=None ctx 下成立（honest scope，同 PERFORM/CALL 刀）。
- **不迁 EVALUATE 的 WHEN 体渲染细节进 leaf**：switch 壳（subject+case 标签）迁公用比对，WHEN 体仍由 visitor 递归（同 IF body 渐进），block 级一致待 §5-项4。
- **不固化 EVALUATE TRUE / 复杂 subject / 多 token subject**：仍交 LLM（`_sk_evaluate` 既有边界，零改）。
- **不接入主翻译、不改 config 正本**；旧 `build_skeleton` 仍是产物正本（下线属 §5-项4）。

---

## 2. 待确认的决定（请认可后按 §6 落地）

- [范围] 本刀切 **EVALUATE switch 壳 + 控制流叶子词（GO/GOBACK/STOP/EXIT/CONTINUE/NEXT）的 flow_label-无关分支**；
  dispatch 模式（`__pc`/`continue FLOW`/`break FLOW`）留**骨架装配刀（Q3）**。
- [文件] 新建**单文件 `translator/leaf/control.py`**（`translate_control` + `translate_evaluate`，逻辑行预估 ≈ 70，< 200）。
  二者同属「控制流」、同复用 `leaf.expr._operand` 底座、同落 visitor 控制流位置 → 合一刀一文件。
  **若你倾向拆 `goto.py`(控制叶子词)+`evaluate.py` 两文件，请指出**（设计可改）。
- [契约] `LeafCtx` 扩 **2 字段** `section_to_method` + `known_sections`（稳定结构信息）；`flow_label`/`flow_paragraphs` **不入契约**（守骨架边界）。
- [节点] `GotoStmt` 加 `tokens` 字段（CallStmt 步骤21 先例）、builder 填；EVALUATE/Leaf 节点不动；**不新增节点种类**。`GotoJavaVisitor` demo 退役，能力并入 `LeafJavaVisitor`。
- [visit_Leaf 语义] arith/assign 兜不住 → 再试 `translate_control` → 仍兜不住才 `// TODO-LEAF`（占位单调收敛，只减不增）。
- [比对] 比对单位＝`translate_control(tokens,ctx)` 的 `(lines)`、`translate_evaluate` 的 switch 壳，**flow_label=None** 下与 `_sk_control`/`_sk_evaluate` 逐字符比。

---

## 3. `translator/leaf/control.py` 抽取边界（瘦而专）

### 3.1 抽取依据（探查结论，留痕）

- `_sk_control`（rules.py:1040-1072）：`first` 路由 GO/GOBACK/STOP/EXIT/CONTINUE/NEXT。其中**仅 GO 的 dispatch 分支**（`ctx.flow_label and target in ctx.flow_paragraphs`，:1051-1052）与 **EXIT 的 dispatch 分支**（`ctx.flow_label`，:1065-1066）读骨架态；
  其余分支只读 `target.endswith("EXIT")` / `ctx.known_sections` / `ctx.section_to_method`（经 `_proc_call`）→ 稳定结构信息。
- `_sk_evaluate`（rules.py:905-925）：subject_java 仅由 `_operand(st.tokens[0])`（单 token）得；多 token/TRUE/无 whens → `new_leaf`（LLM）。case 标签 `_operand(cond[0])` / `default`。`_operand` 已在 `leaf.expr`。
- `_ind`（缩进）属骨架层渲染细节：leaf 函数产**裸行**（indent=0），缩进由 visitor `_body`/rules `_ind` 各自施加（同 MOVE/IF 刀，leaf 不持 indent）。
- 结论：control.py **零新外部依赖**，仅复用 `leaf.expr._operand` + LeafCtx 的 `known_sections`/`section_to_method`（扩 2 字段）。

### 3.2 文件职责与门面

```
translator/leaf/
├── control.py   ← 新建：translate_control（控制叶子词，flow_label-无关）+ translate_evaluate（switch 主体判定）
├── __init__.py  门面：增导出 translate_control / translate_evaluate
└── （expr/move/cond/loop/call/assign/arith 不变）
```

- **`translate_control(tokens, ctx) -> (lines, bool)`**：复刻 `_sk_control` flow_label=None 分支，裸行（无 `_ind`）；
  非控制词或需 dispatch（本函数不读 flow_label，恒走 flow_label=None 路）→ 见 §4.2 比对边界。含 `try/except (ValueError, IndexError)` 兜底。
- **`translate_evaluate(subject_tokens, ctx) -> str | None`**：单 token 且非 TRUE → `f"{_operand(tok)}.trim()"`；否则 None（交 LLM）。
  WHEN case 标签由 visitor 调 `_operand`（与 `_sk_evaluate` 同），或一并提供 `evaluate_case_label(cond, ctx)` 小助手复用（避免 visitor 内嗅探）。
- 依赖单向：`rules → leaf.control`、`asg.visitor → leaf.control`、`leaf.control → leaf.expr`，无环。

### 3.3 `rules.py` 改造（委托，行为零变化）

- `_sk_evaluate`：`subj_java = translate_evaluate(st.tokens, ctx)`（取代 :910-912 的内联判定）；其余壳渲染/`build_skeleton` 递归保留。
- `_sk_control`：flow_label-无关分支改 `lines, ok = translate_control(st.tokens, ctx); if ok: return [_ind(indent)+l for l in lines]`；
  **dispatch 分支（flow_label 真）先于委托判定并保留原样**（骨架态不迁）。
- 顶部 import `translate_control, translate_evaluate`。*验证*：旧单测 + `regress_config_snapshot` 零 diff（硬闸）。

---

## 4. 相3 侧改造

### 4.1 `asg/visitor.py`
- **`visit_EvaluateStmt`（新增）**：`subj = translate_evaluate(node.subject, ctx)`；None → `["// TODO-EVALUATE: "+node.raw]`；
  否则渲 `switch (subj) {` + 每 WHEN（`case label: {` / `default: {` + `_body(body)` + `break;` + `}`）+ `}`，与 `_sk_evaluate` 壳逐字符一致。
- **`visit_GotoStmt` 改委托**：`lines, ok = translate_control(node.tokens, ctx); return lines if ok else ["// TODO-GOTO: …", "return;"]`（GotoStmt 加 tokens）。`GotoJavaVisitor` 退役。
- **`visit_Leaf` 兜底再试**：`la, ok = translate_arith_assign(...); if ok: return la; lc, ok = translate_control(...); return lc if ok else [TODO-LEAF]`。
- `_children` 移除对 EvaluateStmt 的特判？否——`visit_EvaluateStmt` 接管后 generic_visit 不再兜 EVALUATE，但 `_children` 仍供其它遍历器（比对收集器）递归，保留无害。

### 4.2 比对边界（honest scope）
- `translate_control`/`translate_evaluate` 与 `_sk_control`/`_sk_evaluate` 调**同函数同 ctx**（flow_label=None）→ 逐字符必然相等。
- **dispatch 模式（flow_label 真）不在比对内**：该路仍由 `_sk_control` 处理、visitor 侧本刀不产（留骨架刀）；比对脚本喂 flow_label=None ctx，规避伪差异（同 PERFORM ②/CALL ② 的 honest 边界）。
- EVALUATE 比对落 **switch 壳**（subject 行 + case/default 标签），WHEN 体旧 build_skeleton vs 新递归本就渐进不等（同 IF）。

---

## 5. `scripts/diff_asg_vs_legacy.py` 扩 `--verb CONTROL`

- `_legacy_control`：`_walk_segmenter_stmts` 枚举 `kind=="evaluate"` 或（`kind=="simple"` 且 `tokens[0]∈_CONTROL_FIRST`）的 Stmt，
  在 flow_label=None ctx 下跑 `rules._sk_control`/`_sk_evaluate` 取**裸壳**（剥 `_ind`）→ `(raw, shell)`。
- `_ControlCollector(AsgVisitor)`：`visit_GotoStmt`/`visit_EvaluateStmt` + `visit_Leaf`(filter 控制词) 跑 `translate_control`/`translate_evaluate` → `(raw, shell)`。
- 按源码序对齐逐字符 diff；`_SAMPLERS["CONTROL"]=(_legacy_control,_asg_control)`。退出码 全等 0 / 异 1。

---

## 6. 落地步骤（认可后严格按序，每步出产物即验）

1. 建 `translator/leaf/control.py`（translate_control + translate_evaluate + case 助手）；`__init__.py` 增导出；`context.py` LeafCtx 扩 2 字段。
2. 改 `rules.py`：`_sk_evaluate`/`_sk_control` 委托（dispatch 分支保留）。**跑 `unittest test_translation` + `regress_config_snapshot` → 全绿/零 diff**（硬闸）。
3. `asg/nodes.py`：`GotoStmt` 加 `tokens`；`asg/builder.py`：填 `tokens`。跑既有单测仍绿。
4. `asg/visitor.py`：加 `visit_EvaluateStmt`、`visit_GotoStmt` 改委托、`visit_Leaf` 兜底再试、`GotoJavaVisitor` 退役。跑单测（含 GotoJavaVisitor 既有用例预期迁移，见 §7）。
5. `scripts/diff_asg_vs_legacy.py`：加 `--verb CONTROL`。内联程序两路壳逐字符零差异。
6. 加单测（§7）。全量 `test_translation` 全绿。
7. 回填本设计 §9、更新项目总览、写操作记录（命令/产物/校验/Token 分析）。

---

## 7. 自检与验收
- **旧路径零影响硬闸**：`test_translation` 旧用例全绿、`regress_config_snapshot` 零 diff。
- **GotoJavaVisitor 退役的预期更新**：既有 `TestAsgGoto*`/引用 `GotoJavaVisitor` 的用例改用 `LeafJavaVisitor.visit_GotoStmt`（能力等价或增强：新增 known_section→proc_call）——预期迁移，逐一核对留痕。
- **新增单测**：① `TestLeafControlExtract`（translate_control 各控制词 + translate_evaluate 单token/TRUE/多token）；② `TestAsgControlVisitor`（visit_EvaluateStmt switch 壳；visit_GotoStmt==translate_control；CONTINUE 经 visit_Leaf 兜底）；③ `TestDiffAsgVsLegacyControl`（内联程序 EVALUATE+GO TO+CONTINUE，flow_label=None 两路壳逐字符一致）。
- **不接受**：dispatch 模式被强行迁入引入骨架耦合；flow_label/flow_paragraphs 入 LeafCtx；旧用例/快照非预期变化；新增节点种类。

---

## 8. 开放问题（留后续刀）
- **Q1**：dispatch 模式状态机（`__pc`/`continue FLOW`/`break FLOW`）→ 骨架装配迁 visitor 刀（与 PERFORM②THRU/CALL②结构吸收/③struct_rebind 合并）。
- **Q2**：STRING/UNSTRING/INSPECT 新增固化（扩固化，非迁移）。
- **Q3**：全动词 + 骨架迁完后，`_dispatch_leaf`/`_sk_*` 整体下沉 leaf/visitor 唯一入口，下线旧 token 通道（§5-项4）。

---

## 9. 实现结果（2026-06-26 落地回填）

**与设计零偏差**（文件结构取认可的单文件 `control.py`）：

- **公用底座**：新建 `translator/leaf/control.py`（`translate_control` + `translate_evaluate` + `evaluate_case_label`，逻辑行 ≈ 75，< 200，复刻 `_sk_control` flow_label=None 分支 + `_sk_evaluate` switch 壳，含 try/except 兜底）。`leaf/__init__.py` 增导出 3 名。
- **契约扩 2 字段**：`LeafCtx` 增 `known_sections` + `section_to_method`（稳定结构信息；`flow_label`/`flow_paragraphs` 未入，守骨架边界）。
- **rules 委托**：`_sk_evaluate` subject 取 `translate_evaluate`、case 标签取 `evaluate_case_label`（WHEN 体渲染/递归留骨架层）；`_sk_control` flow_label-无关分支委托 `translate_control`，**dispatch 分支（GO/EXIT + flow_label 真）先判并保留原样**。
- **节点**：`GotoStmt` 加 `tokens` 字段（CallStmt 先例）、`builder._lift` 填充；不新增节点种类。
- **相3 visitor**：新增 `visit_EvaluateStmt`（渲 switch 壳 + WHEN 体递归）、`visit_GotoStmt` 改委托 `translate_control`、`visit_Leaf` 在 arith/assign 兜不住后再试 `translate_control`（覆盖落 Leaf 的 CONTINUE/STOP/EXIT/GOBACK/NEXT）；**`GotoJavaVisitor` demo 退役**，能力并入 `LeafJavaVisitor`（同步删 `asg/__init__.py` 导出与 docstring 示例）。
- **比对闸扩 CONTROL**：`scripts/diff_asg_vs_legacy.py` 加 `_CONTROL_VERBS` + `_eval_shell` + `_legacy_control`（控制词跑 `rules._sk_control`/EVALUATE 取壳）+ `_ControlCollector`/`_asg_control` + `_SAMPLERS["CONTROL"]`。

**验收回归闸（全绿，证据）**：
- 旧路径零影响硬闸：`python -m unittest test_translation` → **151 tests OK（skipped=2）**（迁前 135，+16）；
  `regress_config_snapshot.py` before/after 逐字节 **零 diff**（git stash -u 取 HEAD 基线）。
- **§7 预期迁移**：`TestAsgGotoVisitor`（步骤17 demo 自证）由 `GotoJavaVisitor` 改用 `LeafJavaVisitor.visit_GotoStmt`（能力等价，新增 known_section→proc_call 经 `translate_control`），3 用例仍逐字符自证、留痕。
- 新增单测 16 条：`TestLeafControlExtract`(12)/`TestAsgControlVisitor`(4)/`TestDiffAsgVsLegacyControl`(1，内联程序 EVALUATE+GO TO(嵌套于 EVALUATE/IF)+CONTINUE+EXIT，flow_label=None 两路壳逐字符一致)。
- **占位单调收敛**：EVALUATE switch、GO TO、CONTINUE/STOP/EXIT/GOBACK/NEXT 在 visitor 直译可见；dispatch 模式仍占位/留骨架刀。
