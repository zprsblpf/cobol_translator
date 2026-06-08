# 步骤12 · 翻译标准修正（符号 / PERFORM THRU / WS 持久性 / 命名碰撞）设计

状态：🟢 已实现（2026-06-09 用户「认可+继续」采纳全部推荐项，4 条全部落地 config+实现+测试，全量 38 测试通过、真程序端到端验证。S-1 实现期修正见 §6 回填）
对应概要：`../架构索引/项目总览.md`
翻译标准正本：`../翻译标准/变量定义.md`（数值/符号语义）、`config/specs/wsaa_translation_spec.yaml`、`config/specs/skeleton_spec.yaml`、`config/mappings/naming_conventions.yaml`
依赖前序：步骤03/04（WSAA 块翻译，符号在此落地）、步骤07/08（SECTION 方法体 + 文法骨架，PERFORM/控制流在此落地）

---

## 0. 背景与范围

翻译标准评审发现 4 处**与 COBOL 真实语义不符或不一致**的点。本步骤**只做这 4 条修正的设计**，
每条独立、可分别认可分别落地。**不做**：评审里归为"尚未覆盖的构造"（88 setter、88 区间值、
OCCURS DEPENDING ON、GO TO DEPENDING ON、MOVE 类型相关规则）——那些是**新增覆盖**，另开步骤。

修正清单与影响面：

| # | 修正 | 正本/config | 实现落点 | 风险级别 |
|---|---|---|---|---|
| ① | 有符号数值**存储串**保符号 | `wsaa_translation_spec.yaml` assumptions；`变量定义.md` §数值 | `translator/wsaa/storage.py:30`、`render_view.py` | 高（静默数据腐败） |
| ② | `PERFORM A THRU B` 跨段不丢中间段 | `skeleton_spec.yaml` block_grammar.perform | `translator/rules.py`(build_section)、segmenter | 中（漏翻段） |
| ③ | WS 容器跨调用持久性 | `wsaa_translation_spec.yaml` working_storage.java_principle | `skeleton_gen/` | 中（需逐程序确认的假设） |
| ④ | 字段名 camelCase 扁平化碰撞 | `naming_conventions.yaml` | `translator/naming.py`、`parser/variable_resolver.py` | 中（编译冲突/静默覆盖） |

---

## 1. 修正① · 有符号数值存储串保符号（最高优先）

### 1.1 现状与根因
- 数值**字段本身**已带符号：`S9(15)V9(2)` → `BigDecimal`（天然有符号），正确，无需改。
- 但 `config/specs/wsaa_translation_spec.yaml` 的 `assumptions.signed_display_abs` 规定：
  "有符号 DISPLAY 数值存储串取绝对值零填充，不建模负号 overpunch（语义为日期/金额，恒非负）"。
- 实现 `translator/wsaa/storage.py:30` 据此对**存储串序列化**取 `.abs()`：
  `_toDigits(BigDecimal v, int n, int scale)` → `v.movePointRight(scale).abs().toBigInteger()...`。
- **波及路径**：仅当带符号数值经 **REDEFINES / 组定宽切片** 走 `_toDigits` 序列化、或字段值经
  存储串 round-trip 回来时，末位 overpunch 符号位被 `.abs()` 抹掉 → 负的退费/冲正金额静默变正。
- 正本 `变量定义.md:160` **已记载** 符号 overpunch（`C`=正/`D`=负/`F`=无符号），即语义层本就承认负值；
  只是实现图省事丢了。本修正是**让实现对齐已记载的语义**，非改语义。

### 1.2 方案（"默认保符号 + 字段级豁免白名单"）
- 原则：把 `signed_display_abs` 从**全局真理**降级为**字段级可选豁免**。默认保符号，只对能证明恒非负的字段豁免。
- `wsaa_translation_spec.yaml`：删除/重写 `assumptions.signed_display_abs`，改为
  `signed_storage_string`：默认按 overpunch 建模末位符号半字节；新增可选 `abs_whitelist`（字段名列表）声明豁免字段。
- `translator/wsaa/storage.py` `_toDigits`：
  - 默认分支：保留符号——按 COBOL DISPLAY overpunch 规则，对**末位数字字符**叠加 zone（正/无符号→原数字，负→对应 overpunch 字符；最朴素可行方案见决策 S-1）。
  - 豁免分支（字段在白名单）：维持现 `.abs()` 行为。
- `render_view.py`：parse（存储串→数值）侧对称还原符号，保证 round-trip 双向一致。

