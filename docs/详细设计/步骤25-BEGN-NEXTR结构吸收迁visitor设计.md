# 步骤25　BEGN/NEXTR 结构吸收迁 visitor 设计（骨架装配迁 visitor·结构吸收第一刀）

状态：🟢已实现（2026-06-29 用户认可后落地）

定位：承接步骤24 `SectionJavaVisitor`。步骤24 已把 paragraph 装配、状态机壳、flow dispatch、PERFORM out-of-line 目标解析迁入 ASG 侧旁路 visitor。
本步开始迁旧 `rules._rewrite_begn_loops` 中的结构吸收 pass，但只切第一类：

- **本步迁**：BEGN + NEXTR 自跳循环 → `List<Record>` + `for-each`。
- **后续迁**：单次 BEGN、READR/READS 单条读、UPDAT/WRITR/DELET 单条写。

旧实现位置：`translator/rules.py` `_match_begn_loop` / `_render_begn_foreach` / `_strip_struct_setup` / `_tag_rebind` / `_rewrite_begn_loops` Pass 1。

---

## 1. 本步目标与非目标

**目标**：

1. 在 ASG 侧新增一个结构改写 pass，识别 `BEGN + CALL + IF跳出 + NEXTR回跳` 的自跳循环段。
2. 新增 ASG 节点 `BegnForeachStmt`，表达“已吸收为 for-each 的结构化循环”，避免在 rewrite 阶段直接吐 Java raw 行。
3. `SectionJavaVisitor` 在渲染 paragraph 前先跑该 pass；命中后：
   - 剥除前序 setup paragraph 中对同一 `pfx-*` 的 setup 赋值；
   - loop paragraph 替换为 `BegnForeachStmt`；
   - 渲染成 `List<Rec> list = repo.findBy...Begn(keys); for (Rec rec : list) { ... }`。
4. 补齐 `struct_rebind` 的 visitor 语义：for-each 体内的 `pfx-FIELD` 必须绑定到循环变量，而不是参数对象。
5. 扩 `scripts/diff_asg_vs_legacy.py --verb SECTION` 的覆盖样例，证明旧 `rules.build_section` 与 ASG `SectionJavaVisitor` 在 BEGN+NEXTR foreach 场景下逐字符一致。

**非目标**：

- 不迁单次 BEGN（`_match_begn_single/_render_begn_single`）。
- 不迁 READR/READS 单条读（`_match_readr_single/_render_readr_single`）。
- 不迁 UPDAT/WRITR/DELET 单条写（`_match_write_single/_render_write_single`）。
- 不切换主线；`translator.skeleton_gen.body_context` 仍调用 `rules.build_section`。

---

## 2. 节点与文件设计

### 2.1 `asg/nodes.py`

新增：

```python
@dataclass
class BegnForeachStmt:
    pfx: str
    name: str
    keys: list[tuple[str, str]]
    filters: list = field(default_factory=list)
    body: list = field(default_factory=list)
    raw: str = ""
    lineno: int = 0
```

字段含义：

- `pfx`：结构前缀，如 `ELPO`。
- `name`：IO 子程序名，如 `ELPOIO`。
- `keys`：从跳出条件解析出的 finder 键值对，沿用旧 `_begn_breakout_keys` 的 `(key, value)`。
- `filters`：结果集过滤 IF 节点列表，旧 `_is_filter_if` 命中的 `IF cond -> NEXTR + GO loop`。
- `body`：for-each 主体节点列表，已剥除尾部 `MOVE NEXTR` 与 `GO TO loop`。

设计思路：用结构节点表达“已吸收的语义”，避免在 ASG pass 中生成 raw Java。Java 只在 visitor 层渲染，仍保持“ASG → visitor”的边界。

### 2.2 新增 `asg/structure_rewrite.py`

职责：对 `list[Paragraph]` 做纯 ASG 改写，不渲染 Java。

方法：

- `rewrite_begn_foreach(paragraphs, ctx) -> list[Paragraph]`
  - 复刻 `_rewrite_begn_loops` Pass 1。
  - 命中 loop paragraph 后，把该 paragraph 的 `stmts` 替换为 `[BegnForeachStmt(...)]`。
  - 对 loop 前所有 paragraph 调 `_strip_struct_setup_nodes(stmts, pfx)`，剥除 `MOVE ... TO pfx-*` / `INITIALIZE pfx-*`。
  - 未命中返回原 paragraph 列表。

- `_match_begn_loop(label, stmts, ctx) -> dict | None`
  - typed-node 版本，识别首条 `CallStmt`、跳出 IF、filter IF、尾部 NEXTR/GO 自跳。
  - 对不安全 body 内 GO TO 保守放弃。

- `_tag_rebind_nodes(stmts, rebind) -> None`
  - 给 body/filter 内节点递归写 `node.struct_rebind = {pfx: loop_var}`。
  - 递归 If/Evaluate/Perform inline body，保证嵌套叶子也能重绑定。

边界：该文件可以复用 `translator.leaf.cond.translate_condition`、`translator.leaf.expr._operand` 吗？
不需要。rewrite 只做识别和节点变换；条件翻译、operand 渲染仍放 `SectionJavaVisitor.visit_BegnForeachStmt`。

### 2.3 修改 `asg/visitor.py`

`LeafJavaVisitor` 增加统一 rebind 包裹：

- 新增 `_with_rebind(self, node, render_fn)`：
  - 读取 `getattr(node, "struct_rebind", None)`；
  - 临时修改 `ctx.struct_objects`；
  - 调 `render_fn()`；
  - finally 恢复。

应用到：

- `visit_MoveStmt`
- `visit_Leaf`
- `visit_CallStmt`
- `visit_IfStmt` 条件渲染与 body 渲染
- `visit_EvaluateStmt` body
- `visit_PerformStmt` inline body

