# 步骤07 · 主线 SECTION 方法体确定性翻译设计

状态：🟢 已实现（2026-06-03，决策 A/B 见 §0；实现回填见 §7）
对应概要：`../架构索引/项目总览.md`
依赖前序：步骤05（主类骨架，方法体留空）、步骤06（解析器列对齐）

## 0. 已确认的决定

- **范围**：主线方法体确定性翻译（接 rules 引擎填全量 SECTION 方法体），无 LLM，兜不住的叶子落 `// TODO 叶子待译`。
- **复用方式**：主线 `skeleton_gen` 直接调 `segmenter` + `rules`，不另抽公共渲染层。
- **决策 A（字段前缀/后处理）= 方案 B**：在 `body_context.py` 写瘦后处理，只做「数组下标 + `wsaa.` 前缀」，不引入 graph 的多模块路由。
- **决策 B（PERFORM 实参）= B1**：瘦后处理把指向 SECTION 方法的 `this.X()` 补成 `this.X(wsaa, <using…>)`，保留步骤05 的 wsaa 参数传递模型。

---

## 1. 目标（已锁定范围）

把**已存在**的确定性规则引擎（`translator/rules.py`）接进**主线骨架渲染**
（`translator/skeleton_gen/`），让每个 SECTION 方法体从步骤05 的
「空体 + `// TODO 方法体待译`」变成**确定性翻译出的 Java 语句**。

已确认的决定（本次下发）：
- **范围**：主线方法体确定性翻译（接 rules 引擎填 SECTION 方法体），全量所有 SECTION。
- **复用方式**：主线 `skeleton_gen` **直接调** `segmenter` + `rules`，不另抽公共渲染层。
- **无 LLM**：规则兜不住的叶子 → `// TODO 叶子待译: <原COBOL>`（保留原文，不臆测）。

> 与 graph（AI 辅助层）的区别：graph 对兜不住的叶子调 LLM；主线一律落 TODO。两者共用同一套
> `segmenter`+`rules` 确定性逻辑，主线是确定性纯净版。

---

## 2. 现状与接入点

`translator/skeleton_gen/render_skeleton.py`：
- `_section_method(model, using, s)`（§现 L82-91）当前产出：方法签名 + `// COBOL SECTION` 注释 +
  可选 `// TODO-GOTO` + `// TODO 方法体待译` + 若干 `// PERFORM x → method()` 注释。
- **接入点 = 用「rules 翻译出的方法体」替换这段空体**。

可直接复用的成熟件（graph 已用、确定性、无 LLM）：
| 件 | 位置 | 作用 |
|---|---|---|
| `segment(lines)` / `split_paragraphs(lines)` | `translator/segmenter.py` | COBOL 段体行 → 语句树 / 先按 paragraph 切 |
| `build_section(paras, ctx)` | `translator/rules.py:661` | 控制流骨架 + 叶子占位 `/*__LEAF_n__*/`，登记 `ctx.leaves` |
| `translate_leaf(stmt, ctx)` | `translator/rules.py:879` | 单叶子 → Java，返回 `(lines, matched)` |
| `Ctx` | `translator/rules.py:20` | 规则引擎上下文（字段类型 / 段名映射 / 结构体注册表 / IO 映射） |
| `build_struct_registry(state)` | `translator/naming.py:27` | COPY→结构体命名注册表 |
| `resolve(...)` | parser.variable_resolver | WS/LINKAGE 变量 → `field_type_map` + Java 字段名（复用，见 §3.1） |

数据来源已确认齐备：`CobolProgram.sections[i].lines` 即段体行；`working_storage`/`linkage_vars`
可经 `variable_resolver` 出 `field_type_map`；`copy_refs`/`linkage_using` 喂 `build_struct_registry`。

---

## 3. 详细设计

### 3.1 备料：把 `CobolProgram` 收敛成 ctx 所需的料

新增**瘦备料模块** `translator/skeleton_gen/body_context.py`（单一职责：装 ctx，约 60 行）。
理由：`render_skeleton.py` 已近 100 行（规范十七条），备料逻辑独立成包内一文件，渲染层只调用。

`build_body_ctx(program) -> rules.Ctx`：
1. `field_type_map, java_field_names = variable_resolver.resolve(program)` —— **复用**解析器现有产物，
   不重建（与 graph 的 `field_type_map` 同源，保证两路一致）。
2. `known_sections = {s.name.upper() for s in program.sections}`。
3. 构造 `build_struct_registry` 所需的等价 state dict：
   `{"copy_refs": program.copy_refs, "linkage_using": program.linkage_using,
     "sections_meta": [{"name":s.name, "lines":s.lines, "calls":s.calls} for s in program.sections]}`，
   调 `build_struct_registry(state)` 得 `reg`。
4. 载 `config/io_mappings.yaml` 合并 `io_programs(+io_programs2)/date_programs/system_programs/io_default_pattern`
   （与 `context.py` L49-50 / `nodes.py` L264-272 同逻辑）。
