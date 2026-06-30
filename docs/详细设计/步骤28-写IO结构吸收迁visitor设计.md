# 步骤28 写 IO 结构吸收迁 visitor 设计（UPDAT/WRITR/DELET）
状态：已实现（2026-06-29 用户认可后落地）

定位：承接步骤27。步骤25-27 已把 BEGN foreach、BEGN single、READR/READS single 三类结构吸收迁到 ASG typed rewrite + `SectionJavaVisitor`。本步骤迁移旧 `translator/rules.py` 中写 IO 的结构吸收：

- `_write_io_ops`
- `_is_op_delete`
- `_is_init_params`
- `_write_statuz_form`
- `_match_write_single`
- `_render_write_single`

目标是让 `--verb SECTION` 的 ASG 路线覆盖 UPDAT/WRITR/DELET 等写 IO 结构，旧主线仍保持不切换。

---

## 1. 本步目标与非目标

**目标**：

1. 在 ASG 侧识别单条写 IO：
   - setup 中存在 `MOVE <写功能码> TO pfx-FUNCTION`；
   - 后续 `CALL 'xxxIO' USING pfx-PARAMS`；
   - setup 中可包含 `MOVE val TO pfx-<field>` 作为 setter；
   - setup 中若存在 `MOVE SPACES/LOW-VALUES/... TO pfx-PARAMS` 或 `INITIALIZE pfx-PARAMS`，表示插入新实体；
   - CALL 后可选紧邻 `IF pfx-STATUZ ...`，仅吸收 `STATUZ NOT = O-K` 一类错误分支。
2. 新增 ASG 节点 `IoWriteSingleStmt`，表达写 IO 吸收结果：
   - `plain`：渲染可选 new、setters、`repo.save(var)` 或 `repo.delete(var)`；
   - `error`：渲染可选 new、setters、`try { save/delete + try_tail } catch { then_body }`。
3. 在 `asg.structure_rewrite.rewrite_structures` 中追加写 IO pass，顺序对齐旧 `_rewrite_begn_loops`：
   - BEGN foreach -> BEGN single -> READR/READS single -> write IO single。
4. `SectionJavaVisitor` 新增 `visit_IoWriteSingleStmt`，逐字符串对齐旧 `_render_write_single`。
5. 继续复用 `struct_rebind`：setter、`then_body`、`try_tail` 内的 `pfx-FIELD` 绑定到实体变量。

**非目标**：

- 不切换主翻译路线。
- 不抽公共 IO pass 框架；本步最多复用步骤27已有 helper，避免提前抽象。
- 不扩大 STATUZ 形态识别范围；旧路径不吸收的形态，新路径也不吸收。

---

## 2. 节点与文件设计

### 2.1 `asg/nodes.py`

新增：

```python
@dataclass
class IoWriteSingleStmt:
    pfx: str = ""
    name: str = ""
    func: str = ""
    is_new: bool = False
    is_delete: bool = False
    setters: list = field(default_factory=list)
    mode: str = "plain"       # plain | error
    then_body: list = field(default_factory=list)
    try_tail: list = field(default_factory=list)
    raw: str = ""
    lineno: int = 0
```

字段对齐旧 `_match_write_single` 返回 dict：

- `is_new`：是否需要声明并 new 实体；
- `is_delete`：选择 `repo.delete(var)`，否则 `repo.save(var)`；
- `setters`：CALL 前 setup 中的字段赋值节点；
- `then_body`：错误处理分支，渲染进 `catch`；
- `try_tail`：CALL 后剩余语句，渲染进 `try`。

### 2.2 `asg/structure_rewrite.py`

新增 typed-node 版写 IO helpers：

- `_write_io_ops(ctx) -> set`
- `_is_op_delete(func, ctx) -> bool`
- `_is_init_params_node(node, pfx) -> bool`
- `_write_statuz_form(cond_tokens, pfx)`
- `_match_write_single_nodes(stmts, ctx)`

复用步骤27已有 helper：

- `_stmt_call_io`
- `_stmt_touches_pfx_node`
- `_setup_func_code_nodes`
- `_move_key_target_node`
- `_is_statuz_if_node`
- `_split_and`
- `_parse_statuz_term`

新增 pass：

```python
def rewrite_write_single(paragraphs, ctx):
    ...
```

命中后替换为：

```python
before = para.stmts[:info["setup_start"]]
after = para.stmts[info["consume_to"]:]
replace(para, stmts=before + [IoWriteSingleStmt(...)] + after)
```

消费规则对齐旧实现：

- `plain`：只消费 setup + CALL；
- `error`：消费 setup + CALL + IF，并把 CALL 后所有剩余语句放入 `try_tail`，因此 `after` 为空。

`rewrite_structures` 顺序改为：

```python
paragraphs = rewrite_begn_foreach(paragraphs, ctx)
paragraphs = rewrite_begn_single(paragraphs, ctx)
paragraphs = rewrite_readr_single(paragraphs, ctx)
paragraphs = rewrite_write_single(paragraphs, ctx)
return paragraphs
```

`tag_rebind_nodes` 追加 `IoWriteSingleStmt` 分支，递归标记 `setters`、`then_body`、`try_tail`。

### 2.3 `asg/section_visitor.py`

新增 `visit_IoWriteSingleStmt`：

1. repo、record class、变量名与旧 `_render_write_single` 一致：
   - `repo = resolve_io_info(...).field_name`，缺省为 `pfxRepository`；
   - `rec_cls = Pascal(pfx) + "Record"`；
   - `var = java(pfx)`。
2. `is_new` 为真时输出：

```java
XxxRecord xxx = new XxxRecord();
```

3. setters 使用 `_render_rebound_body(node.setters, {pfx: var}, 0)` 渲染，让 `MOVE val TO pfx-FIELD` 走 leaf assign 的 record setter 路径。
4. 操作行：

