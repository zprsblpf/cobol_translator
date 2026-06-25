# 步骤14 · THRU 区间内 GO TO 交互设计

状态：🟢已实现（2026-06-25 TDD 落地，48 单测绿 + 端到端 SMOKE14 验证；见文末「实现回填」）
对应概要：`../架构索引/项目总览.md`
翻译标准正本：`config/specs/skeleton_spec.yaml`（block_grammar.perform.thru / 段内控制流）、`config/grammar/*`（back_edge_state_machine 开关）
依赖前序：步骤13（paragraph 级 THRU 区间解析 + 路线b 合成区间方法，🟢已实现）、步骤08（段内 paragraph 切分 + 回跳 GO TO → `__pc` 状态机降级）

---

## 0. 背景与范围

步骤13 用「路线b·合成区间方法」落地了 `PERFORM A THRU B`（A/B 为 paragraph）：把区间内各单元 COBOL 体
拼接成一个 Java 方法译一次、调用点单次 `this.aThruB();`。但它在 §5 明确把「**THRU 区间内含 GO TO**」
列为范围外。本步骤**只做这一条**：让合成区间方法体内的 GO TO 语义正确，不再误退/误标。

**不做**（仍列范围外，另开步骤）：①非 THRU 区间的普通段内 GO TO（步骤08 已覆盖，不动）；
②`ALTER` 改写 GO TO；③`GO TO … DEPENDING ON`（计算跳转）；④跨 SECTION 的任意 GO TO 全图可达性分析。

### COBOL 语义（正本依据）
`PERFORM A THRU B` 执行期间，区间内的 GO TO 有三类落点：
- **区间内**（目标 paragraph ∈ [A..B]）：在被执行区间内跳转——前向跳过中间单元，或**回跳形成循环**。控制仍在区间内，跳到 B 末尾后才返回调用点。
- **区间的退出点**（目标 = B 的 EXIT 段 / 区间约定出口）：提前结束本次 PERFORM，返回调用点。
- **区间外**（目标 paragraph/section ∉ [A..B]）：控制离开被执行区间——COBOL 中这是公认的危险写法，行为依赖后续物理落点，语义模糊。

---

## 1. 现状与根因（为什么区间内 GO TO 现在是坏的）

根因是**合成区间方法在拼接单元体时丢掉了 paragraph 标签**，导致区间内 paragraph 边界消失、状态机无从路由 GO TO。
静态代码路径追踪（探查留痕）：

| 环节 | 事实 | 出处 |
|---|---|---|
| split 丢标签 | `split_paragraphs` 检测到标签行后 `continue`，标签行**不进 body**，仅作返回元组首元 | `segmenter.py:198`（`if label is not None: … continue`） |
| 单元体无标签 | `_build_proc_order` 每个 paragraph 单元 `u[3]` = 该 paragraph **不含标签行**的体 | `body_context.py:48-54` |
| 合成丢标签 | `_perform_range_paragraph` 合成 `merged += u[3]`，区间各单元标签**全丢** | `rules.py:1224-1227` |
| 重切失结构 | 合成体经 `translate_section_body` 再 `split_paragraphs(merged)`，无标签 → 整体成**一个无标签 paragraph**，`build_section` 看不到区间内边界，`ctx.flow_paragraphs` 空 | `body_context.py:116` |
| GO TO 落末路 | `_sk_control` 中 `ctx.flow_label` 为 None、目标不在 `flow_paragraphs` → 区间内 `GO TO X`：X 结尾 EXIT→`return;`（误退整个合成方法）；否则→`// TODO-GOTO + return;` | `rules.py:1294-1302` |

**后果**：合成区间方法体内的回跳循环（常见：BEGN/NEXTR 取数循环、重试循环）被彻底打断，前向跳转/区间出口也只能误退或挂 TODO。
这与步骤13 「不丢中间单元」的命门相悖——单元体是在，但**控制流被改写错了**。

