# 步骤19　绞杀项3② IF 动词迁 visitor 设计（rules 逐类迁 visitor·第二刀）

状态：🟢已实现（2026-06-26 认可 + 落地，§9 回填）

定位：落地 `架构演进-三相分层(预处理-ASG-visitor)初步设计.md` **§5 迁移分期第 3 项「rules 逐类迁 visitor」的第二刀**——
动词顺序 MOVE → **IF** → PERFORM/THRU → CALL → STRING，承步骤18（MOVE 刀已抽 `translator/leaf/` 公用底座 +
rules 委托 + ASG `visit_MoveStmt` + 比对闸）。本步**只迁 IF 一个动词的「条件翻译」公用层 + visit_IfStmt 控制结构渲染**。

关联：
- 上位路线图：`架构演进…初步设计.md` §5-项3（逐类迁 visitor）、§9-Q4（动词顺序）、§9-Q5（旧/新自动 diff 脚本）。
- 前序：`步骤18-绞杀项3①MOVE迁visitor设计.md` §3（leaf 包结构）、§5（比对闸脚手）、**§8-Q3（条件翻译归入 `translator/leaf/cond.py` 由本刀定）**、§4.3（诚实比对边界范式）。
- 复用对象（只读复用）：`translator/leaf/expr.py`（`_operand`/`_is_numeric_field`/`_is_bigdecimal`/`_is_string_field`/`_bd`/`_FIGURATIVE_*` 已在盘）、
  `translator/skeleton_gen/body_context.build_body_ctx`、`asg/builder._lift`（IfStmt 提升**已就位**）、`asg/visitor.AsgVisitor`。
- 受改造现状（本步动）：`translator/rules.py`（抽出 `_try_condition` 闭包 + 改委托）、`asg/visitor.py`（加 `visit_IfStmt`）、`scripts/diff_asg_vs_legacy.py`（加 `--verb IF`）。

---

## 1. 本步目标与非目标

**目标**：
1. **抽公用**：把 rules 的条件翻译 `_try_condition` / `_try_comparison` / `_negate_numeric` 下沉到新文件
   `translator/leaf/cond.py`，对外名 `translate_condition(tokens, ctx) -> str | None`，复用 `leaf.expr` 底座，
   成为 rules 与相3 visitor **共用的唯一一份**条件逻辑（落地 §8-Q3）。
2. **rules 委托**：rules 顶部 `from translator.leaf.cond import translate_condition as _try_condition`（保旧名别名，4 处调用点零改），
   删除 rules 内 `_try_condition`/`_try_comparison`/`_negate_numeric` 定义。**行为零变化**，旧单测 + `regress_config_snapshot` 零 diff 作硬闸。
3. **相3 visit_IfStmt**：`asg/visitor.LeafJavaVisitor` 加 `visit_IfStmt`——渲染 `if (translate_condition(cond)) {` + 递归 visit then/els 体 + 收口 `}`，
   复刻 `rules._sk_if` 的控制结构形状与 **cond=None 兜底**（整 IF 交 LLM → 占位）。配套 `visit_Leaf`（未迁动词 → 诚实占位）使 body 递归产出扁平行。
4. **比对闸扩 IF**：`scripts/diff_asg_vs_legacy.py` 加 `--verb IF`——对样例程序枚举每条 IF，比对**条件表达式**两路逐字符
   （legacy `_try_condition` vs `leaf.cond.translate_condition`，同函数同 ctx → 必然相等）。

**非目标（本步明确不做）**：
- **不迁 IF 的 body 叶子填充机制**：旧路 `_sk_if` body 走 `build_skeleton`→`ctx.new_leaf` 占位、后续 `translate_leaf` 回填；
  本步**不复刻该占位/回填管线**。visit_IfStmt 的 body 仅对**已迁动词**（MOVE/嵌套 IF）直译，未迁动词落 `visit_Leaf` 占位。
- **不迁 EVALUATE / WHEN / PERFORM-UNTIL 的渲染**：`_try_condition` 被 WHEN / UNTIL / BEGN-foreach 过滤器共用（rules.py:394/1126/1151），
  抽公用后这些调用点**随之委托同一函数**（纯迁址、零行为变化），但其**外层渲染**（EVALUATE/PERFORM 骨架）**仍在 rules，不属本刀**。
