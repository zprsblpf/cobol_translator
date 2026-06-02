# 步骤04 · WSAA 块翻译遗留项（REDEFINES / INDICATOR 88）确定性补全设计

状态：🟢 已实现（2026-06-03）｜认可于 2026-06-02
对应上游：`步骤03-WSAA块翻译设计.md`（§5 已知限制 / 输出内 27 处 `// TODO`）
概要索引：见 `../架构索引/项目总览.md`
类型清单（脚本扫描）：`scripts/scan_ws_types.py`（64 种 PIC 签名 / 22 处 REDEFINES，保证不遗漏）
类型样例目录：`../../config/wsaa_type_catalog.yaml`
决策知识库：`../../knowledge/wsaa_translation_decisions.md`（各情况怎么判、为什么）

---

## 0. 续接入口（/clear 后从这里开始）

方案已认可，下一步**直接实现**，无需再设计。按序读 + 改：

1. 读本文件 §3–§6（算法/改动点）+ `knowledge/wsaa_translation_decisions.md`（D8–D15、假设 A1/A2）。
2. 改代码（§5 表）：`translator/wsaa/render_view.py`（主）、`render_condition.py`、`render_class.py`。
3. 跑 `python scripts/translate_wsaa.py --program ZPOLDWNM --in /home/zp/Documents/cob/ZPOLDWNM/拆解/ZPOLDWNMWSAA.cob --out /home/zp/Documents/cob/ZPOLDWNM/拆解/ZpoldwnmWsaa.java`
4. 自检（§7）：`grep -c TODO` 期望 27→约 12–13（仅剩 D13 数组上下文×4 + D14 畸形层级×6 + 个别）；抽样核对双向同步。
5. 回填 §8 实现结果 + 写 `docs/操作记录/步骤04-…操作记录.md`（含 Token 分析）。

---

## 1. 背景与目标

步骤03 产物 `…/ZPOLDWNM/拆解/ZpoldwnmWsaa.java` 含 **27 处 `// TODO`**，对照源
`ZPOLDWNMWSAA.cob` 归为 6 类。本步骤把其中**算法清晰、能保证双向同步**的类别做确定性补全，
其余如实保留为「人工核对」TODO（不臆测）。**纯确定性、不调大模型。**

## 2. 已确认的决定（固化，不再问）

1. 本轮补全范围：**A 字符/数值子项 over 数值**、**B 数值 over 字符**、**C 字符数组 over 字符**、
   **D INDICATOR 88**，外加 **WSAA-CVCP-AMOUNT-D（目标被停用/不在块内）**。
2. **目标被 `!!!!!!` 停用或不在块内**：拆解已丢弃目标定义，则 REDEFINES 别名是该存储的**唯一存活定义**，
   按其自身 PIC **当普通字段/组渲染**（去掉 REDEFINES 视图语义），不再报「可能在 copybook」TODO。
   （`WSAA-CVCP-AMOUNT-D PIC S9(15)V9(2)` → 普通 `BigDecimal` 字段。）
3. **有符号 DISPLAY 数值**（`S9(n)`，如 `WSAA-RES-CRRCD S9(08)` 日期、`WSAA-RCDYEAR S9(04)`）：
   存储串取**绝对值**零填充数字串；负号 overpunch **不建模**（这些字段语义为日期/金额，恒非负）。
   此假设写进产物注释，如实标注。
4. **保留为 TODO（本轮不做）**：
   - E 数组上下文内 REDEFINES（`WSXX-/WS01-/WS02-PCESTRM-R` 等，在 `OCCURS` 元素内、编辑型显示别名）；
   - F 畸形层级（注释掉组头导致的孤儿子项，源 295–327，结构歧义）；
   - COMP-3 打包十进制 backing（打包字节非干净数字串）。
   这些把 TODO 文案改写为**明确的人工核对原因**（数组上下文 / 畸形层级 / 打包十进制），不强行猜测。

## 3. 核心抽象：定宽存储串（fixed-width storage string）

