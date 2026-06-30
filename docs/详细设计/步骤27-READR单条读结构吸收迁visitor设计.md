# 步骤27　READR/READS 单条读结构吸收迁 visitor 设计（骨架装配迁 visitor·结构吸收第三刀）

状态：🟢已实现（2026-06-29 用户认可后落地）

定位：承接步骤26。步骤25/26 已把 BEGN 查询族两类结构吸收迁入 ASG typed rewrite + `SectionJavaVisitor`。
本步迁旧 `_rewrite_begn_loops` Pass 2b：**READR/READS 单条读**。

旧实现位置：`translator/rules.py` `_read_io_ops` / `_statuz_form` / `_setup_func_code` / `_move_key_target`
/ `_match_readr_single` / `_render_readr_single` / `_render_rebound`。

---

## 1. 本步目标与非目标

**目标**：

1. 在 ASG 侧识别单条读：
   - setup 中有 `MOVE <READR/READS> TO pfx-FUNCTION`；
   - 后续 `CALL 'xxxIO' USING pfx-PARAMS`；
   - setup 中存在查询键 `MOVE val TO pfx-<field>`；
   - CALL 后可选紧跟 `IF pfx-STATUZ ...`。
2. 新增 ASG 节点 `IoReadSingleStmt`，表达单条读吸收结果：
   - `plain`：只渲 finder；
   - `ok/notok`：渲 finder + `if (record != null / == null)`；
   - `error`：渲 `try { finder + try_tail } catch { then_body }`。
3. `asg.structure_rewrite.rewrite_structures` 在 BEGN single 后追加 READR/READS pass：
   - 顺序对齐旧 `_rewrite_begn_loops`：BEGN foreach → BEGN single → READR/READS → 写 IO。
4. `SectionJavaVisitor` 新增 `visit_IoReadSingleStmt`，逐字符对齐旧 `_render_readr_single`。
5. 支持 record 重绑定：
   - `then_body` / `else_body` / `try_tail` 内 `pfx-FIELD` 绑定到 record 变量。

**非目标**：

- 不迁写 IO（UPDAT/WRITR/DELET），留步骤28。
- 不抽通用 IO 基类；若 READR 与写 IO 之后出现明显共性，步骤28 再提取 helper。
- 不切换主线。

---

## 2. 节点与文件设计

### 2.1 `asg/nodes.py`

新增：

```python
@dataclass
class IoReadSingleStmt:
    pfx: str
    name: str
    func: str
    keys: list[tuple[str, str]]
    mode: str = "plain"       # plain | ok | notok | error
    then_body: list = field(default_factory=list)
    else_body: list = field(default_factory=list)
    try_tail: list = field(default_factory=list)
    raw: str = ""
    lineno: int = 0
```

字段含义对齐旧 `_match_readr_single` 返回 dict。

### 2.2 `asg/structure_rewrite.py`

新增 helpers（typed-node 版）：

- `_read_io_ops(ctx) -> set`
- `_split_and(tokens) -> list[list[str]]`
- `_parse_statuz_term(term, pfx)`
- `_statuz_form(cond_tokens, pfx)`
- `_setup_func_code_nodes(stmts, pfx, codes)`
- `_move_key_target_node(node, pfx)`
- `_is_statuz_if_node(node, pfx)`
- `_match_readr_single_nodes(stmts, ctx)`

新增 pass：

- `rewrite_readr_single(paragraphs, ctx) -> list[Paragraph]`
  - 跳过已改写成 `BegnForeachStmt/BegnSingleStmt` 的 paragraph。
  - 命中后替换为 `before + [IoReadSingleStmt] + after`。
  - `after = stmts[consume_to:]`，对齐旧 `consume_to`：
    - plain：CALL 后继续；
    - ok/notok：跳过 CALL + IF；
    - error：CALL 后后续全进 try_tail，after 为空。

修改统一入口：

```python
paragraphs = rewrite_begn_foreach(...)
paragraphs = rewrite_begn_single(...)
paragraphs = rewrite_readr_single(...)
```

### 2.3 `asg/section_visitor.py`

新增 `visit_IoReadSingleStmt`：

- repo/record class/var/finder/vals 与旧 `_render_readr_single` 一致：
  - 若 `ctx.io_programs[name].operations[func]` 有显式方法名，取模板括号前方法名；
  - 否则派生 `findBy<Key...><Func.capitalize()>`。