> 注：步骤08 的段内 `__pc` 状态机（`build_section` 1076-1098）本身是好的、能处理回跳；问题**只**在合成路径把它该吃的标签结构喂没了。故本步骤主体是「把标签结构还给 build_section」，而非新造控制流引擎。

---

## 2. 设计方案

### 2.1 核心：合成区间方法保留 paragraph 标签结构（解决根因）
把 `pending_range_methods` 的值从「拼接后的无标签行 `list[str]`」改为「**带标签的单元序列** `list[(label, body_lines)]`」，
让区间各 paragraph 的标签随体一起传到翻译期，`build_section` 即可照常切分、识别回跳、构建跨区间的 `__pc` 状态机。

- `_perform_range_paragraph`（rules.py）：登记时存 `ctx.pending_range_methods[mname] = [(u[0], u[3]) for u in rng]`
  （`u[0]`=单元名即标签，SECTION 头单元标签为段名；`u[3]`=单元体）。不再 `merged += u[3]` 丢标签。
- 翻译期不再走「序列化成行 → 再 `split_paragraphs`」的有损往返，改为**直接喂已切好的 `(label, body)`**：
  新增 `translate_paragraphs_body(paras_raw, ctx, …)`（body_context），等价于 `translate_section_body` 但跳过
  `split_paragraphs`，直接 `paras = [(lbl, segment(b)) for lbl,b in paras_raw]` → `build_section`。
  `translate_section_body` 可重构为「`split_paragraphs` 后委托 `translate_paragraphs_body`」，零回归、消重复。
- `render_pending_range_methods`（body_context）：drain 时对每条 `paras_raw` 调 `translate_paragraphs_body`。工作集循环（嵌套 THRU）与幂等不变。

**效果**：区间内 `GO TO 某paragraph` 落到 `build_section` 的 `flow_paragraphs`（= 区间各单元标签集），
回跳 → 状态机 `__pc = "X"; continue FLOW;`（循环语义恢复）；单元间 fall-through 由状态机 `__pc=下一单元` 接续（区间顺序执行语义保住）。**复用步骤08 既有状态机，新增代码极小。**

### 2.2 GO TO 落点分类策略（区间方法翻译期）
合成区间方法译时 `ctx.flow_paragraphs` = 区间各单元标签集，`_sk_control` GO TO 据此分流：

| 落点 | 判定 | 译法 | 决策 |
|---|---|---|---|
| E1 区间内 | target ∈ 区间标签集 | 状态机 `__pc="target"; continue FLOW;`（回跳/前向均精确，复用 build_section） | 推荐采纳 |
| E2 区间出口 | target 结尾 EXIT 且 = B 出口段，或 GOBACK/STOP | `return;`（= 返回 PERFORM 调用点） | 推荐采纳 |
| E3 区间外 | target ∉ 区间标签集（他段 paragraph / SECTION） | **保守**（D3 一脉）：`// TODO-GOTO: 跳出区间，需人工核对`；target 若是已知 SECTION 保留 `call+return`（步骤08 既有行为），否则 `TODO+return`，不臆测跳出后的物理落点 | 推荐采纳 |

### 2.3 待决子项：前向 GO TO 是否强制状态机（E4）
`build_section` 现仅在**存在回跳**（back-edge）且正本开关 `back_edge_state_machine()` 开时才建状态机；
**仅前向 GO TO、无回跳**时走扁平拼接、`flow_label=None`，此时区间内前向 `GO TO X` 仍落 E3 末路（TODO/误退）。

- **方案 a（精确，推荐）**：合成区间方法体内**只要含指向区间内标签的 GO TO（前向或回跳）即强制状态机**。
  改动局部：`build_section` 的 `has_back_edge` 判定扩成 `has_intra_goto`（目标在 `label_index` 即触发），
  或仅在区间方法路径上传一个「强制状态机」标志。blast radius：影响普通 SECTION 的前向 GO TO 渲染（原扁平 → 状态机），需回归确认输出无害变化。