5. 照 `nodes.py` L275-289 装 `rules.Ctx(field_type_map=…, section_to_method=_section_to_method,
   known_sections=…, **reg 拆字段, **io_maps 拆字段)`，返回。

> ctx 程序级算**一次**，各 SECTION 复用（与 graph 一致）。但 `ctx.leaves`/`_counter`/`flow_*` 是
> **段级状态**：每段渲染前必须重置（见 3.2），否则叶子编号跨段串号。

### 3.2 逐段填体：改写 `_section_method`

新签名 `_section_method(model, using, s, ctx, field_names)`，体内：
1. **重置段级 ctx 状态**：`ctx.leaves=[]; ctx._counter=[0]; ctx.flow_label=None; ctx.flow_paragraphs=set()`
   （或在 body_context 提供 `reset_section(ctx)` helper，避免散落）。
2. 切分 + 骨架：
   ```python
   paras = [(lbl, segment(body)) for lbl, body in split_paragraphs(s.lines源行)]
   skel  = build_section(paras, ctx)          # 含 /*__LEAF_n__*/ 占位
   body  = "\n".join(skel)
   ```
   异常兜底（同 graph L298-302）：整段退化为单条 `// TODO 段翻译失败` + 原文注释（**不调 LLM**）。
3. 填叶子（**纯规则，无 LLM**）：
   ```python
   for lid, leaf in ctx.leaves:
       lines, matched = translate_leaf(leaf, ctx)
       fill = "\n".join(lines) if matched else f"// TODO 叶子待译: {leaf.raw or ' '.join(leaf.tokens)}"
       body = body.replace(f"/*__LEAF_{lid}__*/", fill)
   body = re.sub(r"/\*__LEAF_\d+__\*/", "// TODO: 未翻译叶子", body)   # 防御
   ```
4. **后处理**（字段前缀等）：见 §3.3 决策。
5. 组装方法：保留 `void {method}({sig})` 签名 + `// COBOL SECTION …` 头注释 + 可选 `// TODO-GOTO`，
   方法体 = 后处理后的 `body`，缩进到方法内层。**移除**原 `// TODO 方法体待译` 与 `// PERFORM …` 尾注释
   （PERFORM 已由 `build_section` 译为内联调用）。

`render_skeleton(program)`：在循环前 `ctx = build_body_ctx(program)`；循环内
`lines += _section_method(model, using, s, ctx, field_names)`。其余（header/services/entry/去重）不变。

### 3.3 ⚠️ 待认可决策 A：字段前缀与后处理

`rules` 输出**裸字段名**，由后处理统一加前缀。graph 的 `_postprocess_java_body`（postprocess.py:26）
做三遍：①数组下标 `name(i)→name[i-1]`；②PERFORM 跨模块路由 `this.m()→facade.perform()`；
③已知字段加 **`st.`** 前缀。

主线是步骤05 的**单类 + `wsaa` 容器**模型（非 graph 的多模块 State）：
- WORKING-STORAGE 字段应加 **`wsaa.`** 前缀（不是 `st.`）；
- PERFORM 目标都在**同一个主类内** → 应是 `this.method(...)`，**不需要**多模块 facade 路由。

**方案 B（推荐）**：在 `body_context.py` 写一个**瘦后处理** `postprocess_body(body, field_names)`，
只做 ①数组下标 + ③`wsaa.` 前缀两遍，**不引入**多模块路由。理由：主线单类，路由概念不适用；
瘦函数职责清晰、与 graph 的多模块后处理解耦，不污染 `_postprocess_java_body` 的语义。
（数组下标修正逻辑约 10 行，可从 postprocess 抽公共小函数共享，避免复制。）

方案 A（备选）：参数化 `_postprocess_java_body` 的前缀（`st.`→传入）并加开关关闭 PERFORM 路由后复用。
缺点：为单类场景给多模块函数加分支，语义变杂。

### 3.4 ⚠️ 待认可决策 B：PERFORM 调用实参

`build_section` 把 `PERFORM X` 译为 `this.method()`（**无参**，graph 模型靠实例 State）。
但步骤05 主线方法签名是 `void method(ZpoldwnmWsaa wsaa, <using…>)`（**靠参数传 wsaa**）。
直接复用会产生 `this.method()`（缺 `wsaa` 实参）→ **不可编译**。三条出路：

- **B1（推荐）**：在 §3.3 的瘦后处理里加一遍：把指向已知 SECTION 方法的 `this.X()` 调用补成
  `this.X(wsaa, <using 实参>)`。改动集中、保留步骤05 的 wsaa 参数传递模型。
- B2：取消步骤05 的 wsaa 参数传递，改 `wsaa` 为主类实例字段（`this.wsaa`），方法变无参——
  与 graph 的实例 State 模型趋同。改动面大、推翻步骤05 §8 已认可决定，本步不建议。
- B3：先接受无参调用 + 标 `// TODO 调用实参待补`。最省但产物不可编译，不建议。

> 决策 A、B 是本设计仅有的两个开放点，其余按上文固化。

---

## 4. 文件改动清单与调用关系