设计思路：旧 rules 的 `translate_leaf` 在叶子回填时统一处理 `stmt.struct_rebind`；visitor 直译没有叶子回填阶段，因此必须在 visitor 调用 leaf 译器前处理同一语义。

### 2.4 修改 `asg/section_visitor.py`

- `render_paragraphs` 入口先调用 `rewrite_begn_foreach(paragraphs, ctx)`。
- 新增 `visit_BegnForeachStmt`：
  - 查 `resolve_io_info(node.name, ctx.io_programs, ctx.io_default_pattern)`；
  - 渲染 repo / record class / loop var / list var；
  - finder 名称与旧 `_render_begn_foreach` 一致：`findBy<Key...>Begn`；
  - 渲染 filters：`if (<cond>) { continue; }`；
  - 给 body/filter 打 `struct_rebind` 后递归渲染 body；
  - 临时把 `ctx.struct_objects[pfx] = loop_var`，保证 filter 条件中的 `pfx-FIELD` 也渲为 `loopVar.getField()`。

---

## 3. 比对闸

扩 `scripts/diff_asg_vs_legacy.py --verb SECTION` 的测试样例即可，不新增 verb。

比较方式仍为：

- legacy：`rules.build_section` 后回填 leaves。
- asg：`SectionJavaVisitor.render_section`。

本步完成后，含 BEGN+NEXTR foreach 的 SECTION 应逐字符一致。

---

## 4. 测试计划

新增测试：

1. `TestAsgBegnForeachRewrite`
   - 命中 BEGN+NEXTR 自跳循环，ASG paragraph 被替换为 `BegnForeachStmt`。
   - 前序 setup 中 `MOVE ... TO pfx-*` 被剥除。
   - exit label 必须是相邻下一 paragraph，否则不改写。

2. `TestAsgBegnForeachVisitor`
   - 渲染 `List<XRecord> xList = xRepository.findBy...Begn(...);`
   - 渲染 `for (XRecord x : xList) {`
   - filter IF 渲为 `if (...) { continue; }`
   - body 内 `pfx-FIELD` 经 rebind 渲为 loop var getter/setter。

3. `TestDiffAsgVsLegacySectionBegnForeach`
   - 内联 COBOL 样例包含 setup paragraph、loop paragraph、exit paragraph。
   - 旧/新 SECTION 产物逐字符一致。

回归：

- `python -m unittest test_translation`
- `python scripts\diff_asg_vs_legacy.py tests\fixtures\minimal.cob --verb SECTION`

---

## 5. 落地步骤（认可后执行）

1. `asg/nodes.py` 增 `BegnForeachStmt`。
2. 新增 `asg/structure_rewrite.py`，实现 BEGN foreach typed-node rewrite。
3. 修改 `LeafJavaVisitor`，统一支持 `struct_rebind`。
4. 修改 `SectionJavaVisitor`，接入 rewrite 并渲染 `BegnForeachStmt`。
5. 扩测试与 `SECTION` 比对样例。
6. 跑全量测试，回填本设计、项目总览、操作记录。

---

## 6. 开放问题（留后续刀）

- 单次 BEGN 是否也建结构节点（如 `BegnSingleStmt`），还是复用更通用的 `IoReadStmt`。
- READR/READS 与写 IO 是否合并成一套 `IoSingleStmt` 节点。
- `struct_rebind` 长期是否保留动态属性，还是升为显式 `RebindScope` 节点。

---

## 7. 实现结果（2026-06-29 落地回填）

**与设计一致，范围未越界**：

- `asg.nodes` 新增 `BegnForeachStmt`，表达 BEGN+NEXTR 自跳循环吸收后的结构节点。
- 新增 `asg/structure_rewrite.py`：
  - `rewrite_begn_foreach(paragraphs, ctx)` 复刻旧 `_rewrite_begn_loops` Pass 1；
  - 命中后把 loop paragraph 替换为 `BegnForeachStmt`；
  - 剥除前序 paragraph 中同 `pfx-*` setup；
  - `tag_rebind_nodes` 给 filters/body 递归打 `struct_rebind`。
- `LeafJavaVisitor` 增 `_with_rebind`，让 visitor 直译路径在调用 leaf 译器/条件译器前临时应用 `ctx.struct_objects` 重绑定；补齐旧 rules `translate_leaf` 回填阶段的 `struct_rebind` 语义。
- `SectionJavaVisitor.render_paragraphs` 接入 `rewrite_begn_foreach`；新增 `visit_BegnForeachStmt` 渲染 `List<Record>` + `for-each`，并在 filter/body 内应用 loop var 重绑定。
- `asg.__init__` 导出 `BegnForeachStmt`。
- 新增 3 条测试：`TestAsgBegnForeachRewrite`(2)、`TestAsgBegnForeachVisitor`(1)。

**验收结果**：

- `python -m unittest test_translation.TestAsgBegnForeachRewrite test_translation.TestAsgBegnForeachVisitor -v` → 3 tests OK。
- `python -m unittest test_translation` → 161 tests OK（skipped=2）。
- `python scripts\diff_asg_vs_legacy.py tests\fixtures\minimal.cob --verb SECTION` → `[OK] ... 2 条 SECTION 两路逐字符一致`。
- `python test_smoke.py` → 1 test OK。
- `python -m py_compile asg\structure_rewrite.py asg\section_visitor.py asg\visitor.py asg\nodes.py` → OK。

**保留边界**：

- 旧主线未切换。
- 单次 BEGN、READR/READS、写 IO 结构吸收未迁。
- `struct_rebind` 仍是动态属性，显式 `RebindScope` 留后续设计。