### 1.3 待确认决策点
- **S-1（负号在存储串里怎么表示）**：① 真 overpunch 字符（`}JKLMNOPQR` 等 EBCDIC 风格，最忠实但 Java 侧切片/比较易踩坑）；
  ② 前置符号字符 `-`（直观但改变定宽宽度，破坏切片偏移）；③ 单独 sign 标志 + abs 数字串（保宽度、保符号，切片偏移不变，**推荐**）。
  → 取决于"存储串是否真被当作 overpunch 字节切片消费"。若切片只取数字段、符号仅末位，方案③副作用最小。
- **S-2（豁免白名单初始内容）**：哪些字段确认恒非负（如纯日期 `9(8)` 已是无符号 `9`，本就不在 `S9` 范围；真正需要豁免的是被证明非负的 `S9` 金额/计数）。建议初始**空白名单**（全部保符号），按实测反例再加。

---

## 2. 修正② · `PERFORM A THRU B` 跨段不丢中间段

### 2.1 现状与根因
- `config/specs/skeleton_spec.yaml` block_grammar.perform 的 out-of-line sample：
  `PERFORM 2000-INIT THRU 2000-EXIT → p2000Init();`——塌成**一次方法调用**。
- `segmentation_spec.yaml` 把 `THRU/THROUGH` 列入 `perform_keywords`（头部关键字），渲染只取**首过程名**，
  `THRU B` 实际被忽略。
- COBOL 语义：`PERFORM A THRU B` = 顺序执行从段 A 到段 B 之间**所有段**。
  仅当 A..B 之间无中间 paragraph（B 是 A 的 EXIT 哨兵）时，塌成 `pA()` 才等价；
  **跨多段时丢掉中间段** → 漏翻。

### 2.2 方案
- `skeleton_spec.yaml` block_grammar.perform：在 `meaning`/`java_skeleton` 显式区分两态——
  `THRU 范围 == 单段（B 即 A 的 EXIT 段）` → 单调用 `pA();`（现状保留）；
  `THRU 范围跨多段` → 生成顺序调用包装（见决策 P-1）。
- 实现侧（`translator/rules.py` build_section / 段序解析）：用**段序号区间**判定 A..B 之间有几个段，
  跨段时按决策渲染。

### 2.3 待确认决策点
- **P-1（跨段怎么渲染）**：① 内联顺序调 `pA(); pMid1(); ...; pB();`（直白，但调用点膨胀）；
  ② 生成包装方法 `pA_thru_B(){ pA(); pMid1(); ...; pB(); }` 调用点 `pA_thru_B();`（**推荐**，贴 COBOL "一个可执行单元"语义，复用性好）；
  ③ 无法确定区间内段序（段不连续/有跳转）→ 挂 TODO 人工核对。
- **P-2（区间判定数据源）**：段序来自拆解 manifest 顺序还是 cobol_parser 段表？需确认二者顺序一致。

---

## 3. 修正③ · WS 容器跨调用持久性（假设显式化）

### 3.1 现状与根因
- `wsaa_translation_spec.yaml` working_storage.java_principle：每次调用程序 `new` 一个容器实例、线程封闭。
  线程安全这点正确。
- 但 COBOL WORKING-STORAGE 在程序**被多次 CALL 之间保留值**（非 `IS INITIAL`/递归时类似 static）。
  若原程序依赖"首次调用初始化标志、后续复用"，"每次 new" 会改语义。
- 多数翻成无状态 service 无碍，但这是**需逐程序确认的假设**，当前被当默认真理写死。

### 3.2 方案
- 不改默认（无状态 new-per-call 仍是合理默认），但把它从"原则"降级为**显式标注的假设**：
  - `wsaa_translation_spec.yaml`：在 `assumptions` 新增一条 `ws_no_cross_call_persistence`，
    文本说明"假设本程序不依赖 WS 跨 CALL 持久；若依赖（首调初始化等），需改为容器复用/持久化"。
  - 产物注释：生成的容器类头部就地标注该假设（便于人工复核）。
- 提供识别线索（非自动改写）：扫描是否存在"仅在某标志为初值时初始化"的惯用式作为人工复核提示。

### 3.3 待确认决策点
- **W-1**：是否要做"依赖跨调用持久性"的**自动探测**并挂 TODO，还是仅写假设注释、留人工判断？（倾向后者，成本低）

---

## 4. 修正④ · 字段名 camelCase 扁平化碰撞

### 4.1 现状与根因
- 组子项全平铺进 `ZpoldwnmWsaa`（见 working_storage：每个 01 → 字段，组子项亦平铺）。
- COBOL 允许不同组下**同名字段**，靠 `OF/IN` 限定区分。两个 `WSAA-X` 在不同父组下都 → `wsaaX`
  → **Java 编译冲突或后者静默覆盖前者**。大程序高发。
