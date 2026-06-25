# 步骤14　非过程段纠错（打底）＋ IF / CALL / STRING 语句确定性翻译

状态：§1 🟢已实现（2026-06-25）；§2-4 ⏸已改期（架构演进绞杀之后再做，见 `架构演进-三相分层(预处理-ASG-visitor)初步设计.md` §7）。
（原设计：先纠错打底，同一步依次吸收 IF/CALL/STRING；后因架构演进优先级更高，IF/CALL/STRING 三类规则将迁入相3 visitor，故暂缓，避免按老 token 框架白写。）

> **§1 实现结果（2026-06-25 回填）**：复用 `cobol_columns.is_comment/is_deactivated` 在 proc_start/ws_start/linkage_start
> 定位循环里剔除注释/停用行。真实 ZPOLDWNM 验证：SECTION 数 **135→131**（4 伪段消失）、TODO 总数 **1574→543**
> （层级号假叶子 **901→0**）。**额外修对**：`PROCEDURE DIVISION USING` 参数提取此前读的是被误命中的注释行 →
> USING 入参由 `[]` 纠正为 `['LETCMNT-PARAMS','PMSPNT-PARAMS']`。新增回归测试 `TestProcStartCommentImmune`，全量 44 测试通过。
> 旁注：`find_division`/`_clean_lines` 为改动前既存死代码，本次未触（范围纪律），留作后续清理。

对应代码：`parser/cobol_parser.py`、`translator/rules.py`、`config/specs/skeleton_spec.yaml`、
`config/mappings/io_mappings.yaml`（或新增 `call_mappings.yaml`，见 §3 决策点）、`test_translation.py`。

依赖前序：步骤07/08（SECTION 方法体确定性翻译＋文法驱动骨架）、步骤10/11（IO CALL 调用约定吸收）、
步骤12/13（PERFORM THRU 区间）。本步骤是**叶子/条件层**的继续吸收，不动控制流降级框架。

---

## 0. 背景与范围（基于 ZPOLDWNM 真实渲染的 1574 TODO 分布）

真实程序 `cleaned_ZPOLDWNM.cob` 渲染后残留 **1574 个 TODO**，分布：

| 来源 | 数量 | 性质 | 本步骤动作 |
|---|---|---|---|
| 数据/环境 DIVISION 段被当方法体（`01/03/05…` 层级号行） | ~901 | ⚠️ 缺陷（根因见 §1） | **§1 纠错** |
| `IF…END-IF` 条件无法确定 | ~184 | 真·待译 | **§2** |
| `CALL`（非 IO 子程序，如 NAMADRS） | ~93 | 真·待译 | **§3** |
| `STRING … DELIMITED BY` | ~92 | 真·待译 | **§4** |
| `GO TO` / `COPY` / 其余 | 其余 | 本步骤范围外（控制流/COPY 展开另议） | — |

**范围边界（不做）**：GO TO 控制流（TODO-GOTO，已有状态机降级框架，非本步骤）、COPY 语句展开、
EVALUATE TRUE 复杂条件、INSPECT/SEARCH 等长尾动词。

---

## 1. 子任务 A：proc_start 注释误判纠错（打底，最高优先级）

### 1.1 根因（已实测定位）

`parser/cobol_parser.py` 第 259–265 行用 `upper_lines`（**裸大写、未剔除注释行**）正则
`\bPROCEDURE\s+DIVISION\b` 定位 `proc_start`。ZPOLDWNM 第 10 行是注释：

```
*   The basic procedure division logic is for reading ...
```

该行被命中 → `proc_start=10`（真值应为 2498，对应第 2499 行 `PROCEDURE DIVISION USING ...`）。
后果：`_parse_sections(raw_lines, 10)` 从第 11 行起把 ENVIRONMENT/DATA DIVISION 下的
`CONFIGURATION / INPUT-OUTPUT / FILE / WORKING-STORAGE` 四段全当过程 SECTION，
其中 `WORKING-STORAGE`（935–2764，~1830 行）的数据声明行被整体倾泻成 ~901 个「TODO 叶子待译」。

实测：当前总段 135 → 纠错后真过程段 **131**（误纳 4 段），TODO 预计 1574 → **~670**。

### 1.2 修法（根因修复，单点）

`parser/cobol_parser.py` `parse()` 内定位 `proc_start`（及对称的 `ws_start`/`linkage_start`）的循环：
**判定前先剔除注释/停用行**，复用既有正本 `parser/cobol_columns.py`（步骤06 定列正本，
已有 `is_comment`/`is_deactivated`/列区清洗，COPY 收集处第 296 行已在用 `is_deactivated`）。

- 设计思路：DIVISION/SECTION 关键字的判定本应在**代码区**进行；注释区（第 7 列 `*`）出现的
  `procedure division` 字样是英文散文，不是语法标记。用 `cobol_columns` 把注释行排除，与项目
  「定列正本单一来源」一致，不在 parser 里另写注释判定（复用优先，规则15）。
