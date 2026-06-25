# 步骤13 · paragraph 级 PERFORM THRU 区间解析设计

状态：🟢已实现（2026-06-09 认可决策 D1=路线b/D2=同段+跨段/D3=保守；2026-06-24 回填 3 处实现级细节；
2026-06-25 用户认可回填细节并落地实现——缺口1 proc_order 四元载荷 / 缺口2 合成方法收集+类级落地 / 缺口3 翻译编排下沉 body_context，
行号已回填 §4，43 项单测通过，真实程序渲染稳定）
对应概要：`../架构索引/项目总览.md`
翻译标准正本：`config/specs/skeleton_spec.yaml`（block_grammar.perform.thru）、`config/mappings/naming_conventions.yaml`
依赖前序：步骤12 §2（SECTION 级 THRU 区间展开，本步骤是其 paragraph 级延伸）、步骤07/08（SECTION 方法体 + 段内 paragraph 内联/状态机降级）

---

## 0. 背景与范围

步骤12 §2 落地了 `PERFORM A THRU B` 的**SECTION 级**展开：A、B 均为已知 SECTION 且 B 在 A 之后时，
按 `section_order` 展开区间内每段调用。其「已知边界」明确留一条 TODO：

> ② 仅当 THRU 两端点均为**已知 SECTION** 才展开；paragraph 级 THRU 端点 → 退化 TODO（P-1③），**未做 paragraph 级区间解析**。

本步骤**只做这一条**：让 `PERFORM A THRU B` 在 A/B 为 **paragraph**（而非 SECTION）时也能正确解析区间、
不丢中间单元，**含跨 SECTION 的 paragraph 区间**（D2 已确认同段+跨段都做）。**不做**：THRU 与区间内 GO TO 的
交互、`PERFORM A THRU B UNTIL/VARYING` 的循环语义细化、C-3（单条 PERFORM paragraph）——这些列入「§5 范围外」，按需另开步骤。

### COBOL THRU 语义（正本依据）
`PERFORM A THRU B` = 按**源码顺序**执行从过程单元 A 到 B（含两端）之间的**全部过程单元**（paragraph 或 section），
执行到 B 末尾后返回调用点。区间以**源码物理顺序**界定，与名字无关。

---

## 1. 现状与根因（为什么 paragraph 端点兜不住）

| 约束 | 现状 | 出处 |
|---|---|---|
| C-1 顺序表只有 SECTION | `Ctx.section_order` 仅 `[SECTION 名]`，无 paragraph，故 paragraph 端点 `order.index(b)` 失败 → 退化 TODO | `rules.py` `_perform_range`、`body_context.py:54` |
| C-2 paragraph 不是方法 | paragraph 在 `build_section` 里**内联**进所属 SECTION 方法体（仅注释 `// paragraph X`），非独立 Java 方法；只有「段内回跳 GO TO」才降级成 `switch(__pc)` 状态机 | `rules.py:1061-1090` |
| C-3 单条 PERFORM paragraph 已隐性破损 | `_proc_call(paragraph)` 盲目产出 `this.pXxx()`，但该方法不存在（C-2），`_postprocess` 的 `known_methods` 路由也只认 SECTION 方法 → 调到不存在的方法 | `rules.py:1159`、`body_context.py:80` |

**核心矛盾**：要把 `PERFORM A THRU B`（A/B 为 paragraph）译成可编译 Java，必须解决两件事——
①**区间解析**（A..B 是哪些单元，需全程序 paragraph 顺序）；②**调用目标落地**（区间得有真实可调用的 Java 目标，
而 paragraph 当前不是方法）。①是用户点名的活儿，②是①绕不开的前置。

---

## 2. 设计方案

### 2.1 数据基座：全程序「过程单元顺序表」 proc_order（解决 C-1）
新增 `Ctx.proc_order: list[ProcUnit]`，`ProcUnit = (name_upper, kind, section_upper, body_lines)`
（**实现细节回填 2026-06-24·缺口1**：原三元 `(name, kind, section)` 不带源体，§2.3 合成方法体「无米下锅」，
故扩为**四元**，第四元 `body_lines` = 该单元的 COBOL 源体行）：
- `kind ∈ {"section", "paragraph"}`；
- 按**源码物理顺序**罗列**所有** SECTION 与其下 paragraph（SECTION 头本身也入表，作为该段第一个单元）；
- `section_upper` = 该单元所属 SECTION（SECTION 自身则为自己），用于 §2.3 的「同段」判定；
- `body_lines: list[str]` = 该过程单元的 COBOL 段体行（`split_paragraphs` 切出的体，不含 PERFORM 标签头），
  供 §2.3 合成区间方法时按序拼接翻译。