- `plain`：返回 `[call_line]`。
- `error`：
  - `try {`
  - `    <call_line>`
  - 渲染 `try_tail`，对 `pfx` 重绑定为 record 变量；
  - `} catch (Exception e) {`
  - 渲染 `then_body`，同样重绑定；
  - `}`。
- `ok/notok`：
  - `if (var != null)` 或 `if (var == null)`；
  - then/else body 均重绑定。

重绑定实现复用步骤25 的 `tag_rebind_nodes` 和 `LeafJavaVisitor._with_rebind`。

---

## 3. 关键边界

1. 键必须来自 setup 内 `MOVE val TO pfx-<field>`，且目标字段不能是 `FUNCTION/FORMAT/STATUZ/PARAMS`。
2. STATUZ IF 形态不认识时，整体不吸收，保持旧路保守行为。
3. `error` 模式消费 CALL 后所有后续语句进 `try_tail`，对齐旧实现。
4. 功能码集合来自 `ctx.io_default_pattern.operations` 中模板包含 `findBy` 的 code。

---

## 4. 测试计划

新增测试：

1. `TestAsgReadrSingleRewrite`
   - READR + `IF STATUZ = O-K` → `IoReadSingleStmt(mode="ok")`。
   - READR + `IF STATUZ NOT = O-K AND ...` → `mode="error"` 且 `try_tail` 被吸收。
   - 无 key / STATUZ 形态不认识 → 不改写。

2. `TestAsgReadrSingleVisitor`
   - ok/notok 产物与旧路逐字符一致。
   - error try/catch 产物与旧路逐字符一致。
   - then/else/try_tail 内 `pfx-FIELD` 经 record 重绑定。

回归：

- `python -m unittest test_translation`
- `python scripts\diff_asg_vs_legacy.py tests\fixtures\minimal.cob --verb SECTION`
- `python test_smoke.py`

---

## 5. 落地步骤（认可后执行）

1. `asg/nodes.py` 增 `IoReadSingleStmt` 并导出。
2. `asg/structure_rewrite.py` 增 READR helpers 与 `rewrite_readr_single`。
3. `asg/section_visitor.py` 增 `visit_IoReadSingleStmt`。
4. 补测试。
5. 跑目标测试、全量测试、SECTION 比对闸。
6. 回填本设计、项目总览、操作记录。

---

## 6. 开放问题（留步骤28）

- 写 IO 是否复用 `IoReadSingleStmt` 的 setup/key/statuz helper，还是独立 `IoWriteSingleStmt`。
- READR/写 IO helper 是否在步骤28 后整理成 `asg/io_patterns.py`。

---

## 7. 实现结果（2026-06-29 落地回填）

**与设计一致，范围未越界**：

- `asg.nodes` 新增 `IoReadSingleStmt`。
- `asg.structure_rewrite` 新增 `rewrite_readr_single`，并在 `rewrite_structures` 中按 BEGN foreach → BEGN single → READR 顺序调用。
- 新增 typed-node 版 READR helpers：`_read_io_ops`、`_statuz_form`、`_setup_func_code_nodes`、`_move_key_target_node`、`_match_readr_single_nodes` 等。
- `SectionJavaVisitor` 新增 `visit_IoReadSingleStmt`，覆盖 `plain/ok/notok/error` 四种模式，then/else/try_tail 通过 `tag_rebind_nodes` + `_render_rebound_body` 应用 record 重绑定。
- 新增 5 条测试：`TestAsgReadrSingleRewrite`(3)、`TestAsgReadrSingleVisitor`(2)。

**验收结果**：

- `python -m unittest test_translation.TestAsgReadrSingleRewrite test_translation.TestAsgReadrSingleVisitor -v` → 5 tests OK。
- `python -m unittest test_translation` → 169 tests OK（skipped=2）。
- `python scripts\diff_asg_vs_legacy.py tests\fixtures\minimal.cob --verb SECTION` → `[OK] ... 2 条 SECTION 两路逐字符一致`。
- `python test_smoke.py` → 1 test OK。
- `python -m py_compile asg\structure_rewrite.py asg\section_visitor.py asg\visitor.py asg\nodes.py` → OK。

**保留边界**：

- 旧主线未切换。
- 写 IO 结构吸收未迁。