- 具体：循环里对每行先 `cobol_columns.is_comment(raw) or is_deactivated(raw)` → `continue`；
  或对参与匹配的文本走一次 `cobol_columns` 的代码区提取再正则。**最终落点（用哪个 API、改循环还是改取值）
  在实现期按 `cobol_columns` 现有签名确定，不超出"剔除注释行后再匹配"这一语义。**
- 防御补强（可选，待认可）：`_parse_sections` 内 `_SECTION_RE` 匹配同样跳过注释行
  （`_strip_cobol_line` 已部分清洗，确认是否已覆盖注释；若已覆盖则无需改）。

### 1.3 影响面与回归预期

- 受影响产物：主类骨架渲染——4 个伪方法（`configuration/inputOutput/file/workingStorage`）消失，
  ~901 假 TODO 消失；131 个真过程段方法不变。
- WSAA 数据线（`working_storage` 变量解析走 `ws_start/ws_end`）：`ws_start` 同样曾受注释误判风险，
  本次一并修对 → WSAA 字段解析更稳（需回归比对 WSAA 产物**不应变化或变得更正确**）。
- **风险**：若某些程序确实在 PROCEDURE DIVISION 之前无注释误命中，则 `proc_start` 不变、零回归；
  ZPOLDWNM 是受影响样例。须跑现有 43 单测确认 SECTION 级用例不回归。

---

## 2. 子任务 B：IF 条件语句翻译扩展

### 2.1 现状

`translator/rules.py` `_sk_if`（1128 行）已能在 `_try_condition` 成功时输出 Java `if/else`；
`_try_condition`（218 行）/`_try_comparison`（246 行）兜不住的条件 → 整个 IF 落 `new_leaf`（TODO）。
~184 个 IF TODO ＝ 条件解析失败的那些。抽样可见类型：88 条件名（`IF WSAA-XXX`）、
多值 OR（`= 'PEA' OR 'PEB' OR ...`）、复合 AND/OR、状态码比较（`ITDM-STATUZ NOT = O-K AND NOT = ENDP`）。

### 2.2 扩展点（在 `_try_condition`/`_try_comparison` 内增量，不改 `_sk_if` 框架）

按出现频次排序，逐项吸收（每项独立函数或分支，命中返回 Java，未命中仍 `None` 退 LLM）：

1. **88 条件名** `IF WSAA-FLAG`（无运算符）→ 调对应布尔方法 `wsaa.isWsaaFlag()`（88 已在 WSAA 线
   渲染成布尔方法，步骤04）。需 ctx 能识别 token 是否为 88 名——查现有 `field_type_map`/88 元数据是否够用，
   不够则在 `build_body_ctx` 备料注入 88 名集（**实现期确认数据来源，不臆造**）。
2. **多值 OR** `X = 'A' OR 'B' OR 'C'` → `(x.equals("A") || x.equals("B") || x.equals("C"))`
   （COBOL 省略主语的连写比较，复用 `_split_or` 已有逻辑 428 行）。
3. **复合 AND/OR 链** `cond1 AND cond2`、`NOT = a AND NOT = b` → 按布尔运算符切分递归套用
   `_try_comparison`，全部子句命中才整体命中。
4. **类条件**（如有）`IF X NUMERIC` 等 → 视抽样实际占比决定是否纳入本步骤（低频可留 TODO）。

### 2.3 config 正本

条件运算符/布尔连接符映射若涉及新词，登记到 `config/specs/skeleton_spec.yaml` 既有
`block_grammar`（或其 condition 子节）作正本，py 只读取套用，不在 rules 写死字面量（规范正本先行）。
**实现期确认 skeleton_spec.yaml 是否已有 condition 节，无则新增最小节。**

---

## 3. 子任务 C：通用 CALL 调用约定吸收

### 3.1 现状

`_t_call`（1416 行）只固化 `CALL 'xxxIO' USING xxx-PARAMS`（Repository IO，步骤10/11）；
非 IO 子程序（`NAMADRS`、`DATCON`、`ITDMIO` 之外的工具子程序）→ `matched=False` → TODO（~93）。

### 3.2 设计：配置表驱动的通用子程序映射

- 新增/复用映射：在 `config/mappings/` 下登记**非 IO 子程序 → Java 服务调用**的范式与显式条目。
  **决策点（待认可）**：① 复用 `io_mappings.yaml` 增 `subprograms:` 节，还是 ② 新建
  `call_mappings.yaml` 专表。倾向 ②（职责单一、与 IO 表解耦），但须在 §「已确认的决定」由用户拍板。
- 映射内容：子程序名 → `{java_class, field_name, method, 参数结构体后缀, import}`，
  比照 IO 表的 `resolve_io_info`/`derive_io_info` 范式（复用优先）。`USING` 参数 → 方法实参顺序。
