# 步骤18　绞杀项3① MOVE 动词迁 visitor 设计（rules 逐类迁 visitor·第一刀）

状态：🟢已实现（2026-06-26 认可 + 落地，§10 回填）

定位：落地 `架构演进-三相分层(预处理-ASG-visitor)初步设计.md` **§5 迁移分期第 3 项「rules 逐类迁 visitor」的第一刀**——
按动词顺序 MOVE → IF → PERFORM/THRU → CALL → STRING 逐类迁移，**本步只迁 MOVE 一个动词**。
承步骤17（相2 ASG 旁路已立、GO TO 单点验证通路），本步把 rules 对 MOVE 的确定性翻译
**抽成两路共用的公用模块**，rules 委托调用（行为零变化）、相3 visitor 共调，并建**常驻比对脚本**作每刀回归闸。

关联：
- 上位路线图：`架构演进…初步设计.md` §5-项3（逐类迁 visitor）、§6（绞杀期两套并存代价）、§9-Q4（动词顺序与比对工具）、§9-Q5（旧/新自动 diff 脚本）。
- 前序：`步骤17-旁路建相2-ASG设计.md` §6（项3 衔接）、§7-Q2（_lift 与 rules._sk_* 短期两份、项3 消除重复）。
- 复用对象（只读复用）：`translator/skeleton_gen/body_context.py`（`build_body_ctx` 装配 `Ctx`）、`asg/builder._lift`、`asg/visitor.AsgVisitor`。
- 受改造现状（本步动）：`translator/rules.py`（抽出 MOVE 译器 + 表达式底座，改委托）。

---

## 1. 本步目标与非目标

**目标**：
1. **抽公用**：把 rules 的 MOVE 确定性翻译 `_t_move` 及其依赖的「表达式底座」（operand/assign/struct/判型）
   下沉到新包 `translator/leaf/`，成为 rules 与相3 visitor **共用的唯一一份**逻辑。
2. **rules 委托**：`rules._t_move` 改为调用公用 `translate_move`；其余 `_t_*` 与条件翻译共享同一底座（只读 import）。
   **行为零变化**，旧 48 单测 + `regress_config_snapshot` 零 diff 作硬闸。
3. **相2 提升 MoveStmt**：`asg/nodes.py` 加 `MoveStmt` 节点，`_lift` 把 MOVE 从 `Leaf` 兜底提升为 `MoveStmt`。
4. **相3 visit_MoveStmt**：`asg/visitor.py` 加 `LeafJavaVisitor.visit_MoveStmt`，调同一 `translate_move`。
5. **常驻比对闸**：建 `scripts/diff_asg_vs_legacy.py`，对样例程序把每条 MOVE 走「旧 `_t_move`」与
   「ASG `visit_MoveStmt`」两路渲染，逐字符 diff（§5-项3 要求的产物比对）。

**非目标（本步明确不做）**：
- **不迁其它动词**：IF/EVALUATE/PERFORM/CALL/STRING/SET/算术仍在 rules，本步**只 MOVE**（§一.3 只做 X）。
- **不迁 `translate_leaf` 的循环重绑定包装**：for-each 体内 `struct_rebind`（叶子临时把结构体重绑到循环变量）是
  **循环上下文**，属 PERFORM/loop 那一刀；本步只迁**纯 `_t_move` 那一层**（见 §4.3 比对边界）。
- **不接入主翻译**：旧 `build_skeleton`→`translate_leaf` 通道仍是产物正本；ASG visitor 仅供比对自证，不下线旧路径（下线是 §5-项4）。
- **不改 config 正本**：specs/mappings 不动。

---

## 2. 已确认的决定（2026-06-26，用户认可）

- [策略] **抽公用模块，两路共调**（A 案）：`translator/leaf/` 持 `translate_move` 与表达式底座，
  rules 委托、visitor 共调 → **产物天然逐字符一致，零 diff 风险**。否决 B（visitor 重写、diff 对账有风险）、
  C（visitor 反向 import rules、违解耦）。依据 §16 复用优先、§17 公用优先、初步设计 §0 削偶然复杂度。