- `naming_conventions.yaml` 当前无碰撞处理规则；`parser/variable_resolver.py` / `translator/naming.py` 直接去前缀转小驼峰。

### 4.2 方案
- `naming_conventions.yaml`：新增 `collision_policy` 节——声明碰撞消歧策略（父组名前缀/后缀消歧）。
- 实现侧（`parser/variable_resolver.py` 字段名生成 + `translator/naming.py`）：
  建字段名时做**全局碰撞检测**，冲突时按策略用父组名消歧（如 `wsaaX` 冲突 → `groupAWsaaX` / `wsaaX_groupA`）。
- 引用点（读/写访问器）同步用消歧后名，保证一致。

### 4.3 待确认决策点
- **N-1（消歧命名形态）**：① 父组名作前缀 `parentWsaaX`；② 父组名作后缀 `wsaaXInParent`；③ 数字序号兜底 `wsaaX2`（信息量最低，不推荐）。倾向①，最可读。
- **N-2（消歧触发范围）**：仅冲突字段消歧（最小改动，**推荐**），还是同组一律带组前缀（统一但啰嗦）？

---

## 5. 落地顺序建议
①（数据正确性，最高）→ ②（漏翻）→ ④（编译冲突）→ ③（仅注释，最轻）。
每条认可后再改对应 config + 实现 + 补测试，逐条回填本文件状态。

---

## 6. 实现回填（2026-06-09，🟢已实现）

### S-1 实现期修正（重要）
设计阶段 S-1 推荐「③ 独立 sign 标志 + abs 数字串」。**读 `storage.py` 后确认：存储串是单个定宽 Java
String、靠 `substring(o,o+w)` 切片消费（`storage.py:104`），无处安放旁路 sign 标志 → ③ 不可实现**。
改为 **① overpunch，但仅对负值生效**：正/无符号值保持纯数字串（与历史一致，**零回归**），仅负值末位
数字叠加 overpunch（`0-9 ⇄ }JKLMNOPQR`）。这是定宽串模型里唯一干净的保符号落法，且只改负值（今天本就被
腐败的路径）→ 严格变好。已向用户说明并默认采纳（正数零回归故先落安全）。

### 各条落地清单

| # | config 改动 | 实现改动 | 测试 |
|---|---|---|---|
| ① | `wsaa_translation_spec.yaml` assumptions `signed_display_abs`→`signed_display_overpunch` | `storage.py` `_toDigits`/`_deOverpunch`/`_fromDigits` + `num_from_digits`(int/long 经 `_deOverpunch`)；`render_view.py`/storage docstring 注释 | `TestSignedOverpunch`×3（负值 round-trip、正值零回归、helper 断言） |
| ② | `skeleton_spec.yaml` block_grammar.perform 新增 `thru` 模板（single_unit/cross_section/unresolved）+ 改正旧错误样例 | `rules.py` Ctx 加有序 `section_order`、新增 `_perform_range()`（跟随上述模板）展开 THRU 区间、`_sk_perform` 改调它；`body_context.py` 填 `section_order` | `TestPerformThru`×4（跨段展开/单段/未知端点 TODO/无 THRU） |
| ④ | `naming_conventions.yaml` 新增 `collision_policy` | `render_class.py` 新增 `_disambiguate()`、碰撞分支改名保留+TODO（取代「重复名跳过」静默丢）、透传 `parent_jn`；`render_field.py` 加 `name_override` | `TestNameCollision`×2（消歧规则、改名不丢） |
| ③ | `wsaa_translation_spec.yaml` working_storage 加 `cross_call_persistence` 假设 | `render_class.py` 容器类头注释就地标注假设（W-1=不自动探测） | 端到端产物含注释（line 9） |

### 验证
- 全量 `python -m unittest test_translation`：38 通过 / 2 skip（LLM 离线），新增 9 用例。
- 真程序 `ZPOLDWNM`：`scripts/translate_wsaa.py` 端到端无异常；产物 overpunch helper 正确产出（`_toDigits`/`_deOverpunch`/`_OVP`），
  签名金额 `wsaaAmount*`(S9V92) 走保符号路径；本程序无命名碰撞（无误报）；③ 假设注释已就位。

### 已知边界（未做，待后续）
- ② 仅当 THRU 两端点均为**已知 SECTION** 才展开；paragraph 级 THRU 端点 → 退化 TODO（P-1③），未做 paragraph 级区间解析。
- ④ 仅消歧**声明**；若撞名二者确为不同字段，**引用处**的 OF/IN 限定解析未做（标 TODO 留人工核对）。
- ① 不建模正号 overpunch（`{ABC…`）；本翻译自产自消，正值用纯数字串自洽，无需处理外来正 overpunch。