所有视图统一建立在「一个节点的定宽存储串」之上（COBOL 共享存储的本质）：

| 节点 | 读表达式（→ 定宽串） | 写语句（← 定宽串 v） |
|---|---|---|
| 字符标量 `X(w)` | `_pad(name, w)` | `name = v;` |
| 数值标量 `9..`/`S9..V9..`（非编辑、非 COMP-3） | `_toDigits(<name 转 BigDecimal>, w, scale)` | `name = <按类型 _fromDigits/parse(v)>;` |
| 组（子项均为上述标量，无嵌套组/OCCURS） | 子项读表达式按偏移 `+` 拼接（FILLER→`_pad("",w)`） | 按偏移 `substring` 切片，逐子项写回（FILLER 跳过） |

- `scale` = PIC 中 V 之后的位数；`w` = `node.byte_len`（步骤03 已算，`9(15)V99`=17、`S9(08)`=8）。
- 数值标量「转 BigDecimal」：`int/long` → `BigDecimal.valueOf(name)`；`BigDecimal` → 直接 `name`。
- 写回按 backing 类型：`int`→`Integer.parseInt`、`long`→`Long.parseLong`、`BigDecimal`→`_fromDigits(v,scale)`。
- **不支持就退化 TODO**：含 OCCURS、编辑型 PIC、COMP-3、嵌套组 → 该节点/子项标 TODO。

### 新增 Java 辅助方法（随视图按需输出，类似现有 `_pad`）

```java
/** 数值 → 定宽数字串：取绝对值，scale 位作低位小数，左补 0 / 高位截断到 n。 */
private static String _toDigits(BigDecimal v, int n, int scale) {
    if (v == null) v = BigDecimal.ZERO;
    String s = v.movePointRight(scale).abs().toBigInteger().toString();
    if (s.length() > n) return s.substring(s.length() - n);
    StringBuilder b = new StringBuilder();
    while (b.length() < n - s.length()) b.append('0');
    return b.append(s).toString();
}
/** 定宽数字串 → BigDecimal（scale 位小数）；空串按 0。 */
private static BigDecimal _fromDigits(String s, int scale) {
    s = (s == null ? "" : s.trim());
    if (s.isEmpty()) s = "0";
    return new BigDecimal(new java.math.BigInteger(s)).movePointLeft(scale);
}
```

## 4. 各类别补全方案（改哪些函数）

### A. 字符/数值子项 over 数值 backing（≈8 处：AMOUNT1/2/3/5/6、AGE、TERM、PREMTRM、INVCAMT、RES-CRRCD）

- 现状：`_string_accessor` 对非字符 target 返回 `None` → 退化 TODO。
- 改造 `render_view._string_accessor`：扩展为「**目标存储串访问器**」，对**数值标量 target** 也能给出
  `(读表达式, 写模板{v}, 总宽 W)`（用 `_toDigits`/`_fromDigits`/`parseInt`）。
- `render_redefines` 的 `slice_view` 扩展为按**子项类型**生成：
  - 字符子项 `X(w)` → `String getX()`/`setX(String)`（现有逻辑，切片 `[off,off+w]`）；
  - 数值子项（如 RES-CRRCD 的 `WSAA-RCDYEAR S9(04)`）→ `int/BigDecimal getX()` =
    `parse(target存储串.substring(off,off+w))`；`setX(类型 v)` = 把 v 的定宽数字串拼回 target 存储串再写回。
- 例：`WSAA-AMOUNT1-UNIT-CHAR X(17) over WSAA-AMOUNT1-UNIT 9(15)V99`
  → `getWsaaAmount1UnitChar()` 返回 `_toDigits(wsaaAmount1Unit,17,2)`；`set...` 解析回 `wsaaAmount1Unit`。

### B. 数值 over 字符组（2 处：WSAA-STRING-R / WSAA-STRING-R-2 `PIC 9(03)`）

- target `WSAA-STRING` 是组（`SEX X(1)` + `ISSUE-AGE 9(02)`，含数值子项 → 现有 `can_group_view`
  不接纳，故无视图）。用 §3 的「组存储串」生成 target 读/写表达式（混合字符+数值子项）。