- **不做 block 级比对**：IF body 两路天然不等（旧占位 vs 新直译），比对**只在条件表达式边界**（§4.3 诚实边界，同 MOVE 刀）。
- **不接入主翻译**：旧 `build_skeleton`→`translate_leaf` 仍是产物正本；ASG visitor 仅供比对自证，不下线旧路径（下线是 §5-项4）。
- **不改 config 正本**；不动 `_REL_OPS`（rules.py:70 现为未被 `_try_condition` 闭包引用的独立常量，留原处不连带迁）。

---

## 2. 待确认的决定（请认可后按 §6 落地）

- [策略] **沿用 A 案「抽公用、两路共调」**：`translator/leaf/cond.py` 持 `translate_condition`，rules 委托、visit_IfStmt 共调 →
  **条件产物天然逐字符一致，零 diff 风险**（同步骤18 §2，依据 §16/§17 复用优先、初步设计 §0 削偶然复杂度）。
- [文件] 条件翻译归入 **`translator/leaf/cond.py`**（落地步骤18 §8-Q3，与 `move.py` 并列，不塞进 `expr.py`——expr 是无控制流的纯表达式底座，cond 是「AND/OR 切分 + 关系比较」的条件层，职责分离、各自 < 200 行）。
- [委托] rules 用 `translate_condition as _try_condition` **别名**导回，4 处调用点（_sk_if / foreach 过滤 / 两处 UNTIL）零改。
- [节点] IfStmt 已有（cond/then/els），`_lift` 提升**已就位**，本步**不动 nodes/builder**。
- [范围] visit_IfStmt 复刻控制结构 + cond=None 兜底；body 只直译已迁动词，未迁落 `visit_Leaf` 占位；比对只在条件边界。

---

## 3. `translator/leaf/cond.py` 抽取边界（瘦而专，逻辑行 < 200）

### 3.1 抽取依据：`_try_condition` 依赖闭包（探查结论，留痕）

`rules._try_condition`（rules.py:79）→ `_try_comparison`（:107）→ `_negate_numeric`（:181）三者构成条件翻译子系统，
其下沉依赖**已全部在 `leaf.expr`**（步骤18 已迁）：

```
translate_condition (_try_condition)        AND/OR 切分 → 逐段 _try_comparison → " " join
 └─ _try_comparison                          定位关系运算符(=/>/</>=/<=,含 NOT)、判型选 Java 写法
     ├─ _operand                             (leaf.expr) 操作数→Java 表达式
     ├─ _is_numeric_field / _is_bigdecimal / _is_string_field   (leaf.expr) 判型选数值/字符串比较
     ├─ _bd                                  (leaf.expr) BigDecimal 包装
     ├─ _FIGURATIVE_BLANK / _FIGURATIVE_ZERO (leaf.expr) StringUtils.isBlank / 0
     └─ _negate_numeric                      本子系统私有：NOT + 数值比较的取反映射
```

ctx 读取字段：`field_type_map`（判型）——已在 `LeafCtx` 契约内（步骤18 §3.2），**无需扩契约**。
结论：cond.py **零新依赖**，纯迁址 + 复用 expr 底座；`_negate_numeric` 为子系统私有，一并迁入 cond.py（不外泄到 `__init__` 门面）。

### 3.2 文件职责与门面

```
translator/leaf/
├── __init__.py     门面：增导出 translate_condition（与 translate_move 并列）
├── context.py      LeafCtx 契约（不变，field_type_map 已涵盖条件判型）
├── expr.py         表达式底座（不变，被 cond 复用）
├── move.py         translate_move（不变）
└── cond.py         ← 新建：translate_condition + _try_comparison + _negate_numeric（迁自 rules，逻辑零改）
```

依赖方向（单向无环）：`rules → leaf.cond`、`asg.visitor → leaf.cond`、`leaf.cond → leaf.expr`、`leaf.cond → leaf.context`。

