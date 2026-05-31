# 步骤03 · WORKING-STORAGE（WSAA）块 → Java 确定性翻译设计

状态：🟢 已实现
对应计划：`~/.claude/plans/cosmic-tickling-treehouse.md`（已认可）
概要索引：见 `../架构索引/项目总览.md`

---

## 1. 背景与目标

六步流水线第 3 步「按块生成 Java」的首块：把拆解产物
`/home/zp/Documents/cob/ZPOLDWNM/拆解/ZPOLDWNMWSAA.cob`（1177 行，WORKING-STORAGE
全局变量定义）翻译为 Java 类 `ZpoldwnmWsaa`。

**纯确定性、不调大模型**：把用户给的 WORKING-STORAGE 翻译规范固化为「COBOL 构造 → Java」
映射，由 Python 脚本 + `config/type_mappings.yaml` 驱动生成。

## 2. 已确认的决定（固化，不再问）

1. 方式：增强确定性解析/渲染，按规范固化模板自动生成（无 LLM）。
2. 重叠/REDEFINES：普通字段 + 派生视图方法（叶子=backing，组名/REDEFINES 别名=getter/setter
   视图，定宽切片双向同步）。
3. COPY 拷贝簿块（源文件 1036–1175，约 150 个 COPY）：等同 import，**不翻译**、不生成字段。
4. 输出：一个 cob 一个包；`package zpoldwnm;`；类名按协作规范 `{PROGRAM}WSAA` → `ZpoldwnmWsaa`；
   产物 `…/ZPOLDWNM/拆解/ZpoldwnmWsaa.java`。整体包结构后续单独设计。

## 3. 构造 → Java 映射（模板）

| COBOL | Java |
|---|---|
| `PIC X(n)` | `String`（VALUE→init，否则 `""`） |
| `PIC 9(n)`/`999` ≤9 位 | `int`；>9 位或 `S9(n) COMP-3` 无小数 → `long` |
| `S9(m)V9(k)`/`9(m)V99`/带 V 的 COMP-3 | `BigDecimal` |
| `VALUE 'str'`/数字/`SPACES`/`ZEROES`/`X'0F'` | `="str"`/`=n`(或 `new BigDecimal`)/`=""`/`=0`/`""` |
| 数字编辑 `Z(14)9.99`/`ZZ9`/`Z(01)9` | `String`（显示串） |
| `PIC 1`（INDICATOR） | `boolean` |
| `88 名 VALUES 'V1' 'V2'…` | `public boolean 名(){ return f.equals("V1")||…; }` |
| 一维 `OCCURS n` | `T[] = new T[n]` |
| 嵌套 `OCCURS`（27×4） | `T[][] = new T[27][4]` |
| 纯记录组 | 子字段平铺 + `// ── 组名 ──` 注释 |
| 重叠组（全字符子项、无 OCCURS） | `getX()` 拼接 / `setX(String)` 切分（双向同步） |
| `REDEFINES`（目标为字符标量/可视图组、非数组） | 别名子项 = 对目标字符视图的定宽 get/set |
| 常量表组 `FORMATS`/`ERRORS`/`HARDCODED` | 子字段 + VALUE init |
| `FILLER` | 不生成字段，仅计长度/偏移 |
| COPY 块 | 跳过 |

字符宽度（视图切片用）：`X(n)=n`、`9(n)=n`、`S/V=0`、`COMP-3=ceil((位数+1)/2)`，组=子项跨度之和。

## 4. 模块设计（各文件职责 + 调用）

### 解析侧 `parser/ws/`（WsNode 森林）
- `model.py`：`WsNode`（level/name/pic/comp/occurs/redefines/value/conditions/children/
  is_filler/is_indicator/java_type/is_edited/byte_len）、`Condition`（88 名+取值/布尔）。
- `lines.py`：`merge_entries()` 读块→去注释（首列 `*`/`/`）→续行合并（非层级号行并入上一条）→
  跳过 WS/LINKAGE 头→遇 COPY/SECTION/DIVISION 止。
