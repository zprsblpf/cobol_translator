# 步骤16 · PERFORM 循环复杂变体设计（TEST AFTER / VARYING…AFTER）

状态：🟢已实现（2026-06-25 TDD 落地，59 单测绿 + 端到端 SMOKE16 验证；见文末「实现回填」）
对应概要：`../架构索引/项目总览.md`
翻译标准正本：`config/specs/skeleton_spec.yaml`（block_grammar.perform）
依赖前序：步骤13/14/15（PERFORM THRU / GO TO / 单条 paragraph 已落地）；本步只动 `_sk_perform` 的**循环子句**翻译，与过程调用解析正交

---

## 0. 背景与范围

步骤13 §5 把「`PERFORM … UNTIL/VARYING` 复杂变体」列为范围外。`_sk_perform` 现已覆盖**基本形**：
`UNTIL cond → while(!(cond))`、`VARYING v FROM a BY b UNTIL cond → for(...)`、`TIMES → for`。本步骤补**两个真语义缺陷**：

1. **WITH TEST AFTER**：COBOL `TEST AFTER` = 先执行循环体一次再判断（do-while）；现码无视该子句、一律 test-before（`while/for` 前判），**语义错**。
2. **VARYING … AFTER …**：多维循环；现码只取首个 VARYING 的 `v/FROM/BY/UNTIL`（`hu.index("UNTIL")` 取首个 UNTIL），**AFTER 内层维度被吞、内层循环丢失**。

**不做**（仍范围外）：`PERFORM … TIMES` 已覆盖不动；条件/操作数仍兜不住者维持现有「落 LLM 叶子」兜底；`PERFORM` 过程解析（步骤13/14/15 已覆盖）不动。

### COBOL 语义（正本依据）
- `WITH TEST BEFORE`（默认）：进入循环先判 UNTIL，真则不执行。`WITH TEST AFTER`：先执行一次体，再判 UNTIL → do-while。
- `VARYING i … UNTIL ci AFTER j … UNTIL cj [AFTER k …]`：i 为最外层、每个 AFTER 是下一更内层，逐层嵌套 for。

---

## 1. 现状与根因

| 缺陷 | 现状 | 出处 |
|---|---|---|
| TEST AFTER 被无视 | `_sk_perform` 仅按 `VARYING/UNTIL/TIMES` 分支发 test-before，`WITH`/`TEST`/`AFTER` 仅作 target 排除关键字，从不据其改 do-while | `rules.py:1260, 1267-1290` |
| VARYING AFTER 被吞 | VARYING 分支只取首个 `UNTIL`，`header[hu.index("UNTIL")+1:]` 把 `AFTER j … UNTIL cj` 一并当条件喂 `_try_condition`（多半失败→落 LLM，或误译单层） | `rules.py:1267-1279` |

**根因**：循环子句解析是「单子句、单测试位置」的硬编码，未把 VARYING/AFTER 视作**可重复的子句序列**，也未读 TEST 位置。
两者都在 `_sk_perform` 同一处，且该函数已偏长——本步顺带按 §17 抽出循环子句解析为独立小工具。

---

## 2. 设计方案

### 2.1 抽出循环子句解析（§17 瘦身 + 可复用）
新增 `_perform_loop(header, hu, ctx, indent) -> tuple[list[str], list[str]] | None`：解析循环子句，返回 `(loop_open_lines, loop_close_lines)`；
无循环子句返回 `([], [])`；遇兜不住（条件/操作数 None）返回 `None`（调用方落 LLM 叶子，维持现有兜底）。
`_sk_perform` 改为调它取 open/close、再包裹 body（body 取 `st.children` 或 `_perform_range`，逻辑不变）。

### 2.2 TEST AFTER → do-while（D16-1）
- 检测：`TEST` 紧跟 `AFTER`（与 VARYING 的 `AFTER` 区分——后者前邻 UNTIL 条件）。记 `test_after = True`。
- **UNTIL（无 VARYING）+ TEST AFTER** → `do { … } while (!(cond));`：`open=["do {"]`，`close=["} while (!(cond));"]`。
- **VARYING + TEST AFTER**（罕见、与多维叠加语义复杂）→ **保守**：返回 `None` 落 LLM 叶子 + 后续可加 `// TODO` 提示，不臆造（D16-3 保守边界）。
- TEST BEFORE / 无 TEST 子句 → 现有 test-before（while/for），零回归。

### 2.3 VARYING … AFTER … → 嵌套 for（D16-2）
- 把 VARYING 起始到 header 末尾切成**子句序列**：每子句 `<var> FROM <a> BY <b> UNTIL <cond>`，`<cond>` 自 UNTIL 后延伸到**下一个 AFTER 或 header 末**。
  首子句以 `VARYING` 引导，其余以 `AFTER` 引导。
- 逐子句生成一层 `for (v=a; !(cond); v=v+b) {`，按序**嵌套**（首子句最外、末子句最内）；`close` 为对应数量的 `}`（逆序）。
- 任一子句 `cond`/操作数兜不住 → 整条返回 `None`（all-or-nothing，落 LLM，不出半个循环）。
- 单层 VARYING（无 AFTER）= 子句序列长度 1，与现有 `for(...)` 输出一致（零回归）。

