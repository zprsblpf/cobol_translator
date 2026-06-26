# 步骤15 · 单条 PERFORM paragraph 调用落地设计（C-3）

状态：🟢已实现（2026-06-25 TDD 落地，53 单测绿 + 端到端 SMOKE15 验证；见文末「实现回填」）
对应概要：`../架构索引/项目总览.md`
翻译标准正本：`config/specs/skeleton_spec.yaml`（block_grammar.perform）、`config/mappings/naming_conventions.yaml`
依赖前序：步骤13（proc_order 全程序过程单元表 + 路线b 合成区间方法 + pending_range_methods 机制，🟢已实现）、步骤14（合成方法保留标签 + translate_paragraphs_body，🟢已实现）

---

## 0. 背景与范围

步骤13 §1 标出 **C-3**：单条 `PERFORM <paragraph>`（无 THRU）现产出 `this.pXxx();`，但 paragraph 在所属 SECTION 里是
**内联**的、**没有同名 Java 方法**——调到不存在的方法，不可编译。步骤13/14 把它列为范围外。本步骤**只做这一条**：
让单条 `PERFORM <paragraph>` 落到一个真实可调用的目标。

**不做**（仍范围外）：①`PERFORM A THRU B`（步骤13/14 已覆盖）；②`PERFORM` 循环子句 UNTIL/VARYING/TIMES 的复杂变体
（步骤13 §5 另列）；③`PERFORM` 一个全程序都不存在的名字（既非 SECTION 亦非 paragraph）——保守 TODO，不臆造。

### COBOL 语义（正本依据）
`PERFORM X`（X 为 paragraph）= 执行 **paragraph X 自身的体**（从 X 标签到下一 paragraph 边界），到末尾返回调用点。
**不**贯穿后续 paragraph（那是 THRU 的事）。故目标体 = proc_order 中 X 单元的体 `u[3]`。

---

## 1. 现状与根因

| 约束 | 现状 | 出处 |
|---|---|---|
| 无条件产出 this.pXxx() | `_perform_range` 无 THRU 分支直接 `_proc_call(target)` → `this.<section_to_method(target)>();`，**不分 SECTION/paragraph** | `rules.py:1180-1181`、`_proc_call` 1169-1171 |
| paragraph 无方法 | paragraph 在 `build_section` 内联进所属 SECTION 方法体（仅注释 `// paragraph X`），非独立方法 | `rules.py:1070-1073` |
| 路由只认 SECTION | B1 后处理 `this.X()` 补实参仅当 X ∈ known_methods（SECTION 方法 + pending_range_methods）；paragraph 名不在其中 | `body_context.py:_postprocess_body` |

**根因**：调用点假设「过程名 = 方法名」，但 paragraph 不是方法。步骤13 已把**全部 paragraph** 收进 `proc_order`（带体），
步骤13/14 已有「登记 pending → drain 译为类级方法」的成套机制——C-3 可直接复用：**单条 PERFORM paragraph = 单单元区间**，
合成一个「X 自身的方法」即可，**调用点形态 `this.pXxx();` 不必变**（恰好就是 `_proc_call` 已产出的名字）。

---

## 2. 设计方案

### 2.1 单条 PERFORM paragraph → 合成单段方法（复用步骤13/14 机制）
在 `_perform_range` 无 THRU 分支（`_proc_call` 之前）加判定：
- **target 是已知 SECTION**（`target ∈ ctx.known_sections`）→ 维持 `_proc_call`（真实 SECTION 方法已存在，零回归）。
- **target 是 paragraph**（在 `proc_order` 中恰出现一次、kind=paragraph，且不是 SECTION）→ **登记单单元 pending 方法**：
  `ctx.pending_range_methods[section_to_method(target)] = [(target, 该单元体)]`（幂等，重复 PERFORM 同段只合成一次），
  仍返回 `_proc_call(target)`（即 `this.pXxx();`）。
  - 渲染期 `render_pending_range_methods` drain 该 pending → `translate_paragraphs_body` 译出 `void pXxx(wsaa…){ … }` 挂主类；
  - B1 后处理凭 `known_methods | pending_range_methods` 自动把调用点 `this.pXxx();` 补成 `this.pXxx(wsaa, using…);`。
- **兜不住**（target 既非 SECTION 亦不在 proc_order、或 proc_order 中重名、或 `section_to_method(target)` 与某**已存在 SECTION 方法**同名却指向不同单元）→ **保守**：维持 `this.pXxx();` 但前置可见 `// TODO 单条 PERFORM <X>：未解析到过程单元，调用目标可能不存在，需人工核对`，不臆造（D15-2）。

### 2.2 命名（复用 section_to_method，调用点零变化）
合成单段方法名直接取 `section_to_method(target)`——与 `_proc_call` 既产出的调用名**同名**，故调用点 `this.pXxx();` 不动，
只是「补出」一个之前缺失的方法定义。无需新增命名模板（区别于步骤13 的 `perform_range_method`，那是多单元区间才需要的新名）。

### 2.3 区间内 GO TO（单单元情形）
单段方法体若含 `GO TO Y`：Y 是该 paragraph 之外的目标（单单元内无其他标签）→ 落步骤14 的 **E3 区间外**保守分支
（`// TODO-GOTO` / 已知 SECTION 则 call+return），与步骤14 一致，无需新增。`force_sm` 对单单元无意义，传默认 False。