- **`cond.py`**：`translate_condition(tokens, ctx) -> str | None` ＝ `_try_condition` 函数体**原样搬**；
  `_try_comparison`、`_negate_numeric` 一并搬，内部 `from translator.leaf.expr import (_operand, _is_numeric_field,
  _is_bigdecimal, _is_string_field, _bd, _FIGURATIVE_BLANK, _FIGURATIVE_ZERO)`。ctx 注解 `Ctx → LeafCtx`。逻辑零改。
- **`__init__.py`**：增 `from translator.leaf.cond import translate_condition`，`__all__` 加 `"translate_condition"`。

### 3.3 `rules.py` 改造（纯委托，行为零变化）

- 删除 `_try_condition`（:79-104）、`_try_comparison`（:107-178）、`_negate_numeric`（:181-183）三处定义。
- 顶部增 `from translator.leaf.cond import translate_condition as _try_condition`
  （别名导回 → `_sk_if`(:985)、foreach 过滤(:394)、PERFORM-UNTIL 两处(:1126/1151) **调用点零改**）。
- `Ctx` 留在 rules（天然满足 `LeafCtx`，field_type_map 已有）。依赖单向 `rules → leaf`，无环。
- *验证*：旧单测 + `regress_config_snapshot` 零 diff（纯迁址+委托，作硬闸）。

---

## 4. 相3 侧改造（visit_IfStmt 控制结构渲染）

### 4.1 `asg/visitor.py`：`LeafJavaVisitor.visit_IfStmt` + `visit_Leaf`

```python
class LeafJavaVisitor(AsgVisitor):
    def visit_IfStmt(self, node) -> list[str]:
        cond = translate_condition(node.cond, self.ctx)
        if cond is None:                                  # 复刻 _sk_if：条件不可定 → 整 IF 交 LLM（占位）
            return [f"// TODO-IF: {node.raw}"]
        lines = [f"if ({cond}) {{"]
        lines += self._body(node.then) or ["    // (空)"]
        if node.els:
            lines.append("} else {")
            lines += self._body(node.els)
        lines.append("}")
        return lines

    def _body(self, stmts) -> list[str]:
        """递归 visit 子节点并扁平化为 Java 行（已迁动词直译，未迁落占位）。"""
        out: list[str] = []
        for c in stmts:
            for ln in self.visit(c):                      # visit_MoveStmt / visit_IfStmt → list[str]
                out.append("    " + ln)
        return out

    def visit_Leaf(self, node) -> list[str]:              # 未迁动词：诚实占位（非空 body 可见）
        return [f"// TODO-LEAF: {node.raw}"]
```

*设计思路*：
- **形状复刻 `_sk_if`**：`if (cond) {` / `} else {` / `}`、cond=None 兜底、空 then 补 `// (空)`——与旧骨架同构，
  保证 IF **控制结构**在 visitor 侧可独立成形（不再依赖 token 嗅探）。
- **body 仅直译已迁动词**：MoveStmt → `visit_MoveStmt`（步骤18）、嵌套 IfStmt → 递归本方法；其余（CALL/算术/GOTO…）
  暂落 `visit_Leaf` 占位。这是绞杀**渐进**的诚实呈现：body 完整直译随后续动词刀逐步补齐（§5-项4 前不下线旧路）。
- **缩进**：`_body` 统一加一级缩进；与旧 `_sk_if` 的 `_ind(indent+1)` 等价（绝对层级由比对边界外，见 §4.2）。

> `visit_GotoStmt` 仍在 `GotoJavaVisitor`（步骤17 demo），`LeafJavaVisitor` 不复刻——GOTO 是后续刀；
> 本步 `LeafJavaVisitor` 仅扩 IF（条件 + 结构）与 Leaf 占位。

### 4.2 比对边界（关键，honest scope）

本刀迁的是**条件翻译那一层**。比对落在 IF 的**条件表达式**：
`rules`（迁后即 `translate_condition`）与 `translate_condition` 调**同一函数同一 ctx** → 条件串**逐字符必然相等**。

**body 不比对**：旧路 `_sk_if` body 是 `ctx.new_leaf` 占位串（`/*__LEAF_n__*/`）、新路 `visit_IfStmt` body 是直译/占位，
两者**本就不等**（占位 vs 直译）——这是渐进迁移的预期态，非缺陷。block 级一致须待全部动词迁完（§5-项4），
故本刀比对脚本对 body **不取样**，只取条件串（同 MOVE 刀 §4.3「只比 translate_move 层、循环重绑定 skip」的诚实边界范式）。