构建点：`body_context.build_body_ctx` 已能拿到 `program.sections`，每段再 `split_paragraphs(s.lines)` 即得段内
paragraph 顺序与其体（`split_paragraphs` 已存在，步骤08）。把「SECTION 名 + 其 paragraph 标签 + 各自体」按段序、
段内序拍平即成。`section_order` 保留不动（步骤12 SECTION 级路径继续用它），`proc_order` 是其超集补充。

### 2.2 区间解析：`_perform_range` 升级（解决 ①）
`_perform_range` 现逻辑（步骤12）：查 `THRU` → 取 `a,b` → 在 `section_order` 找区间。升级为**两级查找**：
1. **SECTION 级**（保持不变，零回归）：`a,b` 均在 `section_order` → 按原逻辑展开（步骤12 §2 路径）。
2. **paragraph 级**（新增）：否则在 `proc_order` 找 `a,b`。
   - 两端都找到、`b` 在 `a` 之后（区间可跨 SECTION，D2 确认）→ 按 §2.3 路线 b 合成区间方法、单次调用。
   - `a==b` 或区间仅 1 单元 → 退化单调用。
   - 任一端点找不到、或 `b` 在 `a` 之前、或区间内含无标签裸块/畸形单元（D3 保守）→ 维持步骤12 的 TODO 退化（`pA()` + `// TODO 人工核对`），不臆测。

### 2.3 调用目标落地（解决 ②）—— 路线 b（已确认 D1）
区间内单元若是 SECTION→已有方法可调；若是 paragraph→当前无方法。采**路线 b·合成区间方法**：
为 `A THRU B` 合成一个 Java 方法（命名走 config，见 §2.4），方法体 = 区间内各单元 COBOL 体按 `proc_order`
顺序拼接后过 `build_section` 整体翻译一次；调用点产出单次 `this.aThruB()`（实参由 B1 后处理补齐，见下）。
- **跨段无额外代价**：合成方法挂主类，与 SECTION 共享同一 `(wsaa, using…)` 上下文，区间跨不跨 SECTION 对它无差异——
  只是把 `proc_order` 中 A..B 各单元的体连起来译，故 D2 的「跨段」在路线 b 下与「同段」同一套实现。
- 天然兼容 `UNTIL/VARYING`（循环体即该方法调用）、无重复代码、对现有段内联渲染零侵入。
- C-3（单条 PERFORM paragraph 调到不存在方法）路线 b 不顺带修，单列 §5 TODO。

#### 实现细节回填 2026-06-24·缺口2（合成方法的「收集 + 类级落地」机制）
`_perform_range` 在某 SECTION 体翻译**中途**被调，当场无处发射类级方法。故拆「登记」与「落地」两步：
1. **登记（rules 层）**：`Ctx` 新增**程序级**字段 `pending_range_methods: dict[str, list[str]]`
   （键=合成方法名，值=区间内各单元体按 `proc_order` 序拼接后的 COBOL 行；**不随段重置**，
   `reset_section` 不清它）。`_perform_range` 命中 paragraph 区间时：按 §2.4 config 模板算方法名 →
   把「方法名 → 拼接体」存入 `pending_range_methods`（同名幂等，重复 PERFORM 同区间只合成一次）→
   返回单行 `this.aThruB();`。
2. **补实参（沿用 B1，零新增）**：合成方法名一并加入 `known_methods`，则 `body_context._postprocess_body`
   的现有 B1 路由（`this.X()` → `this.X(wsaa, using…)`，凭 `known_methods` 判定）**自动**把
   `this.aThruB();` 补成 `this.aThruB(wsaa, using…);`——无需 `_perform_range` 感知 `call_args`。
3. **落地（render_skeleton 层）**：`render_skeleton` 在发射完所有 SECTION 方法后，drain
   `ctx.pending_range_methods`，对每个合成方法走 §2.3·缺口3 的翻译流程产出方法体，作为额外类级方法发射。