---

## 3. 决策点（待用户认可）
- **D15-1 落地形态** → 复用步骤13/14 pending 机制合成单段方法、调用点 `this.pXxx();` 不变（§2.1）。（设计推荐）
- **D15-2 兜不住时** → 保守：维持 `this.pXxx();` + 前置可见 TODO（不再是静默坏调用），不臆造（§2.1 末）。（设计推荐）
- **D15-3 命名** → 复用 `section_to_method(target)`、调用点零变化（§2.2）。（设计推荐）

---

## 4. 文件与调用关系（实现落点，待认可后回填行号）

| 文件 | 改动 | 职责 |
|---|---|---|
| `translator/rules.py` | `_perform_range` 无 THRU 分支加 paragraph 判定 → 登记单单元 pending（复用 §2.1）；新增小工具 `_perform_single_paragraph()`（或内联） | 单段解析 + 登记 |
| `config/specs/skeleton_spec.yaml` | `block_grammar.perform` 增「单条 PERFORM paragraph → 合成单段方法 / 兜不住保守 TODO」说明 | 翻译标准 |
| `test_translation.py` | 扩 `TestPerformThru` 或新增用例（见 §6） | 验证 |

数据流：`_sk_perform`（无循环、无 children）→ `_perform_range`（无 THRU）→ 判 SECTION/paragraph：paragraph 则登记
`pending_range_methods[pXxx] = [(X, body)]` + 返回 `this.pXxx();` → `render_pending_range_methods` drain → 发射 `void pXxx(){…}`。

---

## 5. 范围外（明确不做，留 TODO）
- `PERFORM A THRU B`（步骤13/14 已覆盖）。
- `PERFORM … UNTIL/VARYING/TIMES` 的复杂循环变体（步骤13 §5）。
- `PERFORM` 全程序不存在的名字（保守 TODO，不臆造）。
- paragraph 体内贯穿语义之外的控制流细化（GO TO 跳出单段按步骤14 E3 保守处理）。

---

## 6. 测试设计（合成 ctx，沿步骤13/14 路子）
- `test_perform_single_paragraph_synthesizes_method`：`PERFORM PARA-X`（X 为 proc_order 中 paragraph）→ 登记 `pending_range_methods["p_parax"]==[("PARA-X", body)]`、调用点 `this.p_parax();`。
- `test_perform_single_section_unchanged`：`PERFORM SOME-SEC`（X 为已知 SECTION）→ 不登记 pending、维持 `this.<sec>();`（零回归）。
- `test_perform_single_paragraph_idempotent`：同 paragraph 多次 PERFORM → 只合成一次。
- `test_perform_single_unknown_conservative`：`PERFORM NOPE`（proc_order 无、非 SECTION）→ 维持 `this.pNope();` + 可见 TODO，不登记。
- `test_perform_single_paragraph_renders_method`：drain 后合成方法体含该 paragraph 译文（端到端到渲染层）。
- 步骤13/14 全用例零回归。

---

## 实现回填（2026-06-25 🟢已实现）

| 落点 | 实际改动 |
|---|---|
| `translator/rules.py` 新增 `_perform_single_paragraph(target, ctx, indent)`（1174-1192） | SECTION→维持 `this.<sec>()`；paragraph（proc_order 恰一次、非 SECTION、合成名不撞 SECTION 方法名）→登记单单元 pending `[(target, body)]`（幂等）+ 返回 `this.pXxx();`；兜不住→`this.pXxx()` + 前置可见 TODO |
| `translator/rules.py` `_perform_range` 无 THRU 分支（1200-1202） | 由 `return [_proc_call(target)]` 改为 `return _perform_single_paragraph(...)` |
| `config/specs/skeleton_spec.yaml` | `block_grammar.perform` 增 `single.section/paragraph/unresolved` 三态 |
| `test_translation.py` | `TestPerformThru` 加 4 测（synthesizes/section_unchanged/unknown_conservative/idempotent）+ `TestThruRangeGoto.test_perform_single_paragraph_renders_method` |

**复用为主、改动极小**：渲染（`render_pending_range_methods`/`translate_paragraphs_body`）、B1 补实参、命名（`section_to_method`）全部沿用步骤13/14，
未新增渲染/命名代码。调用点形态 `this.pXxx();` 不变——只是「补出」之前缺失的方法定义。

**端到端（SMOKE15）**：`PERFORM 2000-CALC`（2000-CALC 为 paragraph）→ 调用点 `this.calc2000(wsaa);` + 新增 `void calc2000(Smoke15Wsaa wsaa){ … wsaa.wsaaN = 7; }`。
步骤15 前该方法不存在（不可编译）。注：该 paragraph 在所属 `work2000()` 段方法里仍内联一份、又作 `calc2000()` 独立一份——路线b 体复制权衡，与步骤13 合成区间方法一致，正确。

---

## 已确认的决定
- **D15-1 落地形态 = 复用步骤13/14 pending 机制合成单段方法、调用点 `this.pXxx();` 不变**（2026-06-25 用户认可）。
- **D15-2 兜不住 = 保守维持 `this.pXxx();` + 前置可见 TODO（消除静默坏调用），不臆造**（2026-06-25 用户认可）。
- **D15-3 命名 = 复用 `section_to_method(target)`、调用点零变化**（2026-06-25 用户认可）。