- **方案 b（保守，最小）**：本步只精确处理「回跳循环」（E1 的回跳子集，价值最高），前向 GO TO 维持 E3 保守 TODO，留后续步骤。改动最小、零回归。

> 设计推荐 **a**：本步主题就是 GO TO 交互，前向跳过中间单元若仍误退/挂 TODO 则命门只补了一半；状态机对前向跳转同样天然正确。但 a 触碰 `build_section` 通用路径，需用户在认可时拍板是否接受该回归面。

---

## 3. 决策点（待用户认可）
- **D14-1 标签保留载体** → `pending_range_methods` 值改 `list[(label, body)]` + 新增 `translate_paragraphs_body`（§2.1）。（设计推荐）
- **D14-2 落点分类 E1/E2/E3** → 区间内状态机 / 区间出口 return / 区间外保守 TODO（§2.2）。（设计推荐）
- **D14-3 前向 GO TO 强制状态机？** → 方案 a（精确，触碰 build_section 通用路径）vs 方案 b（最小，前向留 TODO）。**请认可时择一。**
- **D14-4 保守边界**：区间内夹无标签裸块/区间外 GO TO 一律 TODO 退化，不臆测（沿用步骤13 D3）。（设计推荐）

---

## 4. 文件与调用关系（实现落点，待认可后回填行号）

| 文件 | 改动 | 职责 |
|---|---|---|
| `translator/rules.py` | `_perform_range_paragraph` 登记改存 `[(label,body)]`（不再 merge 丢标签）；（若 D14-3=a）`build_section` 回跳判定扩为「区间内 GO TO 即状态机」 | 区间登记 + 控制流降级 |
| `translator/skeleton_gen/body_context.py` | 新增 `translate_paragraphs_body`（跳过 split 直喂已切 paras）；`translate_section_body` 重构为其薄封装；`render_pending_range_methods` 改调新函数 | 合成体翻译（保结构） |
| `config/specs/skeleton_spec.yaml` | `perform.thru` 增「区间内 GO TO」落点说明（E1/E2/E3）；正本先行 | 翻译标准 |
| `test_translation.py` | 扩 `TestPerformThruParagraph` / 新增 `TestThruRangeGoto`（见 §6） | 验证 |

数据流：`_perform_range_paragraph` 登记带标签单元序列 → `render_pending_range_methods` drain → `translate_paragraphs_body`
→ `build_section`（识别区间内回跳 → `__pc` 状态机）→ `_sk_control` 按 E1/E2/E3 分流 GO TO。

---

## 5. 范围外（明确不做，留 TODO）
- 非 THRU 区间的普通段内 GO TO（步骤08 已覆盖，本步不动）。
- `ALTER` 改写 GO TO 目标、`GO TO … DEPENDING ON`（计算跳转）。
- 区间外 GO TO 跳出后的真实物理落点重建（E3 一律保守 TODO，不做全图可达性分析）。
- C-3 单条 PERFORM paragraph 调到不存在方法（步骤13 §5 列项，另开步骤）。

---

## 6. 测试设计（合成 ctx + 渲染双层，沿步骤13 路子）
- `test_thru_goto_back_edge_loop`：区间内回跳 `GO TO 前序paragraph` → 合成方法体出现 `__pc=…; continue FLOW;` 状态机，循环不被打断（命门）。
- `test_thru_goto_to_exit_returns`：区间内 `GO TO B-EXIT` → `return;`（提前退出 PERFORM）。
- `test_thru_goto_out_of_range_todo`：区间内 `GO TO 区间外段` → 保守 `// TODO-GOTO`，不臆测（D14-4）。
- `test_thru_goto_forward_intra`：区间内前向 `GO TO 后序paragraph`（无回跳）→ 按 D14-3 结论：方案 a 出状态机精确跳转 / 方案 b 出保守 TODO（用例随拍板定断言）。
- `test_thru_no_goto_unchanged`：区间无 GO TO → 合成体与步骤13 一致（零回归）。
- `test_perform_thru_section_level_unchanged` + 步骤13 全用例：全绿（零回归）。