### 2.4 config 正本同步
`block_grammar.perform` 增循环复杂变体说明：`test_after`（do-while）、`varying_after`（嵌套 for）、保守兜底（VARYING+TEST AFTER / 兜不住 → LLM 叶子 + TODO）。

---

## 3. 决策点（待用户认可）
- **D16-1 TEST AFTER** → 仅 `UNTIL`（无 VARYING）形支持 do-while；`VARYING+TEST AFTER` 保守落 LLM。（设计推荐：覆盖常见形，复杂叠加不臆造）
- **D16-2 VARYING AFTER** → 支持**任意层**嵌套（子句序列驱动，自然覆盖 2 维及以上）。（设计推荐）
- **D16-3 保守边界** → 任一子句条件/操作数兜不住 → 整条 PERFORM 落 LLM 叶子（all-or-nothing），不出半个/误译循环。（设计推荐，沿历史兜底）

---

## 4. 文件与调用关系（实现落点，待认可后回填行号）

| 文件 | 改动 | 职责 |
|---|---|---|
| `translator/rules.py` | 新增 `_perform_loop`（循环子句解析→open/close，含 TEST AFTER / VARYING AFTER / 保守 None）；`_sk_perform` 改调之、瘦身 | 循环子句翻译 |
| `config/specs/skeleton_spec.yaml` | `block_grammar.perform` 增 `test_after`/`varying_after`/保守兜底说明 | 翻译标准 |
| `test_translation.py` | 新增 `TestPerformLoop`（见 §6） | 验证 |

数据流：`_sk_perform` → `_perform_loop`（解析 TEST 位置 + VARYING/AFTER 子句序列 → open/close 或 None）→ 包裹 body。

---

## 5. 范围外（明确不做，留 TODO）
- `PERFORM … TIMES`（已覆盖，不动）。
- `VARYING + TEST AFTER` 叠加（保守落 LLM）。
- 条件/操作数本身兜不住的翻译能力提升（属 `_try_condition`/`_operand` 范畴，另议）。
- `PERFORM` 过程解析（步骤13/14/15 已覆盖）。

---

## 6. 测试设计（合成 ctx，沿历史路子）
- `test_until_test_after_do_while`：`PERFORM … WITH TEST AFTER UNTIL cond`（含 body）→ `do { … } while (!(cond));`。
- `test_until_test_before_unchanged`：`PERFORM … UNTIL cond` / 显式 `TEST BEFORE` → `while (!(cond))`（零回归）。
- `test_varying_after_nested`：`VARYING i … UNTIL ci AFTER j … UNTIL cj` → 外 `for(i…)` 内 `for(j…)` 双层嵌套、body 在最内。
- `test_varying_single_unchanged`：单层 `VARYING v …` → 单 `for(...)`（零回归）。
- `test_varying_after_unparsable_falls_to_llm`：某层条件兜不住 → 整条落 LLM 叶子（不出半个循环）。
- `test_varying_test_after_conservative`：`VARYING…WITH TEST AFTER` → 保守落 LLM（D16-1）。

---

## 实现回填（2026-06-25 🟢已实现）

| 落点 | 实际改动 |
|---|---|
| `translator/rules.py` 新增 `_has_test_after(hu)` | TEST 紧跟 AFTER 检测（与 VARYING 的 AFTER 区分） |
| `translator/rules.py` 新增 `_parse_varying_clauses(header, hu, ctx)` | VARYING/AFTER 切子句序列 `[(v,a,b,cond),…]`，任一兜不住→None |
| `translator/rules.py` 新增 `_perform_loop(header, hu, ctx, indent)` | 循环子句→`(open_lines, close_lines)`：TEST AFTER do-while / VARYING AFTER 嵌套 for / UNTIL·TIMES 基本形 / 兜不住 None |
| `translator/rules.py` `_sk_perform` 重写 | 改调 `_perform_loop`（§17 瘦身）：`None`→落 LLM 叶子；`inner_indent = indent + len(open_lines)`（每层 open=一层嵌套）；`open + body + close` |
| `config/specs/skeleton_spec.yaml` | `block_grammar.perform` 增 `loop.test_before/test_after/varying_after/conservative` |
| `test_translation.py` | 新增 `TestPerformLoop`（6 测：test_after/test_before/varying_after_nested/varying_single/unparsable→LLM/varying_test_after_conservative） |

**端到端（SMOKE16）**：
- `PERFORM WITH TEST AFTER UNTIL WSAA-N > 3 … END-PERFORM` → `do { wsaa.wsaaN += 1; } while (!(wsaa.wsaaN > 3));`（do-while）。
- `PERFORM VARYING WSAA-I … UNTIL … AFTER WSAA-J … UNTIL … END-PERFORM` → `for(wsaaI…){ for(wsaaJ…){ … } }`（双层嵌套）。
步骤16 前：TEST AFTER 错发 test-before `while`、VARYING AFTER 丢内层 j 循环。

---

## 已确认的决定
- **D16-1 TEST AFTER = 仅 `UNTIL`（无 VARYING）形支持 do-while；`VARYING+TEST AFTER` 保守落 LLM**（2026-06-25 用户认可）。
- **D16-2 VARYING AFTER = 子句序列驱动的任意层嵌套 for**（2026-06-25 用户认可）。
- **D16-3 保守边界 = 任一子句条件/操作数兜不住 → 整条 PERFORM 落 LLM 叶子（all-or-nothing）**（2026-06-25 用户认可）。