- REDEFINES 节点自身为数值标量 `9(03)` → 生成 `int getWsaaStringR()` = `parse(组存储串)`；
  `setWsaaStringR(int v)` = `组存储串写回(_toDigits(v,3,0))`。

### C. 字符数组 over 字符（1 处：WSAA-P `X(2) OCCURS 5` over WSAA-PVALUE `X(10)`）

- 现状：`render_redefines` 见子项带 OCCURS 即 `// TODO 子项含组/OCCURS`。
- 改造：子项为**纯标量 + 一维 OCCURS n** 且 `n*w == 剩余宽度`时，生成带下标访问器：
  `String getP(int i)` = `target存储串.substring((i-1)*2,(i-1)*2+2)`；
  `void setP(int i, String v)` = 切片写回。（下标用 i-1，与类头约定一致。）

### D. INDICATOR 88（2 处：IND-ON / IND-OFF over `INDIC-TABLE OCCURS 99 PIC 1`）

- `INDIC-TABLE` → `boolean[] indicTable`。88 的 `VALUE B'1'`=元素 true、`B'0'`=false。
- 改造 `render_condition`：holder 为数组（`occurs>0` 或处数组上下文）且 condition `is_boolean` 时，
  生成**带下标布尔访问器**：
  - `public boolean indOn(int i){ return indicTable[i-1]; }`（B'1'）
  - `public boolean indOff(int i){ return !indicTable[i-1]; }`（B'0'）
  - 需把「是否数组」传入 `render_conditions`（由 `render_class._handle` 据 dims/occurs 传 `indexed` 标志）。

### 目标停用/不在块内（WSAA-CVCP-AMOUNT-D 等）

- `render_redefines`：`name_index` 找不到 target 时，改为调用新 `_as_primary(node)`——
  按 node 自身 PIC 走 `render_field`（叶子）或组平铺，**输出到 fields 而非 views**，附一行轻量注释
  `// 原 REDEFINES 目标已停用，按主定义渲染`，不再是 TODO。

## 5. 模块 / 文件改动（职责不变，仅增强；单文件仍 <100 逻辑行）

| 文件 | 改动 | 说明 |
|---|---|---|
| `translator/wsaa/render_view.py` | 改 `_string_accessor`→支持数值/组存储串；改 `render_redefines` 的 `slice_view`（字符+数值+数组子项）、target 缺失走 `_as_primary`；新增 `NUM_HELPER`（`_toDigits/_fromDigits`） | 主改动；若超 100 行则把存储串构造拆到 `render_view` 内部小函数或新 `storage.py` |
| `translator/wsaa/render_condition.py` | `render_conditions(holder, indexed)`；INDICATOR 88 数组→带下标 get | |
| `translator/wsaa/render_class.py` | `_handle` 给 `render_conditions` 传 `indexed`（dims 非空或 occurs）；target 缺失的 REDEFINES 结果并入 fields；输出 `NUM_HELPER` | |
| `translator/wsaa/render_field.py` | 不变（复用） | |
| `docs/…/步骤03-WSAA块翻译设计.md` | §5 已知限制更新：标注哪些已补全、剩余 TODO 的明确原因 | |
| `docs/架构索引/项目总览.md` | 登记本步骤详细设计链接 | |

调用关系不变：`render_class._handle` → `render_view.render_redefines` / `render_condition.render_conditions`。

## 6. 双向同步与正确性论证（要点）

- **A/B/C 仍是「视图，无独立存储」**：所有 get/set 都落到 backing（数值变量或字符 target），
  改子↔改父经同一 backing，天然同步；定宽串读写互逆（`_toDigits`/`_fromDigits` 对非负值、
  位宽充足时往返一致）。
- **截断/补齐**：宽度不足时 `_toDigits` 高位截断、`_pad` 右补空格——与 COBOL MOVE 截断语义一致。
- **退化项**：任一不支持的构造（OCCURS-on-数值、编辑型、COMP-3、嵌套组、target 在 arrayed）
  仍走 TODO，绝不生成可能错误的 Java。