---

## 5. `scripts/diff_asg_vs_legacy.py` 扩 `--verb IF`

- **入参**：`--verb {MOVE,IF}`（默认 MOVE，本步加 IF 选项）。
- **IF 流程**（复用步骤18 同一脚手：`parse` → `build_body_ctx` 单份 ctx 两路共用）：
  - 旧路：`split_paragraphs`→`segment`→`_walk_segmenter_stmts` 枚举每条 `kind=="if"` 的 `Stmt`，跑 `rules._try_condition(st.tokens, ctx)`，收 `(raw, cond_str)`；
  - 新路：`build_asg` → 遍历 `IfStmt` 节点（新增 `_IfCollector(AsgVisitor).visit_IfStmt`），跑 `translate_condition(node.cond, ctx)`，收 `(raw, cond_str)`；
  - 按源码序对齐，逐字符 diff 条件串（None 也比，两路应同为 None）。
- **退出码**：全等 0 / 有差异 1。
- *设计思路*：脚手沿用步骤18（`_walk_segmenter_stmts` 已含 then/else/when/perform 递归序，IF 嵌套天然覆盖），
  仅按 `--verb` 分派取样器与渲染函数，**不重写**比对主干（§16 复用）。

---

## 6. 落地步骤（认可后严格按序，每步出产物即验）

1. 建 `translator/leaf/cond.py`：`translate_condition`+`_try_comparison`+`_negate_numeric` 原样搬，import `leaf.expr`。改 `__init__.py` 门面增导出。
2. 改 `rules.py`：删三处定义、加别名 import。**跑 `python -m unittest test_translation` + `scripts/regress_config_snapshot.py` → 须全绿/零 diff**（硬闸，先验旧路径无副作用）。
3. `asg/visitor.py`：`LeafJavaVisitor` 加 `visit_IfStmt`/`_body`/`visit_Leaf`。跑既有 ASG 单测须仍绿（不破 MOVE 比对）。
4. `scripts/diff_asg_vs_legacy.py`：加 `--verb IF` + `_IfCollector` + 取样分派。对样例程序跑 `--verb IF`，**条件串两路逐字符零差异**。
5. 加单测（§7）。全量 `test_translation` 全绿。
6. 回填本设计「实现结果」、更新 `docs/架构索引/项目总览.md`（`translator/leaf/cond.py` + `visit_IfStmt` + 比对闸 IF 条目）、写 `docs/操作记录/步骤19-…操作记录.md`（命令/产物/校验/Token 分析）。

---

## 7. 自检与验收

- **旧路径零影响（硬闸）**：`test_translation` 旧用例全绿、`regress_config_snapshot` 零 diff（迁址+委托，行为不变）。
- **新增单测**（`test_translation.py`）：
  - ① `TestLeafCondExtract`：`translate_condition` 抽出后，对若干条件 token（数值 `=`/`>`、`NOT =`、`= SPACES`→`StringUtils.isBlank`、
    BigDecimal `compareTo`、AND/OR 复合、88/复杂条件→`None`）输出与抽取前一致。
  - ② `TestAsgIfVisitor`：含 IF 的最小程序 `build_asg` 后，`LeafJavaVisitor.visit(IfStmt)` 的**条件行** == `rules._try_condition(cond, ctx)`（逐字符）；
    cond=None 时落 `// TODO-IF`；then 内 MoveStmt 直译、未迁动词落 `// TODO-LEAF`、嵌套 IF 递归成形。
  - ③ `TestDiffAsgVsLegacyIf`：内联程序（含嵌套 IF / AND-OR / NOT）`--verb IF` 两路条件串逐字符一致。
- **不接受**：任何使旧用例/快照变化的副作用；IF 之外动词被改动；body 占位/回填管线被半迁；block 级被强行比对而引入伪差异。

---

## 8. 开放问题（留后续刀）