#### 实现细节回填 2026-06-24·缺口3（合成方法体翻译流程 + 编排分层）
完整段翻译流程（`build_section`→占位 leaves→外层解析 leaves + `_postprocess_body` 加 `wsaa.` 前缀/B1 补实参）
现居 `body_context.py`。若把 `_render_perform_range_method` 放 `rules.py`，会令 `rules` 反向依赖 `body_context`
成环。故**编排下沉 `body_context`**：
- `rules._perform_range` **只做**「解析区间 + 登记 pending + 返回 `this.aThruB();`」，不碰翻译流程，`rules` 不依赖 `body_context`；
- `body_context` 新增 `render_pending_range_methods(ctx, ws_field_names, call_args, known_methods) -> dict[name, method_body]`：
  对 `ctx.pending_range_methods` 每条，复用 `translate_section_body` 同款流程（`reset_section` + `split_paragraphs`
  + `build_section` + leaf 解析 + `_postprocess_body`）把拼接体翻一次，得合成方法体文本；
- `render_skeleton` 调它，按 §2.3·缺口2 第 3 步发射为类级方法。

### 2.4 config 正本同步（skeleton_spec.yaml）
`block_grammar.perform.thru` 现有 `single_unit/cross_section/unresolved` 三态，新增 paragraph 级说明：
- `paragraph_intra_section`：「A、B 为同段 paragraph 且 B 在后 → 按段内单元顺序解析区间，落地形态见 D2」；
- `cross_section_paragraph`：「区间跨 SECTION → 退化 TODO 人工核对（步骤13 §5 范围外）」。
命名（路线 b 选中时）：`naming_conventions.yaml` 新增 `perform_range_method`（如 `{a}Thru{B}` 模板 + 兜底序号）。

---

## 3. 决策点（已确认，见文末「已确认的决定」）

- **D1（区间落地形态）→ 路线 b·合成区间方法**（用户确认）。
- **D2（区间范围）→ 同段 + 跨段都做**（用户确认）；路线 b 下两者同一套实现（§2.3）。
- **D3（中间单元判定严格度）→ 保守**（设计推荐，默认采纳）：区间内全部单元须有明确标签才展开，
  夹无标签裸块/畸形层级 → TODO 退化，不臆测边界。如需放宽请在认可时指出。

---

## 4. 文件与调用关系（实现落点，行号已回填 2026-06-25）

| 文件 | 改动 | 职责 |
|---|---|---|
| `translator/rules.py` | `Ctx` 加 `proc_order`（四元，缺口1，`rules.py:30`）+ `pending_range_methods`（程序级，缺口2，`rules.py:33`）字段；`reset_section` **不清**（该重置在 `body_context.reset_section`，未列这两字段→不清，零改动即满足）；`_perform_range` 升级两级查找（`rules.py:1171`）；新增 `_perform_range_paragraph`（解析区间→登记 pending→返回 `this.aThruB();`，缺口2-3，`rules.py:1202`）；`from config import spec_loader`（`rules.py:18`）调命名正本 | 区间解析 + 登记（**不碰翻译流程**） |
| `config/spec_loader.py` | 新增 `perform_range_method(a_method,b_method)`（缺口/§2.4 命名取值辅助，`spec_loader.py:116`） | 命名正本访问层 |
| `translator/skeleton_gen/body_context.py` | 新增 `_build_proc_order()`（遍历 `program.sections`+`split_paragraphs` 建四元，`body_context.py:38`）并在 `build_body_ctx` 注入（`body_context.py:75`）；`translate_section_body` 末尾 `known_methods ∪ pending 键`（缺口2，`body_context.py:129`）；新增 `render_pending_range_methods()`（缺口3，工作集循环至稳定，`body_context.py:133`） | 数据基座 + 合成方法翻译编排 |
| `translator/skeleton_gen/render_skeleton.py` | 新增 `_range_method()`（合成方法签名+体，`render_skeleton.py:97`）；section 循环后 drain `pending` 调 `render_pending_range_methods` 发射类级方法（缺口2 step3，`render_skeleton.py:126`） | 合成方法类级落地 |
| `config/specs/skeleton_spec.yaml` | `perform.thru` 加 `paragraph_intra_section`/`cross_section_paragraph` 两态说明（正本先行） | 翻译标准 |
| `config/mappings/naming_conventions.yaml` | （路线 b）新增 `perform_range.method_template`（`{a}Thru{B}`） | 命名规范 |
| `test_translation.py` | `TestPerformThru` 扩展 5 项 paragraph 级用例（synthesize/cross-section/idempotent/duplicate-degrade/b-before-a-degrade） | 验证 |