## 7. 自检计划（实现后执行，结果回填本文件 §8 与操作记录）

1. 重新运行 `scripts/translate_wsaa.py` 生成 Java。
2. `grep -c TODO`：预期从 27 降到 **E+F 剩余数**（约 12–13），逐条确认剩余项均为已决定保留类。
3. 抽样核对：AMOUNT1（BigDecimal scale2）、RES-CRRCD（日期数值切片）、WSAA-P（数组视图）、
   WSAA-STRING-R（数值 over 组）、IND-ON/OFF（带下标）各 1 处，人工读生成代码确认双向同步正确。
4. `javac`（若环境可用）或肉眼校验语法；确认 `_toDigits/_fromDigits` helper 已输出且 import 充分。

## 8. 实现结果（回填）

状态：🟢 已实现（2026-06-03）。

### 改动文件
- **新增** `translator/wsaa/storage.py`：定宽存储串构造（按设计 §5 把存储串逻辑从 render_view 下沉，
  保持单文件 <100 逻辑行）。导出 `scale_of`（PIC V 后位数）、`num_to_digits/num_from_digits`、
  `storage_accessor(tnode)→(读表达式, 写函数, W)`、`NUM_HELPER`（`_toDigits/_fromDigits`）。
- **改** `translator/wsaa/render_view.py`：删旧 `_string_accessor`；`render_redefines` 改为基于
  `storage_accessor`，新增 `_slice_view`（字符/数值子项切片）、`_array_view`（字符数组带下标，D9）、
  `_scalar_view`（alias 自身为标量 over 组/数值，D11）、`render_primary`（目标停用按主定义，D12）。
- **改** `translator/wsaa/render_condition.py`：`render_conditions(holder, indexed)`；INDICATOR 88
  在数组上下文生成 `indOn(int i)/indOff(int i)`（D7+D 类）。
- **改** `translator/wsaa/render_class.py`：`_handle` 给 `render_conditions` 传 `indexed`（dims 或 occurs）；
  REDEFINES 目标不在 `idx` 时走 `render_primary` 并入 `fields`；视图含数值串时追加 `NUM_HELPER`。

### 自检结果
- 重新运行 `scripts/translate_wsaa.py`，产物 `ZpoldwnmWsaa.java` 的 `// TODO` 由 **27 → 10**。
- 剩余 10 处全部为已决定保留类：**畸形层级 ×6（D14）** + **数组上下文 REDEFINES ×4（D13，
  WSXX/WS01/WS02-PCESTRM-X、WSXX-RCESTRM-X）**，无臆测。
- 抽样核对双向同步均正确：
  - `WSAA-AMOUNT1-CHAR`（X(17) over 9(15)V99）→ `getWsaaAmount1Char` 用 `_toDigits(...,17,2)`，set 经 `_fromDigits(_n,2)` 回写；
  - `WSAA-RCDYEAR/MONTH/DAY`（数值子项 over S9(08)）→ `int` 切片 get/set，offset 0/4/6；
  - `WSAA-P`（X(2) OCCURS 5 over X(10)）→ `getWsaaP(int i)/setWsaaP(int i,String)` 带 i-1 下标；
  - `WSAA-STRING-R`（9(03) over 组 SEX+ISSUE-AGE）→ `int getWsaaStringR()`，set 切回 `wsaaSex/wsaaIssueAge`；
  - `IND-ON/IND-OFF`（88 over INDIC-TABLE boolean[]）→ `indOn(int i)/indOff(int i)`；
  - `WSAA-CVCP-AMOUNT-D`（目标停用）→ 普通 `BigDecimal` 字段 + D12 注释。
- 括号配平：花括号 108/108；去注释/字符串后代码区圆括号净差 0（唯一不配平的 `(` 来自被 `_short`
  截断的 COBOL 原文注释，无害）。`javac` 环境不可用，未做编译校验。