- [比对] **建常驻 `scripts/diff_asg_vs_legacy.py`**：每刀的回归闸，逐字符比对旧/新两路 MOVE 产物，常驻保留（§12 脚本一律留存、§9-Q5）。
- [复用利好] ASG 侧 leaf-ctx **直接复用 `body_context.build_body_ctx(program)`**（与旧路径同一 `Ctx`），
  保证两路 ctx 字节相同；本步**不另造** ctx 装配。

---

## 3. `translator/leaf/` 公用模块抽取边界（瘦而专，单文件逻辑 < 200 行）

### 3.1 抽取依据：`_t_move` 依赖闭包（探查结论，留痕）

`rules._t_move`（rules.py:1534）**非纯 token 工作**，闭包牵出整条表达式底座：

```
_t_move
 ├─ _struct_prefix / _struct_obj / _struct_cls      (结构体前缀→Java 对象/类)
 ├─ _operand                                         (源操作数→Java 表达式：字面量/字段/下标/引用修改/结构体读)
 │   └─ _refmod_lo/_refmod_hi · _is_field · _field_base · _pascal · _struct_*
 ├─ _lvalue / _assign                                (左值/赋值：字段 = / setter / new 结构体)
 ├─ _is_numeric_field / _is_bigdecimal               (判型，读 ctx.field_type_map)
 ├─ _bd · _java                                      (BigDecimal 包装 · COBOL名→camelCase)
 ├─ 常量集 _FIGURATIVE_BLANK / _FIGURATIVE_ZERO
 └─ 副作用：写 ctx.struct_function[prefix]=功能码  (MOVE …TO X-FUNCTION 仅记状态、不出行)
```

ctx 读取字段：`field_type_map / io_struct_prefixes / struct_objects / struct_classes /
struct_getter / struct_setter / struct_default_suffix`，写：`struct_function`。
**这条底座也被条件翻译 `_try_comparison`、其它 `_t_*`（SET/算术/CALL）共用**——正是该抽的公用部分（§17）。

### 3.2 包结构与文件职责

```
translator/leaf/                ← 新建「相3 叶子翻译公用底座」（rules 与 asg.visitor 共用）
├── __init__.py                 瘦门面：导出 translate_move + 表达式底座符号 + LeafCtx 协议
├── context.py                  LeafCtx 协议（叶子译器读取的 ctx 契约，duck-type / typing.Protocol）
├── expr.py                     表达式底座（纯函数，取 ctx）：operand/lvalue/assign/struct/判型/figurative/refmod/bd/java/pascal
└── move.py                     translate_move(toks, ctx) -> (lines, ok)：从 rules._t_move 原样搬
```

依赖方向（单向，无环）：`rules → leaf`，`asg.visitor → leaf`，`leaf.move → leaf.expr`，`leaf.expr/context → 无 rules 依赖`。

- **`context.py`**：`class LeafCtx(typing.Protocol)`——声明叶子译器读取的字段
  （`field_type_map / io_struct_prefixes / struct_objects / struct_classes / struct_getter /
  struct_setter / struct_default_suffix / struct_function`）。
  *设计思路*：**不搬整个 `rules.Ctx`**（Ctx 还含 `new_leaf/leaves/_counter/flow_label` 等 skeleton 层状态，不属叶子）；
  改用窄契约——`rules.Ctx` 结构化满足它（已有全部字段），ASG 侧也复用同一 `Ctx`（经 `build_body_ctx`），双方 duck-type 通过。
- **`expr.py`**：把 §3.1 底座函数 + 两个 figurative 常量集**原样搬入**（逻辑零改，仅迁址），
  `_FIGURATIVE_*` 与 `_REL_OPS` 中 MOVE 用到的部分一并迁；签名不变（`(tok, ctx)`），ctx 按 `LeafCtx` 取属性。
- **`move.py`**：`translate_move(toks, ctx) -> tuple[list[str], bool]`——`rules._t_move` 函数体**原样搬**，
  内部改 `from translator.leaf.expr import ...`。逻辑零改。

### 3.3 `rules.py` 改造（纯委托，行为零变化）