- `_t_call` 在 IO 分支未命中后，再查通用子程序表：命中 → `obj = service.method(params);`（或 void 调用）；
  仍未命中 → `matched=False` 退 LLM（保守，不臆测陌生子程序语义）。

### 3.3 范围控制

仅吸收**映射表已登记**的子程序；未登记的一律留 TODO。首批登记哪些（按 ZPOLDWNM 频次：
NAMADRS 等）由实测 top 列表决定，**不预先臆造业务子程序清单**。

---

## 4. 子任务 D：STRING 语句翻译

### 4.1 现状

`_dispatch_leaf`（1342 行）**没有 STRING 分支** → 所有 `STRING` 落 TODO（~92）。

### 4.2 设计：新增 `_t_string`

COBOL `STRING a DELIMITED BY SIZE b DELIMITED BY SPACE INTO target [ON OVERFLOW …]`
→ Java 字符串拼接到 `target`。

- 语义：各源项按 `DELIMITED BY` 截断后顺序拼接，写入 `INTO` 目标（定长字段 → 右填充/截断按目标 PIC）。
  - `DELIMITED BY SIZE` → 整串。
  - `DELIMITED BY SPACE` / `DELIMITED BY <lit>` → 截到首个分隔符（`.trim()` 近似或 `split` 取首段，
    **实现期确认与现有字符串字段语义一致**）。
- 输出范式：`target = (s1 + s2 + ...);`（源项经 `_operand` 转 Java，字面量/字段统一走既有助手）。
  目标为定长字段时复用 WSAA 字段的赋值/填充约定（步骤12 符号/持久性已立的规则），不另造。
- `ON OVERFLOW`：低频，首版可留 `// TODO ON OVERFLOW` 注释或整句退 LLM（保守），由抽样占比定。
- config 正本：`STRING` 的块构造（分隔符关键字、拼接范式）登记到 `skeleton_spec.yaml`
  `block_grammar`，py 读取，不写死。

### 4.3 接线

`_dispatch_leaf` 增 `if verb == "STRING": return _t_string(toks, ctx)`，与现有动词分支同构。

---

## 5. 改动文件清单（待认可后实现，回填行号）

| 文件 | 改动 | 子任务 |
|---|---|---|
| `parser/cobol_parser.py` | `parse()` 定位 proc_start/ws_start/linkage_start 时剔除注释行（复用 cobol_columns） | A |
| `translator/rules.py` | `_try_condition`/`_try_comparison` 扩展（88名/多值OR/AND链）；`_t_call` 加通用子程序分支；新增 `_t_string` + `_dispatch_leaf` 接线 | B/C/D |
| `config/specs/skeleton_spec.yaml` | condition 节（如需）＋ STRING block_grammar（正本先行） | B/D |
| `config/mappings/call_mappings.yaml`（或 io_mappings 增节，§3 决策） | 非 IO 子程序映射表 | C |
| `config/spec_loader.py` | 若新增 call_mappings → 加访问方法 | C |
| `test_translation.py` | 各子任务新增单测（见 §6） | A/B/C/D |

**拆分提示**：`rules.py` 已 1328 逻辑行，远超单文件阈值。本步骤**只增量、不顺带重构**（避免扩大范围）；
但须在操作记录里记一笔「rules.py 体量告警」，作为后续独立「rules 包化拆分」步骤的输入（不在本步骤做）。

---

## 6. 验收基线与测试

| 项 | 预期 |
|---|---|
| 现有单测 `python -m unittest test_translation` | 43+ 全过（含新增用例），既有 SECTION/THRU 用例不回归 |
| ZPOLDWNM 真实渲染 SECTION 数 | 135 → **131**（4 个数据/环境伪段消失） |
| ZPOLDWNM TODO 总数 | 1574 → **≤~700**（~901 数据噪声消除 + IF/CALL/STRING 各吸收一批） |
| 新增单测 | A：注释行含 "procedure division" 不误判 proc_start；B：88名/多值OR/AND链 IF；C：登记子程序 CALL 固化、未登记退 TODO；D：STRING 多源/DELIMITED BY SIZE/SPACE 拼接 |

---

## 7. 已确认的决定（待补）

- [范围] 步骤14 ＝ 先纠错（§1）打底，同一步依次吸收 IF（§2）/CALL（§3）/STRING（§4）；GO TO/COPY/EVALUATE-TRUE 范围外。✅（用户已确认）
- [§3 决策] 通用 CALL 映射用新表 `call_mappings.yaml` 还是并入 `io_mappings.yaml`？→ **待用户拍板**。
- [§2/§4 长尾] 类条件 / ON OVERFLOW 是否纳入首版？→ 倾向留 TODO，**待用户确认**。
- [不重构] 本步骤不顺带做 rules.py 包化拆分，仅记告警。✅（设计内固化）