---

## 实现回填（2026-06-25 🟢已实现）

| 落点 | 实际改动 |
|---|---|
| `translator/rules.py` `_perform_range_paragraph`（1223-1226） | 登记改存带标签单元序列 `[(u[0], u[3]) for u in rng]`（不再 merge 丢标签） |
| `translator/rules.py` `build_section`（1040-1064） | 加形参 `force_sm: bool=False`；回跳判定 `has_back_edge`→`has_jump`，`force_sm` 下 `j is not None`（任一指向内部标签的 GO TO 即状态机），默认仅 `j<=i`（回跳） |
| `translator/skeleton_gen/body_context.py` | 新增 `translate_paragraphs_body(paras_raw,…,force_sm)`（跳过 split 直喂带标签 paras，共用翻译核）；`translate_section_body` 重构为 `translate_paragraphs_body(split_paragraphs(...))` 薄封装；`render_pending_range_methods` 改调 `translate_paragraphs_body(force_sm=True)` |
| `config/specs/skeleton_spec.yaml` | `perform.thru` 增 `goto_intra_range/goto_range_exit/goto_out_of_range` 三态 + 回跳循环 sample |
| `test_translation.py` | 新增 `TestThruRangeGoto`（back_edge_loop/forward_intra/out_of_range/no_goto 4 测）+ `TestPerformThru.test_thru_paragraph_registers_labeled_units`；同步两条 step-13 旧断言到带标签契约 |

**校正（与 §2.3 方案 a 描述的微调，记录留痕）**：设计 §2.3 方案 a 原拟「扩 `build_section` 的 `has_back_edge` 通用判定」，
明列会波及普通 SECTION 的前向 GO TO 渲染。实现时改用**作用域标志 `force_sm`**：该「前向 GO TO 亦建状态机」的精确行为
**仅施加于合成区间方法**（`render_pending_range_methods` 传 `force_sm=True`），普通 SECTION 走默认 `False`、渲染零变化。
如此既达成 D14-3=a 认可的「区间内前向 GO TO 精确跳转」，又把回归面收敛到零（更稳、符合 §17 最小爆炸半径）。
GO TO 落点分类 E1/E2/E3 未新增独立分支——**复用** `_sk_control`（1283-1302）既有逻辑：标签保留 + `force_sm` 后
`ctx.flow_paragraphs` 自动含区间标签，E1 走状态机、E2 EXIT/GOBACK→return、E3 区间外→既有 TODO-GOTO 分支，零新增代码。

**端到端（SMOKE14）**：`PERFORM 2000-PA THRU 2000-PC`，区间内 `2000-PB` 含 `IF WSAA-N<3 GO TO 2000-PA`（回跳）。
产出合成方法 `pa2000ThruPc2000` 体含 `switch(__pc)` + `case "2000-PB"` 内 `if (wsaa.wsaaN<3){ __pc="2000-PA"; continue FLOW; }`——
回跳循环精确还原（步骤14 前此处退化为 `// TODO-GOTO + return;`，循环报废）。

---

## 已确认的决定
- **D14-1 标签保留载体 = `pending_range_methods` 值改 `list[(label, body)]` + 新增 `translate_paragraphs_body`**（2026-06-25 用户认可）：合成区间方法保留 paragraph 标签结构，复用步骤08 `build_section` 状态机。
- **D14-2 落点分类 = E1 区间内状态机 / E2 区间出口 return / E3 区间外保守 TODO**（2026-06-25 用户认可）。
- **D14-3 前向 GO TO = 方案 a·精确（区间内 GO TO 即建状态机）**（2026-06-25 用户认可设计推荐）：实现时隔离为最后一步（扩 `build_section` 回跳判定为「区间内 GO TO 即状态机」），a/b 分歧仅此一处，前序步骤 a/b 通用。
- **D14-4 保守边界**：区间内夹无标签裸块 / 区间外 GO TO 一律 TODO 退化，不臆测（沿步骤13 D3）（2026-06-25 用户认可）。