- 删除 §3.1 已迁的 helper 定义与 `_t_move` 函数体、`_FIGURATIVE_*` 常量；
  顶部 `from translator.leaf.expr import (_operand, _assign, _lvalue, _struct_prefix, _struct_obj,
  _struct_cls, _is_field, _is_numeric_field, _is_bigdecimal, _is_string_field, _java, _pascal,
  _field_base, _bd, _FIGURATIVE_BLANK, _FIGURATIVE_ZERO, ...)`、`from translator.leaf.move import translate_move`。
- `_dispatch_leaf` 中 `if verb == "MOVE": return _t_move(toks, ctx)` 改 `return translate_move(toks, ctx)`
  （或保留薄 `_t_move = translate_move` 别名，二选一，落地时定）。
- `Ctx` **留在 rules**（skeleton 层仍大量用），新增字段无；`Ctx` 天然满足 `LeafCtx`。
- *验证*：旧 48 单测 + `regress_config_snapshot` 零 diff（纯迁址+委托，行为不变，作硬闸）。

---

## 4. 相2/相3 侧改造（ASG 提升 MOVE + visit）

### 4.1 `asg/nodes.py`：加 `MoveStmt`

```python
@dataclass
class MoveStmt:
    tokens: list[str] = field(default_factory=list)   # 原始 MOVE token（src + TO + dsts），供 translate_move 直接消费
    raw: str = ""
    lineno: int = 0
```
*设计思路*：MOVE 的语义（src/多 dst/figurative/结构体）全由公用 `translate_move` 从 token 解析，
节点本步**只保 token**（与 `Leaf` 同构但带类型名，使 visitor 可分派）；字段化（拆 src/dsts）留后续按需，**本步不过度建模**。

### 4.2 `asg/builder._lift`：MOVE → MoveStmt（唯一嗅探点收口）

`_lift` 的 simple 分支加：`if first == "MOVE": return nodes.MoveStmt(tokens=list(st.tokens), raw=st.raw)`
（置于 GO/CALL 同级，落在 `Leaf` 兜底之前）。token 嗅探仍只在 `_lift` 一处。

### 4.3 `asg/visitor.py`：`LeafJavaVisitor.visit_MoveStmt`

```python
class LeafJavaVisitor(AsgVisitor):
    """相3 叶子翻译 visitor：visit_MoveStmt → 调公用 translate_move（与旧 rules._t_move 同一函数）。"""
    def __init__(self, ctx):           # ctx 满足 LeafCtx（由 build_body_ctx 提供）
        self.ctx = ctx
    def visit_MoveStmt(self, node):
        lines, _ok = translate_move(node.tokens, self.ctx)
        return lines
```
*比对边界（关键，honest scope）*：本步迁的是**纯 `_t_move` 那一层**。旧路径 `translate_leaf` 外层还有
for-each 体内 `struct_rebind`（循环上下文重绑定）——那属 PERFORM/loop 刀，**本步不复刻**。
故比对在 `_t_move` 边界做：`rules`（迁后即 `translate_move`）与 `visit_MoveStmt` 调同一函数同一 ctx → **逐字符必然相等**；
循环内重绑定的 MOVE 留待 PERFORM 刀，本步比对脚本对其**标注跳过**（不算差异）。

> `GotoJavaVisitor`（步骤17 单点 demo）保留；`LeafJavaVisitor` 与之并列，互不影响。

---

## 5. `scripts/diff_asg_vs_legacy.py`（常驻比对闸）

- **入参**：`<program.cob>`（样例源），可选 `--verb MOVE`（本步固定 MOVE）。
- **流程**：`parse(cob)` → 一份 `ctx, _ = build_body_ctx(program)`（两路共用）→
  - 旧路：遍历 program，对每条 `kind=="simple"` 且首 token==MOVE 的 `Stmt`，跑 `rules.translate_move(st.tokens, ctx)`；
  - 新路：`build_asg(program)` → 遍历 `MoveStmt` 节点，跑 `LeafJavaVisitor(ctx).visit(node)`；
  - 按源码顺序对齐两路 MOVE 输出，逐字符 diff，打印不一致项（带 lineno/raw）。
- **退出码**：全等 0、有差异 1（CI/回归可断言）。循环内重绑定 MOVE 标注 skip，不计入差异。
- *设计思路*：常驻 `scripts/`（§12），项3 后续每刀复用同一脚手（加 `--verb IF` 等），是 §5-项3「逐字符比对旧路径」的落地工具（§9-Q5）。

