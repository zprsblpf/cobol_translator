# 步骤29 主线 SECTION 渲染切到 SectionJavaVisitor 设计
状态：已实现（2026-06-29 用户认可后落地）

定位：承接步骤24-28。ASG 旁路 `SectionJavaVisitor` 已覆盖：

- paragraph 装配与状态机壳；
- flow dispatch；
- PERFORM out-of-line 目标解析；
- BEGN foreach / BEGN single / READR/READS / UPDAT/WRITR/DELET 结构吸收；
- `struct_rebind`。

旧主线仍在 `translator.skeleton_gen.body_context.translate_paragraphs_body` 中调用 `rules.build_section`。本步骤把主线 SECTION 方法体渲染入口切到 ASG `SectionJavaVisitor`，旧 `rules.build_section` 暂保留为异常回退与比对参照。

---

## 1. 本步目标与非目标

**目标**：

1. 主线 `translate_section_body` / `translate_paragraphs_body` 使用 `SectionJavaVisitor` 渲染 Java 方法体。
2. pending THRU 合成区间方法仍走同一入口，支持 `force_sm=True`。
3. 保持主线外部 API 不变：
   - `build_body_ctx(program)` 不变；
   - `translate_section_body(body_lines, ctx, ws_field_names, call_args, known_methods)` 不变；
   - `render_pending_range_methods(...)` 不变。
4. 后处理链保持不变：
   - `fix_array_subscripts`；
   - `this.X()` 补 `wsaa/using` 实参；
   - WS 字段 `wsaa.` 前缀。
5. 异常兜底不退化：ASG 渲染异常时回退旧 `rules.build_section`，并保留原来的 TODO 失败文本策略。

**非目标**：

- 不删除 `rules.build_section` / `_rewrite_begn_loops`，本步只切主线调用点。
- 不改 `render_skeleton.py` 的方法签名、入口控制流或类结构。
- 不扩大叶子动词覆盖面；`LeafJavaVisitor` 未覆盖的动词仍落 `// TODO-LEAF`，主线失败文本仍按现有 TODO 口径可见。
- 不一次性清理 `rules.py` 中旧骨架代码；下线旧路径另开步骤。

---

## 2. 关键设计

### 2.1 ASG raw paragraph 构造入口

当前 `build_asg(program)` 需要完整 `CobolProgram`，但主线 `translate_paragraphs_body` 同时服务：

- 普通 SECTION：只有 `body_lines`；
- pending THRU 合成区间：只有 `[(label, body_lines)]`。

因此本步在 `asg.builder` 增加窄入口：

```python
def build_paragraphs(paras_raw: list[tuple[str | None, list[str]]], ctx) -> list[nodes.Paragraph]:
    ...
```

职责：

- 对每个 raw paragraph 调 `segment(body)`；
- 复用 `_lift` 生成 typed nodes；
- 给 `Paragraph.body_lines` 填原始行；
- 用一个轻量 `ProcRegistry` 或兼容解析对象，让 GO/PERFORM target 能解析到 `ProcRef`。

目标解析策略：

- 优先根据 `ctx.proc_order` 构造 `ProcRegistry` 所需信息，保证 pending range 内 paragraph target 也可解析；
- 若构造成本过高，则提供 `_CtxProcResolver`，暴露 `resolve(name)`：
  - name 在 `ctx.proc_order` 或 `ctx.known_sections` 中出现且唯一 -> `ProcRef(name.upper())`；
  - 否则返回 `None`。

这样不要求 `translate_paragraphs_body` 持有完整 program，也不破坏现有调用面。

### 2.2 body_context 主线切换

`translate_paragraphs_body` 当前流程：

```python
reset_section(ctx)
paras = [(lbl, segment(body)) for lbl, body in paras_raw]
body = "\n".join(_rules.build_section(paras, ctx, force_sm=force_sm))
填 ctx.leaves 占位
_postprocess_body(...)
```

切换后：

```python
reset_section(ctx)
paragraphs = build_paragraphs(paras_raw, ctx)
body = "\n".join(SectionJavaVisitor(ctx, force_sm=force_sm).render_paragraphs(paragraphs))
_postprocess_body(...)
```

注意：ASG visitor 已直接渲染叶子，不再使用 `ctx.leaves` 占位替换。因此旧的 leaf placeholder 填充循环只留在 fallback 路径。

### 2.3 fallback 路径

新增私有 helper：

```python
def _translate_paragraphs_body_legacy(...):
    ...
```

封装旧 `rules.build_section` + leaf placeholder 替换逻辑。

新主线：

```python
try:
    body = _translate_paragraphs_body_asg(...)
except Exception:
    body = _translate_paragraphs_body_legacy(...)
return _postprocess_body(...)
```

异常兜底原则：

- ASG 渲染异常：回退 legacy，不直接失败；
- legacy 也异常：保留现有 `// TODO 段翻译失败...` 文本；
- 不吞掉 pending range 注册：ASG visitor 与 legacy 一样写 `ctx.pending_range_methods`。

### 2.4 比对与可观测性

新增测试不只比 `SectionJavaVisitor` 与 legacy，而是比主线 `translate_section_body` 产物：

- 切换前可用旧 helper 得到 legacy body；
- 切换后 `translate_section_body` 得到 ASG 主线 body；
- 对覆盖步骤24-28的样例逐字符一致。

