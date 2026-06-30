# 步骤24　骨架装配迁 visitor 设计（rules 逐类迁 visitor·骨架刀第一步）

状态：🟢已实现（2026-06-29 用户认可后落地）

定位：承接 `架构演进-三相分层(预处理-ASG-visitor)初步设计.md` §5 迁移分期第 3 项。
步骤18-23 已把 MOVE / IF / PERFORM 循环子句 / CALL 散点 / 算术赋值 / EVALUATE-GOTO 的叶子与壳迁到
`translator.leaf` + `LeafJavaVisitor`。本步开始处理前几刀明确留下的“骨架装配态”：

- `build_section` 的 paragraph 级装配、状态机壳、`flow_label/flow_paragraphs` 派发；
- `PERFORM paragraph/THRU` 的 out-of-line 目标解析与 `pending_range_methods` 登记；
- BEGN/NEXTR、READR/写 IO 的结构吸收仍先保留在旧 rules，作为本步非目标。

本步目标不是下线旧路径，而是让 ASG visitor 具备一个可比对的“SECTION/paragraph 渲染入口”，为后续接主线和结构吸收迁移做基座。

---

## 1. 本步目标与非目标

**目标**：

1. 新增 ASG 侧骨架渲染器 `SectionJavaVisitor`，继承/组合 `LeafJavaVisitor`，入口直接吃 `asg.nodes.Section` 或 paragraph 列表，产出 Java 行。
2. 迁入 `rules.build_section` 中的**状态机装配壳**：
   - paragraph label 归一；
   - `_collect_gotos` 等价逻辑；
   - 无内部跳转时顺序拼接并输出 `// paragraph X`；
   - 存在内部跳转时输出 `String __pc` + `FLOW: while(true)` + `switch(__pc)`；
   - `GO TO` 内部目标输出 `__pc = "..."; continue FLOW;`，`EXIT` 输出 `break FLOW;`。
3. 迁入 `PERFORM` out-of-line 目标解析：
   - `PERFORM section` → `this.<sectionMethod>();`
   - `PERFORM paragraph` → 登记 `ctx.pending_range_methods`，返回 `this.<paragraphMethod>();`
   - `PERFORM A THRU B`：SECTION 区间展开；paragraph 区间登记合成方法。
4. 扩 `scripts/diff_asg_vs_legacy.py` 新闸 `--verb SECTION`，在样例程序上比较旧 `rules.build_section` 与新 `SectionJavaVisitor` 的可迁 SECTION 产物。
5. 保持旧主线正本不变：`translator.skeleton_gen.body_context.translate_section_body` 仍调用 `rules.build_section`，本步只旁路自证。

**非目标**：

- 不迁 BEGN/NEXTR foreach、单次 BEGN、READR/READS、写 IO 的结构吸收；`rules._rewrite_begn_loops` 暂留旧路。
- 不处理 `struct_rebind` 迁移；for-each 体内结构体重绑定留后续“结构吸收刀”。
- 不接入 `render_skeleton` 主线，不删除 `rules.build_section/_sk_perform/_sk_control`。
- 不新增 STRING/UNSTRING/INSPECT 固化。

---

## 2. 文件与类设计

### 2.1 新增 `asg/section_visitor.py`

新增类 `SectionJavaVisitor`。

职责：把 ASG 的 `Section.paragraphs` 渲染为 Java 方法体行。它是“骨架装配 visitor”，不同于 `LeafJavaVisitor` 只访问单条语句。

方法设计：

- `__init__(self, ctx, force_sm: bool = False)`
  - 保存 `ctx` 和 `force_sm`。
  - 内部创建 `LeafJavaVisitor(ctx)` 复用已迁动词。
  - `force_sm` 语义与旧 `rules.build_section(force_sm=True)` 保持一致：合成区间方法内前向 GO TO 也触发状态机。

- `render_section(self, section: nodes.Section) -> list[str]`
  - 取 `section.paragraphs`，委托 `render_paragraphs`。
  - 不做后处理，不加 `wsaa.` 前缀；保持与旧 `rules.build_section` 同层级。