---

## 6. 落地步骤（认可后严格按序，每步出产物即验）

1. 建 `translator/leaf/`：`context.py`（LeafCtx 协议）→ `expr.py`（底座原样搬）→ `move.py`（translate_move 原样搬）→ `__init__.py` 门面。
2. 改 `rules.py`：删已迁定义、改 import、`_dispatch_leaf` 委托。**跑 `python -m unittest test_translation` + `scripts/regress_config_snapshot.py` → 须零 diff/全绿**（硬闸，先验旧路径无副作用）。
3. `asg/nodes.py` 加 `MoveStmt`；`asg/builder._lift` 加 MOVE 分支。跑 ASG 既有单测须仍绿。
4. `asg/visitor.py` 加 `LeafJavaVisitor`。
5. `scripts/diff_asg_vs_legacy.py`。对样例程序跑，**两路 MOVE 逐字符零差异**（循环重绑定项 skip）。
6. 加单测（§7）。全量 `test_translation` 全绿。
7. 回填本设计「实现结果」、更新 `docs/架构索引/项目总览.md`（新增 `translator/leaf/` 包 + `LeafJavaVisitor` + 比对脚本条目与调用关系）、写 `docs/操作记录/步骤18-…操作记录.md`（命令/产物/校验/Token 分析）。

---

## 7. 自检与验收

- **旧路径零影响（硬闸）**：`test_translation` 旧用例全绿、`regress_config_snapshot` 零 diff（迁址+委托，行为不变）。
- **新增单测**（`test_translation.py`）：
  - ① `TestLeafMoveExtract`：`translate_move` 抽出后，对若干 MOVE token（普通字段 / figurative SPACES/ZERO /
    结构体字段 setter / X-PARAMS 互拷 BeanUtils / MOVE…TO X-FUNCTION 仅记 struct_function）输出与抽取前快照一致。
  - ② `TestAsgMoveLift`：含 MOVE 的最小程序 `build_asg` 后，对应节点为 `MoveStmt` 且 `tokens` == segmenter 切分 token。
  - ③ `TestAsgMoveVisitor`：`LeafJavaVisitor(ctx).visit(moveNode)` == `rules.translate_move(toks, ctx)`（逐字符；同函数同 ctx，必然相等，作通路自证）。
  - ④ `diff_asg_vs_legacy.py` 对样例源退出码 0（无差异）。
- **不接受**：任何使旧用例/快照变化的副作用；MOVE 之外动词被改动；循环重绑定被半迁。

---

## 8. 开放问题（留后续刀）

- **Q1**：`translate_leaf` 的 `struct_rebind` 循环重绑定何时迁——随 PERFORM/loop 刀；届时 visitor 需重建循环上下文。
- **Q2**：`MoveStmt` 是否字段化（拆 `src`/`dsts`/`is_function_move`）——待 IF/EVALUATE 等需在节点层判 MOVE 形态时再定，本步只保 token。
- **Q3**：`expr.py` 底座被条件翻译共用，IF 刀迁 `_try_condition` 时一并归入 `translator/leaf/`（cond.py）还是另置——IF 刀定。
- **Q4**：ASG `_lift` 与 rules `_sk_*` 短期两份判定（步骤17 §7-Q2）何时归一——全动词迁完（§5-项4 下线旧 token 通道）时清算。

---

## 9. 待确认的决定（请认可后我按 §6 落地）

- [包/边界] 新建 `translator/leaf/{__init__,context,expr,move}.py`，把 `_t_move` + 表达式底座下沉为公用；rules 改委托 import。
- [契约] `LeafCtx` 用 `typing.Protocol` 窄契约，**不搬整个 `rules.Ctx`**；`rules.Ctx` 与 `build_body_ctx` 产物 duck-type 满足。
- [复用] ASG 侧 leaf-ctx **直接复用 `body_context.build_body_ctx`**，不另造 ctx 装配。
- [节点] `MoveStmt` 本步**只保 token**（不字段化），`_lift` 收口 MOVE 嗅探。
- [范围] **只迁纯 `_t_move` 一层**；`translate_leaf` 循环重绑定留 PERFORM 刀；比对在 `_t_move` 边界、循环重绑定项 skip。
- [比对] 常驻 `scripts/diff_asg_vs_legacy.py` 作项3 每刀回归闸。