- `entry.py`：`parse_entry()` 单条定义行→WsNode（COMP/VALUE 用「前置空白」锚避免误匹配名字里的关键字）。
- `conditions.py`：`is_condition()/parse_condition()` 解析 88→Condition。
- `value.py`：`extract_value_raw()/literals()/java_init()`（figurative、`X'..'` hex、`B'..'`、数字、串归一）。
- `pic.py`：`java_type()`（config 驱动，`is_edited`/`PIC 1` 前置判定）、`char_width()`、`_digits()`。
- `tree.py`：`build()` = `build_tree()`（栈按 level 建父子、88 挂前一兄弟）+ `backfill()`（自底向上算
  类型/宽度，畸形叶子也递归回填）。
- `__init__.py`：`parse_ws(cob)`。

### 渲染侧 `translator/wsaa/`（树 → Java）
- `render_field.py`：`render_field(node,dims)` 叶子→字段声明（VALUE init、一/二维数组）；`java_name`
  复用 `parser.variable_resolver._cobol_to_java_name`。
- `render_condition.py`：`render_conditions()` 88→布尔方法（INDICATOR 留 TODO）。
- `render_view.py`：`can_group_view`/`render_group_view`（重叠组拼接/切分）、`render_redefines`
  （目标字符标量/可视图组→定宽切片 get/set；外部/数组/数值目标→退化普通字段+TODO）、`PAD_HELPER`。
- `render_class.py`：`render_wsaa()` 深度遍历，累计 OCCURS 维度、去重、收集字段/视图/条件，
  拼 package+import+类体；`_index_and_groups` 产出 名→节点 索引、可视图组、数组化名集合。
- `__init__.py`：`render_wsaa(roots, program)`。

### 入口 `scripts/translate_wsaa.py`
瘦入口：`--program/--in/--out`，调 `parse_ws → render_wsaa → 写文件`，打印自检统计。

调用链：`scripts/translate_wsaa.py → parser.ws.parse_ws →(lines→entry/conditions/value/pic→tree)`；
`→ translator.wsaa.render_wsaa →(render_field/condition/view/class)`。单向无环。

## 5. 已知限制（如实标注，输出内含 TODO）

- **数值/编辑型 REDEFINES**（如 `WSAA-AMOUNT1-CHAR` over `9(15)V99`）：目标非字符型，
  退化为普通字段 + `// TODO`（未做数值↔定宽串的零位视图）。共约 8 处。
- **OCCURS 数组上下文内的 REDEFINES**（`WSXX-PCESTRM-R` 等）：定宽标量视图不适用 → TODO + 标量占位。
- **外部 REDEFINES 目标**（`WSAA-CVCP-AMOUNT` 在 copybook）：普通字段 + TODO。
- **畸形层级区**（源 295–327，父 01 被注释、层级跳变）：尽力平铺 + `// TODO 畸形层级`。
- **INDICATOR 88**（`IND-OFF/IND-ON`）：需结合数组下标，留 TODO。
- 编辑 PIC 的 `byte_len` 不计插入字符（. ,），仅近似（编辑字段为显示串，极少参与切片）。

## 6. 验证结果（2026-05-31）

生成 `ZpoldwnmWsaa.java`（1278 行）。自检：01 级根 383 / 节点 891 / 组 95 / 叶子 796 /
88 条件 12 / REDEFINES 22 / OCCURS 27 / 编辑 PIC 18。
结构 lint：772 唯一字段（无重名冲突）、68 唯一方法、花括号 70/70 平衡、无 类型/初值 不匹配、
无关键字泄漏进 88 取值。抽样核对 WSAA-PROG/LETOKEYS/A65086(88)/CP-AMOUNT-D(2D)/
CTRL-FLGS(REDEFINES 视图)/各 PIC 类型 均符合规范。本机无 `javac`，未做编译校验。
