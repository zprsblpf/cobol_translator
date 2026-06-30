# 步骤26　单次 BEGN 结构吸收迁 visitor 设计（骨架装配迁 visitor·结构吸收第二刀）

状态：🟢已实现（2026-06-29 用户认可后落地）

定位：承接步骤25。步骤25 已把 `_rewrite_begn_loops` Pass 1（BEGN+NEXTR 自跳循环）迁到 ASG typed rewrite + `SectionJavaVisitor`。
本步迁旧 `_rewrite_begn_loops` Pass 2 的第一类：**单次 BEGN 等值定位**。

旧实现位置：`translator/rules.py` `_match_begn_single` / `_render_begn_single` / `_rewrite_begn_loops` Pass 2。

---

## 1. 本步目标与非目标

**目标**：

1. 在 ASG 侧识别单次 BEGN：
   - 同一 paragraph 内存在 setup；
   - setup 中有 `MOVE BEGN TO pfx-FUNCTION`；
   - 后续 `CALL 'xxxIO' USING pfx-PARAMS`；
   - CALL 后紧跟 `IF ...`；
   - IF then 分支不含 GO TO 回跳；
   - IF 条件可提取等值键。
2. 新增 ASG 节点 `BegnSingleStmt`，表达“单次 BEGN findBy...Begn + isEmpty 分支”。
3. 在 `asg.structure_rewrite` 中新增 `rewrite_begn_single`，并由统一入口顺序执行：
   - 先跑步骤25 `rewrite_begn_foreach`；
   - 再跑本步 `rewrite_begn_single`；
   - 顺序对齐旧 `_rewrite_begn_loops`：Pass 1 命中 loop 后该 paragraph 不再进入 Pass 2。
4. `SectionJavaVisitor` 渲染 `BegnSingleStmt`：
   - `List<Rec> list = repo.findBy<Key...>Begn(vals);`
   - then body 非空时：`if (list.isEmpty()) { ... }`
5. 保持旧主线不切换，只扩 `--verb SECTION` 可迁场景的覆盖。

**非目标**：

- 不迁 READR/READS 单条读（`_match_readr_single/_render_readr_single`）。
- 不迁 UPDAT/WRITR/DELET 单条写（`_match_write_single/_render_write_single`）。
- 不把 BEGN 单次与 READR 抽象成通用 IO 节点；本步先沿用独立 `BegnSingleStmt`，降低风险。
- 不切换 `body_context.translate_section_body` 主线。

---

## 2. 节点与文件设计

### 2.1 `asg/nodes.py`

新增：

```python
@dataclass
class BegnSingleStmt:
    pfx: str
    name: str
    keys: list[tuple[str, str]]
    then_body: list = field(default_factory=list)
    raw: str = ""
    lineno: int = 0
```

字段含义：

- `pfx`：结构前缀，如 `ELPO`。
- `name`：IO 子程序名，如 `ELPOIO`。
- `keys`：从 IF 条件提取的 finder 键值对，复用步骤25 的 `_begn_breakout_keys`。
- `then_body`：IF then 分支节点列表。旧逻辑只在 `list.isEmpty()` 时执行 then。

### 2.2 `asg/structure_rewrite.py`

新增统一入口：

- `rewrite_structures(paragraphs, ctx) -> list[Paragraph]`
  - `paragraphs = rewrite_begn_foreach(paragraphs, ctx)`
  - `paragraphs = rewrite_begn_single(paragraphs, ctx)`
  - 后续 READR/写 IO 继续追加到这里，避免 `SectionJavaVisitor` 逐步堆多个 pass 调用。

新增：

- `rewrite_begn_single(paragraphs, ctx) -> list[Paragraph]`
  - 逐 paragraph 扫描当前 `stmts`。
  - 若 paragraph 第一个 stmt 已是 `BegnForeachStmt`，跳过。
  - 调 `_match_begn_single_nodes(stmts, ctx)`。
  - 命中后以 `before + [BegnSingleStmt] + after` 替换，其中：
    - `before = stmts[:setup_start]`
    - `after = stmts[call_idx + 2:]`
    - 对齐旧实现跳过 `CALL + IF`。

辅助：

- `_match_begn_single_nodes(stmts, ctx) -> dict | None`
  - typed-node 版 `_match_begn_single`。
  - 复用步骤25 的 `_stmt_call_io/_setup_has_begn/_contains_goto/_begn_breakout_keys/_stmt_touches_pfx` 等 helper。

### 2.3 `asg/section_visitor.py`