| 文件 | 动作 | 职责 |
|---|---|---|
| `translator/skeleton_gen/body_context.py` | **新增**（~60 行） | `build_body_ctx(program)→Ctx`、`reset_section(ctx)`、瘦后处理 `postprocess_body`（含决策A/B落地） |
| `translator/skeleton_gen/render_skeleton.py` | 改 | `render_skeleton` 建 ctx；`_section_method` 改为填体（接 segmenter+rules）；去尾注释 |
| `translator/postprocess.py` | 可能微改 | 若决策A/B需共享数组下标逻辑，抽一个公共小函数（不改既有行为） |

调用关系（新增/变化）：
```
render_skeleton(program)
  → body_context.build_body_ctx(program)
        → variable_resolver.resolve(program)        # 复用：field_type_map
        → naming.build_struct_registry(state)       # 复用：结构体注册表
        → 载 config/io_mappings.yaml                # 同 context.py
        → rules.Ctx(...)
  └─ 每段 _section_method(..., ctx)
        → reset_section(ctx)
        → segmenter.split_paragraphs / segment
        → rules.build_section(paras, ctx)           # 骨架 + 叶子占位
        → rules.translate_leaf(leaf, ctx)           # 纯规则；未命中→TODO
        → body_context.postprocess_body(body, field_names)   # 数组下标 + wsaa.前缀 + this.X(wsaa,…)
```
依赖方向保持 `skeleton_gen → translator(rules/segmenter/naming/postprocess) + parser.variable_resolver`，单向，无环。

---

## 5. 验证计划（实现后逐项核对）

1. **导入冒烟**：`body_context` / `render_skeleton` 及各被调方导入无误。
2. **全量渲染**：对 `ZPOLDWNM.cob` 重生成主类骨架，统计：方法数不变（步骤06 基线 134）、
   `// TODO 方法体待译` 归零、新出现的 `// TODO 叶子待译` 计数（量化规则覆盖率）。
3. **花括号配平** + **无非法 Java 标识符**（沿用步骤05/06 校验脚本）。
4. **可编译性抽样**：抽 3-5 个代表性 SECTION，肉眼核对：字段 `wsaa.` 前缀正确、`this.X(wsaa,…)`
   实参齐、结构体 `obj.getXxx()`、数组下标 `-1`、控制流（IF/PERFORM/EVALUATE）结构正确。
5. **与 graph 一致性抽样**：同一 SECTION，主线规则命中的叶子与 graph 规则命中的叶子 Java 应一致
   （仅前缀 `wsaa.` vs `st.` 不同），验证「同源确定性」。
6. **WSAA 回归**：WS 容器类 `ZpoldwnmWsaa.java` 不受影响（diff 为空）。

---

## 6. 不做（出范围）

- 不调 LLM、不接 RAG（那是 graph AI 辅助层的职责）。
- 不改 graph 侧任何逻辑。
- 不新增/改写 `rules.py` 的翻译规则本身（仅复用；规则增强是后续独立步骤）。
- 不动步骤05 的 WS 容器/服务依赖/入口 `execute` 结构（仅入口控制流 TODO 留作后续，除非决策B2，但B2不建议）。

---

## 7. 实现回填（2026-06-03）

落地产物（与 §4 一致）：
- 新增 `translator/skeleton_gen/body_context.py`：`build_body_ctx`(配方同 pipeline，WS+LINKAGE 入 field_type_map、
  仅 WS 入 wsaa 前缀集)、`reset_section`、`translate_section_body`、瘦后处理 `_postprocess_body`（决策A方案B + B1）。
- 改 `translator/skeleton_gen/program_model.py`：`SectionModel` 加 `body_lines`，`build_model` 回填 `s.lines`。
- 改 `translator/skeleton_gen/render_skeleton.py`：`render_skeleton` 建 ctx 一次；`_section_method` 接 `translate_section_body`，
  去 `// TODO 方法体待译` 与 PERFORM 尾注释（PERFORM 已译为内联 `this.X(wsaa,…)`）；移除已无用的 `_perform_method` 导入。
- 微改 `translator/postprocess.py`：抽模块级 `fix_array_subscripts`；`_prefix_fields_outside_strings` 加 `prefix` 参（默认 `st.`，graph 行为不变）。

验证（§5 全绿，对 `/home/zp/Documents/cob/ZPOLDWNM.cob`）：方法数 134（=133 段+execute）；
`// TODO 方法体待译` 归零；新增 `// TODO 叶子待译` 712 条（规则覆盖盲区，无 LLM）；花括号配平 1019/1019；
无残留 LEAF 占位、无数字开头非法标识符；`wsaa.` 前缀 2309 处、`this.X(wsaa,…)` 214 处、结构体访问器 2933 处；
`test_translation.py` 24 项通过（含 postprocess 回归）；graph `_postprocess_java_body` 仍输出 `st.`。

已知局限（既有 rules 规则盲区，非本步引入、graph 同样存在）：少数未进 `field_type_map` 的名被当字面量
渲染到赋值左侧（如 `"WSAA-A65086" = "";`），不可编译。规则增强留后续独立步骤（§6 已划出范围）。