- `render_paragraphs(self, paragraphs: list[nodes.Paragraph]) -> list[str]`
  - 对 paragraph label 做 `__ENTRY_i` 归一。
  - 调 `_has_internal_jump` 判断是否需要状态机。
  - 无状态机时按 paragraph 顺序调用 `_body`。
  - 有状态机时设置临时 flow 环境并渲染 `switch` 壳。

- `_body(self, stmts: list) -> list[str]`
  - 逐节点 `visit` 并扁平化。
  - 对普通 body 不主动加缩进；缩进由调用点统一通过 `_indent_lines` 处理。

- `visit_GotoStmt(self, node) -> list[str]`
  - 若当前处于 flow 模式且 target 在 `self.flow_paragraphs`，输出 `__pc = "..."; continue FLOW;`。
  - 否则退回 `LeafJavaVisitor.visit_GotoStmt`，复用步骤23 的 flow_label 无关分支。

- `visit_Leaf(self, node) -> list[str]`
  - 若 token 是 `EXIT` 且处于 flow 模式，输出 `break FLOW;`。
  - 其它叶子委托 `LeafJavaVisitor.visit_Leaf`。

- `visit_PerformStmt(self, node) -> list[str]`
  - 先复用 `translate_perform_loop` 渲染循环壳。
  - 有 inline body 时递归渲染。
  - 无 inline body 且有 target 时，走 `_perform_target`。

- `_perform_target(self, node, indent: int = 0) -> list[str]`
  - 复刻 `_perform_range/_perform_single_paragraph/_perform_range_paragraph` 的可迁逻辑。
  - 写 `ctx.pending_range_methods`，value 仍保持 `[(label, body_lines), ...]` 旧契约，以便 `body_context.render_pending_range_methods` 继续 drain。

设计思路：本步把“flow 状态”放在 `SectionJavaVisitor` 实例字段中，而不是扩 `LeafCtx`。这样保留步骤23 的边界：叶子译器仍不读取骨架瞬态，骨架态只属于骨架 visitor。

### 2.2 调整 `asg/visitor.py`

- 不移动 `LeafJavaVisitor`。
- `LeafJavaVisitor.visit_PerformStmt` 保持现状，仍对 out-of-line PERFORM 输出 `// TODO-PERFORM-CALL`；它是叶子级 visitor。
- `SectionJavaVisitor` 作为新文件引入，避免 `asg/visitor.py` 继续膨胀。

### 2.3 `scripts/diff_asg_vs_legacy.py`

新增 `--verb SECTION`：

- legacy：对每个 section，`split_paragraphs` + `segment` 后调用 `rules.build_section(paras, ctx, force_sm=False)`。
- asg：`build_asg(program)` 后对每个 `Section` 调 `SectionJavaVisitor(ctx).render_section(section)`。
- 比对范围先跳过会触发 `_rewrite_begn_loops` 的结构吸收样例，或在脚本中标记为非本步范围。

---

## 3. 关键边界

1. `ctx.flow_label/flow_paragraphs` 不再写入 leaf 层。新 visitor 自己持有 `flow_label` 与 `flow_paragraphs`，只在 `visit_GotoStmt/visit_Leaf(EXIT)` 使用。
2. `pending_range_methods` 继续用旧数据结构，避免本步牵动 `body_context.render_pending_range_methods`。
3. ASG 的 `ProcRef` 已由 `asg.registry` 解析，但本步仍优先保持旧行为逐字符一致：输出方法名继续走 `ctx.section_to_method(name)` 和 `spec_loader.perform_range_method(...)`。
4. 旧 `rules.build_section` 先跑 `_rewrite_begn_loops`，新 visitor 本步不迁该 pass；因此 `SECTION` 比对样例必须排除 BEGN/READR/写 IO 结构吸收，避免伪差异。

---

## 4. 验收与测试

新增测试：