- **Q1**：visit_IfStmt body 的完整直译（CALL/算术/GOTO 落地、占位归零）——随对应动词刀逐步补齐。
- **Q2**：EVALUATE/WHEN 外层渲染迁 visitor（`visit_EvaluateStmt`）——EVALUATE 刀；其 WHEN 条件已可复用 `translate_condition`。
- **Q3**：PERFORM-UNTIL/VARYING 的条件已复用 `translate_condition`，但循环**头部/重绑定**渲染留 PERFORM 刀（步骤18 §8-Q1）。
- **Q4**：block 级（含 body）两路一致何时可断言——全动词迁完、§5-项4 下线旧 token 通道时统一回归。

---

## 9. 实现结果（回填，2026-06-26）

**公用包**（`translator/leaf/cond.py`，逻辑行 < 200）：
- `translate_condition(tokens, ctx)` 迁自 `rules._try_condition`；`_try_comparison`、`_negate_numeric` 一并迁，逻辑零改。
- import `leaf.expr` 的 `_operand/_is_numeric_field/_is_bigdecimal/_is_string_field/_bd/_FIGURATIVE_BLANK/_FIGURATIVE_ZERO`；ctx 注解 `Ctx → LeafCtx`。**零新依赖**（field_type_map 已在 LeafCtx 契约）。
- `__init__.py` 门面增导出 `translate_condition`。

**rules 改造**（纯迁址 + 委托）：删 `_try_condition`/`_try_comparison`/`_negate_numeric` 三定义（原 rules.py:77-183 整块，连带「条件翻译」节注释）；
顶部增 `from translator.leaf.cond import translate_condition as _try_condition` 别名导回 → `_sk_if` / BEGN-foreach 过滤 / PERFORM-UNTIL 两处 **4 处调用点零改**。依赖单向 `rules → leaf`，无环。`_REL_OPS`（rules.py:70）未迁（非 `_try_condition` 闭包成员，留原处）。

**相3 改造**：`asg/visitor.LeafJavaVisitor` 增 `visit_IfStmt`（`if (cond) { … } [else { … }]`，cond=None → `// TODO-IF: <raw>`，空 then → `// (空)`）、`_body`（递归 visit 子节点 + 一级缩进扁平化）、`visit_Leaf`（未迁动词 → `// TODO-LEAF: <raw>`）；import 增 `translate_condition`。`nodes.py`/`builder.py` **未动**（IfStmt 与 `_lift` 提升步骤17 已就位）。

**比对闸扩 IF**：`scripts/diff_asg_vs_legacy.py` `--verb` 增 IF；新增 `_legacy_ifs`（segmenter 树枚举 `kind=="if"` 跑 `rules._try_condition`）、`_IfCollector`/`_asg_ifs`（遍历 IfStmt 跑 `translate_condition`，`generic_visit` 递归 then/els 捕嵌套 IF）；`main` 按 `_SAMPLERS` 字典分派取样器，比对主干复用。比对单位＝**条件表达式串**（None 也比），按设计 §4.2 不取 body。

**与设计偏差**：无（按 §6 落地）。

**验收（§7 三项，落实为 `test_translation.py` 单测）**：
- `TestLeafCondExtract`（①，7 测）：数值 `==`/`>`、`NOT =`→`!=`、`= SPACES`→`StringUtils.isBlank`、BigDecimal `compareTo(...)==0`、AND 复合 `&&`、88/无关系符→`None`——逐项断言。
- `TestAsgIfVisitor`（②，5 测）：条件行 == `rules._try_condition`（逐字符）、cond=None→`// TODO-IF`、未迁 Leaf→`// TODO-LEAF`、嵌套 IF 缩进递归、else 分支 `} else {`。
- `TestDiffAsgVsLegacyIf`（③）：内联程序（嵌套 IF + AND + NOT）`_legacy_ifs` 与 `_asg_ifs` 条件串逐字符一致。

**回归闸**：`python -m unittest test_translation` → **99 通过 / 2 skip / 0 失败**（旧 86 + 新 13）；
`scripts/regress_config_snapshot.py`（PYTHONIOENCODING=utf-8）exit 0（条件翻译抽取未触碰 config，rules→leaf import 完好）；
`scripts/diff_asg_vs_legacy.py <sample.cob> --verb IF` → `[OK] 4 条 IF 两路逐字符一致` exit 0；`--verb MOVE` 同样 exit 0（MOVE 刀回归未破）。