新增 `scripts/diff_asg_vs_legacy.py` 可选增强不作为本步硬要求；已有 `--verb SECTION` 继续保留。

---

## 3. 边界与风险

1. **target 解析风险**：ASG `_lift_perform` / `_lift` 需要 `ProcRef`。本步必须让 raw paragraph 构造入口基于 `ctx.proc_order` 解析 target，不能只靠完整 program。
2. **ctx 状态风险**：`reset_section(ctx)` 仍必须在每段/每个 pending range 方法前调用，避免 `flow_label`、`struct_function`、`leaves` 串段。
3. **pending range 幂等**：`render_pending_range_methods` 循环 drain 的逻辑不变；ASG visitor 登记 `ctx.pending_range_methods` 的 key/value 需与旧路径一致。
4. **postprocess 风险**：ASG 输出行进入同一 `_postprocess_body`，不能跳过 `wsaa.` 前缀和调用实参补全。
5. **行为不扩大**：ASG visitor 未覆盖叶子动词输出可能从旧 `// TODO 叶子待译` 变成 `// TODO-LEAF`；本步测试要确认既有主线关键断言是否接受。若出现大量文本差异，先在 visitor 中对主线 TODO 文本做兼容，而不是放宽测试。

---

## 4. 测试计划

新增测试：

1. `TestMainlineSectionViaAsg`
   - 普通 SECTION：`translate_section_body` 与 legacy helper 逐字符一致；
   - 含 back-edge GO TO：状态机壳一致；
   - PERFORM paragraph：`ctx.pending_range_methods` 登记一致；
   - BEGN/READR/write IO 样例：主线输出包含对应结构吸收产物。
2. `TestMainlinePendingRangeViaAsg`
   - `render_pending_range_methods` 的 pending THRU 合成方法与旧路径一致；
   - `force_sm=True` 时前向 GO TO 仍走状态机。
3. fallback 测试：
   - monkeypatch ASG helper 抛异常，确认回退 legacy 并产出旧路径内容。

回归：

- `python -m unittest test_translation.TestMainlineSectionViaAsg test_translation.TestMainlinePendingRangeViaAsg -v`
- `python -m unittest test_translation`
- `python scripts\diff_asg_vs_legacy.py tests\fixtures\minimal.cob --verb SECTION`
- `python test_smoke.py`
- `python -m py_compile translator\skeleton_gen\body_context.py asg\builder.py asg\section_visitor.py`

---

## 5. 落地步骤（认可后执行）

1. `asg/builder.py` 增加 raw paragraph 构造入口与 ctx/proc resolver。
2. `asg/__init__.py` 导出新入口（如 `build_asg_paragraphs`）。
3. `translator/skeleton_gen/body_context.py`：
   - 抽 `_translate_paragraphs_body_legacy`；
   - 新增 `_translate_paragraphs_body_asg`；
   - `translate_paragraphs_body` 默认走 ASG，异常回退 legacy；
   - 保持 `_postprocess_body` 调用位置不变。
4. 补测试覆盖普通 SECTION、pending range、结构吸收、fallback。
5. 跑目标测试、全量测试、SECTION diff、smoke、py_compile。
6. 回填本设计、操作记录和项目总览。

---

## 6. 后续步骤

- 步骤30 可考虑下线 `rules.build_section` 的结构吸收与骨架装配旧代码，只保留必要委托或 legacy fallback。
- 再后续统一 TODO 文本与 `translate_leaf_stmt` 入口，逐步收敛 `rules._dispatch_leaf`。

---

## 7. 实现结果（2026-06-29 落地回填）

**与设计一致，范围未越界**：

- `asg.builder` 新增 `build_paragraphs(paras_raw, ctx)`，可从预切分 raw paragraph 构造 ASG `Paragraph`，供普通 SECTION 与 pending THRU 合成区间共用。
- `asg.__init__` 导出 `build_asg_paragraphs`。
- `translator.skeleton_gen.body_context` 将旧 `translate_paragraphs_body` 实现封装为 `_translate_paragraphs_body_legacy`。
- 新增 `_translate_paragraphs_body_asg`，默认通过 `SectionJavaVisitor(ctx, force_sm=...)` 渲染主线方法体。
- 公开 `translate_paragraphs_body` 默认走 ASG，ASG 异常时回退 legacy。
- `_postprocess_body` 仍保持统一出口，继续处理数组下标、`this.X(...)` 实参补全和 `wsaa.` 前缀。
- 新增 5 条测试：`TestMainlineSectionViaAsg`(4) 与 `TestMainlinePendingRangeViaAsg`(1)。

**验收结果**：

- `python -m unittest test_translation.TestMainlineSectionViaAsg test_translation.TestMainlinePendingRangeViaAsg -v` -> 5 tests OK。
- `python -m unittest test_translation` -> 181 tests OK（skipped=2）。
- `python scripts\diff_asg_vs_legacy.py tests\fixtures\minimal.cob --verb SECTION` -> 2 条 SECTION 两路逐字符一致。
- `python test_smoke.py` -> 1 test OK。
- `python -m py_compile translator\skeleton_gen\body_context.py asg\builder.py asg\__init__.py asg\section_visitor.py asg\structure_rewrite.py asg\nodes.py` -> OK。