**实现期偏差说明（如实记录，均更保守、未超范围）**：
- 命名取值辅助最终落 `config/spec_loader.py`（命名正本的天然归属），由 `rules._perform_range_paragraph` 调用——比「放 rules」更内聚，rules 仍不含 config 解析逻辑。
- `reset_section` 实际位于 `body_context.py`（非 rules）；其本就不触碰 `proc_order`/`pending_range_methods`，故「程序级、段重置不清」零改动即成立。
- 区间「单单元」(`ib<=ia`，含 C-3 单条 PERFORM paragraph) → 返回 None 交回 TODO 退化（不发射指向不存在方法的裸调用），比 §2.2「退化单调用」更安全；端点重名（count≠1，D3 保守）同样退化。

数据流（回填后）：`body_context.build_body_ctx` 建四元 `proc_order` → 注入 `Ctx` → 段翻译中 `_sk_perform`
→ `_perform_range`（先 SECTION 级，零回归；后 paragraph 级）→ 命中 paragraph 区间则**登记** `pending_range_methods`
+ 返回 `this.aThruB();`（B1 后处理补实参）→ `render_skeleton` 发射完 SECTION 后 → `render_pending_range_methods`
对 pending 各条复用 `translate_section_body` 流程翻译 → 发射为类级合成方法。

---

## 5. 范围外（明确不做，留 TODO）
- THRU 区间内含 GO TO（区间内跳转语义与 THRU 单元边界的交互）。
- `PERFORM A THRU B UNTIL/VARYING` 的循环语义深化（路线 b 下循环调用合成方法即可覆盖基本形，复杂变体仍标 TODO）。
- C-3：单条 `PERFORM <paragraph>` 调到不存在方法（路线 b 不顺带修，单列 TODO 另开步骤）。
- 评审「尚未覆盖的构造」（88 setter、OCCURS DEPENDING ON 等）——与本步无关，另开步骤。

---

## 6. 测试设计（无真实样本，合成 ctx 验证，沿用步骤12 TestPerformThru 路子）
- `test_thru_paragraph_intra_section_expanded`：同段 `pA THRU pC`（中夹 pB）→ 区间三单元都落地，不丢 pB。
- `test_thru_paragraph_single_unit`：`pA THRU pA` → 单调用。
- `test_thru_paragraph_cross_section_expanded`：区间跨 SECTION（D2）→ 合成方法体含跨段各单元译文，不丢。
- `test_thru_paragraph_endpoint_unknown_todo`：端点不在 `proc_order` → TODO 退化。
- `test_thru_paragraph_unlabeled_gap_todo`：区间内夹无标签裸块（D3 保守）→ TODO 退化。
- `test_thru_section_level_unchanged`：步骤12 SECTION 级四用例全绿（零回归）。
- `test_perform_range_method_synthesized`：合成方法名符合 `perform_range_method` 模板、方法体含区间各单元译文、调用点单次调用。

---

## 已确认的决定
- **D1 落地形态 = 路线 b·合成区间方法**（2026-06-09 用户确认）：`A THRU B` → 合成单方法 `aThruB()`，
  体 = 区间各单元译文拼接，调用点单次 `this.aThruB(…)`。不改段内联渲染，blast radius 最小。
- **D2 区间范围 = 同段 + 跨段都做**（2026-06-09 用户确认）：路线 b 下跨段无额外代价，统一按 `proc_order` 连续切片处理。
- **D3 中间单元严格度 = 保守**（设计推荐默认采纳）：区间内全部单元须有明确标签；夹无标签裸块/畸形 → TODO 退化。
- 范围限定：本步只做 THRU 区间解析与落地；C-3（单条 PERFORM paragraph）、区间内 GO TO、UNTIL/VARYING 复杂变体均列 §5 范围外。