```java
repo.delete(var);
```

或：

```java
repo.save(var);
```

5. `plain` 直接追加操作行返回。
6. `error` 渲染：

```java
try {
    repo.save(var);
    ...
} catch (Exception e) {
    ...
}
```

其中 `try_tail` 与 `then_body` 均使用同一 rebind。

`_collect_gotos` 追加 `IoWriteSingleStmt` 分支，覆盖 `setters`、`then_body`、`try_tail`。

---

## 3. 关键边界

1. 写功能码集合来自 `ctx.io_default_pattern.operations` 中模板包含 `save` 或 `delete` 的 code。
2. 删除判断仍按模板是否包含 `delete`，不按功能码名称硬编码。
3. `setters` 只收 `MOVE val TO pfx-<field>`，排除 `FUNCTION/FORMAT/STATUZ/PARAMS`。
4. `is_new` 只识别旧路径已支持的 `INITIALIZE pfx-PARAMS` 或 `MOVE SPACES/SPACE/ZEROS/ZEROES/ZERO/LOW-VALUES/HIGH-VALUES TO pfx-PARAMS`。
5. CALL 后的 STATUZ IF 若不是 `NOT = O-K` 类错误形态，整段不吸收，交回原节点渲染。
6. pass 顺序放在 READR 后，避免同一段中读写功能码混淆；实际命中仍由功能码集合互斥兜底。

---

## 4. 测试计划

新增测试：

1. `TestAsgWriteSingleRewrite`
   - WRITR + init params -> `IoWriteSingleStmt(is_new=True, is_delete=False, mode="plain")`；
   - UPDAT + setters + `IF STATUZ NOT = O-K` -> `mode="error"`，`try_tail` 被吸收；
   - DELET -> `is_delete=True`；
   - 不识别 STATUZ 形态 -> 不改写。
2. `TestAsgWriteSingleVisitor`
   - WRITR new entity 产物与旧 `_render_write_single` 一致；
   - UPDAT error try/catch 产物与旧路线一致；
   - setters 内 `pfx-FIELD` 经 `struct_rebind` 输出为实体 setter；
   - DELET 输出 `repo.delete(var);`。

回归：

- `python -m unittest test_translation.TestAsgWriteSingleRewrite test_translation.TestAsgWriteSingleVisitor -v`
- `python -m unittest test_translation`
- `python scripts\diff_asg_vs_legacy.py tests\fixtures\minimal.cob --verb SECTION`
- `python test_smoke.py`
- `python -m py_compile asg\structure_rewrite.py asg\section_visitor.py asg\visitor.py asg\nodes.py`

---

## 5. 落地步骤（认可后执行）

1. `asg/nodes.py` 新增 `IoWriteSingleStmt`。
2. `asg/structure_rewrite.py` 新增写 IO helpers 与 `rewrite_write_single`，并接入 `rewrite_structures` / `tag_rebind_nodes`。
3. `asg/section_visitor.py` 新增 `visit_IoWriteSingleStmt` 与 `_collect_gotos` 递归。
4. 补写单测。
5. 跑目标测试、全量测试、SECTION 比对与 smoke。
6. 回填设计实现结果、项目总览和操作记录。

---

## 6. 开放问题

- 写 IO 与读 IO helper 后续是否抽到 `asg/io_patterns.py`：本步先不抽，等写 IO 落地后再判断重复是否足够稳定。
- 是否把更多 STATUZ 写法纳入吸收：本步不扩大行为面，保持与旧路线一致。

---

## 7. 实现结果（2026-06-29 落地回填）

**与设计一致，范围未越界**：

- `asg.nodes` 新增 `IoWriteSingleStmt`，并在 `asg.__init__` 导出。
- `asg.structure_rewrite` 新增 `rewrite_write_single`，接入统一 `rewrite_structures`，顺序为 BEGN foreach -> BEGN single -> READR/READS -> write IO。
- 新增 typed-node 版写 IO helpers：`_write_io_ops`、`_is_op_delete`、`_is_init_params_node`、`_write_statuz_form`、`_match_write_single_nodes`。
- `tag_rebind_nodes` 支持 `IoWriteSingleStmt` 的 `setters`、`then_body`、`try_tail`。
- `SectionJavaVisitor` 新增 `visit_IoWriteSingleStmt`，覆盖 WRITR new/save、UPDAT reuse/save/error try-catch、DELET delete。
- `_collect_gotos` 支持递归扫描 `IoWriteSingleStmt`，避免错误分支内跳转漏判。
- 新增 7 条测试：`TestAsgWriteSingleRewrite`(4) 与 `TestAsgWriteSingleVisitor`(3)。

**验收结果**：

- `python -m unittest test_translation.TestAsgWriteSingleRewrite test_translation.TestAsgWriteSingleVisitor -v` -> 7 tests OK。
- `python -m unittest test_translation.TestAsgBegnForeachRewrite test_translation.TestAsgBegnForeachVisitor test_translation.TestAsgBegnSingleRewrite test_translation.TestAsgBegnSingleVisitor test_translation.TestAsgReadrSingleRewrite test_translation.TestAsgReadrSingleVisitor test_translation.TestAsgWriteSingleRewrite test_translation.TestAsgWriteSingleVisitor -v` -> 18 tests OK。
- `python -m unittest test_translation` -> 176 tests OK（skipped=2）。
- `python scripts\diff_asg_vs_legacy.py tests\fixtures\minimal.cob --verb SECTION` -> 2 条 SECTION 两路逐字符一致。
- `python test_smoke.py` -> 1 test OK。
- `python -m py_compile asg\structure_rewrite.py asg\section_visitor.py asg\visitor.py asg\nodes.py` -> OK。