> 本设计经认可后，即按 §6 落地（仅 MOVE 一刀：抽公用 + rules 委托 + ASG 提升/visit + 比对脚本）。

---

## 10. 实现结果（回填，2026-06-26）

**公用包**（`translator/leaf/`，逻辑行均 < 200）：
- `context.py`：`LeafCtx(typing.Protocol)` 窄契约（8 字段：field_type_map / io_struct_prefixes /
  struct_objects / struct_classes / struct_getter / struct_setter / struct_default_suffix / struct_function）。
- `expr.py`：表达式底座 18 个符号**原样迁自 rules**（_operand/_lvalue/_assign/_struct_* /_is_* /_java/_pascal/
  _field_base/_refmod_*/_bd + 两 figurative 常量集），逻辑零改，ctx 注解 `Ctx → LeafCtx`。
- `move.py`：`translate_move(toks, ctx)` 迁自 `rules._t_move`，逻辑零改。
- `__init__.py`：门面导出 `LeafCtx` / `translate_move`。

**rules 改造**（纯迁址 + 委托）：删除上述 18 符号 + `_t_move` 定义；顶部 `from translator.leaf.expr import (…)`
+ `from translator.leaf.move import translate_move`；`_dispatch_leaf` 的 MOVE 分支改 `return translate_move(toks, ctx)`。
`Ctx` 留在 rules（skeleton 层仍用），天然满足 `LeafCtx`。依赖单向 `rules → leaf`，无环。

**ASG 改造**：`nodes.MoveStmt(tokens, raw, lineno)`；`builder._lift` simple 分支加 `first=="MOVE" → MoveStmt`
（置于 GO/CALL 同级、Leaf 兜底之前）；`visitor.LeafJavaVisitor(ctx).visit_MoveStmt → translate_move`；
`asg/__init__` 导出 `MoveStmt` / `LeafJavaVisitor`。

**比对闸**：`scripts/diff_asg_vs_legacy.py <prog.cob> [--verb MOVE]`——legacy 侧从 segmenter 切分树
（含 IF/PERFORM 内嵌套，按 `_lift` 递归序）枚举每条 MOVE 跑 `translate_move`；asg 侧 `build_asg`→遍历 `MoveStmt`
跑 `LeafJavaVisitor`；按源码序逐字符 diff，退出码 全等 0 / 有差异 1。两路共用 `build_body_ctx` 同一 ctx。

**与设计偏差**：无（按 §6 落地）。比对边界确认无 skip 项——两路均比 `translate_move` 层、本就不施加循环重绑定（§4.3）。

**验收（§7 四项，均落实为 `test_translation.py` 单测）**：
- `TestLeafMoveExtract`（①）：figurative SPACES→`""` / ZERO→`0`、数值字面量→`new BigDecimal("100")`、
  字面量→`"Y"`、结构体 setter、`MOVE …TO X-FUNCTION` 不出行仅记 struct_function、X-PARAMS 互拷 BeanUtils——逐项断言。
- `TestAsgMoveLift`（②）：MOVE 提升为 `MoveStmt` 且 `tokens` 与 segmenter 一致、不再落 `Leaf`。
- `TestAsgMoveVisitor`（③）：`LeafJavaVisitor.visit(MoveStmt) == translate_move`（逐字符）。
- `TestDiffAsgVsLegacy`（④）：内联程序（含 IF 内嵌套 MOVE）两路 MOVE 逐字符一致。

**回归闸**：`python -m unittest test_translation` → **86 通过 / 2 skip / 0 失败**（旧 75 + 新 11）；
`scripts/regress_config_snapshot.py`（UTF-8 输出）exit 0（leaf 抽取未触碰 config / resolve_io_info，rules→leaf import 完好）；
`scripts/diff_asg_vs_legacy.py` 对样例源 exit 0（7 条 MOVE 两路逐字符一致）。

> 注：`regress_config_snapshot.py` 在 GBK 控制台直接 stdout 会因 `∉`(U+2209) 报 UnicodeEncodeError——
> 是终端编码问题，非回归；`PYTHONIOENCODING=utf-8` 重定向到文件即 exit 0。