- `render_paragraphs` 从调用 `rewrite_begn_foreach` 改为调用 `rewrite_structures`。
- 新增 `visit_BegnSingleStmt`：
  - repo/record/list/finder/vals 逻辑对齐旧 `_render_begn_single`。
  - then body 通过 `self.visit` 递归渲染，并缩进一级。
  - 本步不做 `struct_rebind`：旧 `_render_begn_single` 没有把 then 分支重绑定到 record，只是把 then body 交给 `build_skeleton`，保持一致。

### 2.4 `scripts/diff_asg_vs_legacy.py`

无需新增 verb。继续通过 `--verb SECTION` 比对完整可迁 SECTION 产物。

---

## 3. 关键边界

1. 单次 BEGN 必须有紧随 CALL 的 IF；无 IF 不吸收。
2. IF then 分支含 GO TO 时不吸收，保留给 loop pattern 或旧控制流。
3. 键提取仍走 `_begn_breakout_keys` 形态：每个 OR term 为 `pfx-KEY NOT = VAL`，`pfx-STATUZ NOT = O-K` 可跳过。
4. 本步不处理 CALL 后其它 STATUZ 形态；READR 的 STATUZ 三态留步骤27。

---

## 4. 测试计划

新增测试：

1. `TestAsgBegnSingleRewrite`
   - 命中 setup+CALL+IF，生成 `BegnSingleStmt`。
   - 保留 `before/after` 语句顺序。
   - IF then 含 GO TO 时不改写。

2. `TestAsgBegnSingleVisitor`
   - 渲染 `List<XRecord> xList = xRepository.findBy...Begn(...);`
   - then body 非空时渲 `if (xList.isEmpty()) { ... }`
   - 与旧 `rules.build_section` 逐字符一致。

回归：

- `python -m unittest test_translation`
- `python scripts\diff_asg_vs_legacy.py tests\fixtures\minimal.cob --verb SECTION`
- `python test_smoke.py`

---

## 5. 落地步骤（认可后执行）

1. `asg/nodes.py` 增 `BegnSingleStmt` 并导出。
2. `asg/structure_rewrite.py` 增 `rewrite_structures` 与 `rewrite_begn_single`。
3. `asg/section_visitor.py` 改用 `rewrite_structures`，新增 `visit_BegnSingleStmt`。
4. 补测试。
5. 跑目标测试、全量测试、SECTION 比对闸。
6. 回填本设计、项目总览、操作记录。

---

## 6. 开放问题（留后续刀）

- READR/READS 是否建 `IoReadSingleStmt`，以及它是否复用 `BegnSingleStmt` 的 renderer helper。
- 写 IO 是否建 `IoWriteSingleStmt`，并与 READR 共用 setup/window matcher。
- 长期是否把 `_begn_breakout_keys` 等 helper 从 `structure_rewrite.py` 提升为通用 `asg/io_patterns.py`。

---

## 7. 实现结果（2026-06-29 落地回填）

**与设计一致，范围未越界**：

- `asg.nodes` 新增 `BegnSingleStmt`。
- `asg.structure_rewrite` 新增统一入口 `rewrite_structures`，顺序执行 `rewrite_begn_foreach` → `rewrite_begn_single`。
- `rewrite_begn_single` 复刻旧 `_rewrite_begn_loops` Pass 2 的单次 BEGN 分支：
  - 识别 setup+CALL+IF；
  - then 分支含 GO TO 时保守不吸收；
  - 命中后以 `before + BegnSingleStmt + after` 替换。
- `SectionJavaVisitor.render_paragraphs` 改用 `rewrite_structures`；新增 `visit_BegnSingleStmt` 渲染 `findBy...Begn` + `list.isEmpty()`。
- 新增 3 条测试：`TestAsgBegnSingleRewrite`(2)、`TestAsgBegnSingleVisitor`(1)。

**验收结果**：

- `python -m unittest test_translation.TestAsgBegnSingleRewrite test_translation.TestAsgBegnSingleVisitor -v` → 3 tests OK。
- `python -m unittest test_translation` → 164 tests OK（skipped=2）。
- `python scripts\diff_asg_vs_legacy.py tests\fixtures\minimal.cob --verb SECTION` → `[OK] ... 2 条 SECTION 两路逐字符一致`。
- `python test_smoke.py` → 1 test OK。
- `python -m py_compile asg\structure_rewrite.py asg\section_visitor.py asg\visitor.py asg\nodes.py` → OK。

**保留边界**：

- 旧主线未切换。
- READR/READS 单条读、写 IO 结构吸收未迁。