1. `TestAsgSectionVisitorFlow`
   - 无 GO：按 paragraph 顺序输出，含 `// paragraph X`。
   - 回跳 GO：输出 `String __pc`、`switch`、`continue FLOW`。
   - force_sm 前向 GO：合成区间方法场景也走状态机。

2. `TestAsgSectionVisitorPerformTarget`
   - `PERFORM SECTION` 与旧 `_perform_range` 输出一致。
   - `PERFORM paragraph` 登记 `ctx.pending_range_methods` 并输出 `this.pXxx();`。
   - `PERFORM A THRU B` paragraph 区间登记合成方法。

3. `TestDiffAsgVsLegacySection`
   - 内联 COBOL 样例包含 paragraph、GO 回跳、EXIT、PERFORM paragraph/THRU。
   - 不包含 BEGN/READR/写 IO 结构吸收。
   - `--verb SECTION` 两路逐字符一致。

回归闸：

- `python -m unittest test_translation`
- `python scripts/diff_asg_vs_legacy.py <fixture> --verb SECTION`
- 旧 config snapshot 零 diff（若本步只旁路不接主线，预期旧产物零变化）

---

## 5. 落地步骤（认可后执行）

1. 新增 `asg/section_visitor.py`，实现 `SectionJavaVisitor` 与 helper。
2. 为 `scripts/diff_asg_vs_legacy.py` 增 `SECTION` sampler。
3. 增加单测覆盖状态机、PERFORM out-of-line、SECTION 比对。
4. 跑全量单测与 SECTION 比对。
5. 回填本设计实现结果、更新 `docs/架构索引/项目总览.md`，写 `docs/操作记录/步骤24-骨架装配迁visitor操作记录.md`。

---

## 6. 开放问题（留后续刀）

- BEGN/NEXTR foreach、单次 BEGN、READR/写 IO 结构吸收如何从 `_rewrite_begn_loops` 迁为 ASG 预变换或骨架 visitor pass。
- `struct_rebind` 是否继续挂在语句节点，还是改成显式 `RebindScope` 节点。
- 主线何时从 `rules.build_section` 切到 `SectionJavaVisitor`，以及切换前是否需要完整 Java 方法体级 snapshot 比对。

---

## 7. 实现结果（2026-06-29 落地回填）

**与设计一致，范围未越界**：

- 新增 `asg/section_visitor.py`：`SectionJavaVisitor` 继承 `LeafJavaVisitor`，迁入 paragraph 装配、状态机壳、flow dispatch、PERFORM out-of-line 目标解析；`flow_label/flow_paragraphs` 只保存在 visitor 实例中，未扩 `LeafCtx`。
- `asg.nodes.Paragraph` 增 `body_lines`，`asg.builder` 填原始 COBOL 行，供 paragraph/THRU 登记 `ctx.pending_range_methods` 时保持旧契约 `[(label, body_lines), ...]`。
- `asg.__init__` 导出 `SectionJavaVisitor`。
- `scripts/diff_asg_vs_legacy.py` 增 `--verb SECTION`，旧路按 `rules.build_section` 后回填 leaves，新路按 `SectionJavaVisitor.render_section`，比对完整可迁 SECTION 产物。
- 新增 7 条测试：`TestAsgSectionVisitorFlow`(3)、`TestAsgSectionVisitorPerformTarget`(3)、`TestDiffAsgVsLegacySection`(1)。

**验收结果**：

- `python -m unittest test_translation.TestAsgSectionVisitorFlow test_translation.TestAsgSectionVisitorPerformTarget test_translation.TestDiffAsgVsLegacySection -v` → 7 tests OK。
- `python -m unittest test_translation` → 158 tests OK（skipped=2）。
- `python scripts\diff_asg_vs_legacy.py tests\fixtures\minimal.cob --verb SECTION` → `[OK] ... 2 条 SECTION 两路逐字符一致`。
- `python test_smoke.py` → 1 test OK。

**保留边界**：

- 旧主线仍由 `rules.build_section` 驱动，未接 `render_skeleton`。
- BEGN/NEXTR、READR/写 IO 结构吸收与 `struct_rebind` 未迁，留后续结构吸收刀。
