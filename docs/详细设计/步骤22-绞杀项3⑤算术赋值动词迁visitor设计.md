# 步骤22　绞杀项3⑤ 算术/赋值动词迁 visitor 设计（rules 逐类迁 visitor·第五刀）

状态：🔶待认可（设计完成，待用户认可后按 §6 落地）

定位：落地 `架构演进-三相分层(预处理-ASG-visitor)初步设计.md` **§5 迁移分期第 3 项「rules 逐类迁 visitor」的第五刀**——
承步骤18（MOVE）/19（IF）/20（PERFORM）/21（CALL）同范式。前四刀已把 MOVE/CALL 升为带类型节点、IF/PERFORM 控制结构迁入 visitor，
`LeafJavaVisitor.visit_Leaf` 仍对**其余叶子动词**落 `// TODO-LEAF` 占位。本刀把 `_dispatch_leaf` 已固化、但 ASG 侧仍占位的
**7 个算术/赋值叶子动词**一次性迁入公用底座 + visit_Leaf 直译，**清零 visit_Leaf 对这 7 类的占位**。

本刀范围（7 个叶子动词，均经 rules `_dispatch_leaf` 固化、均落 ASG `Leaf` 节点）：

| 动词 | rules 函数 | 形态 |
|---|---|---|
| INITIALIZE | `_t_initialize` | 结构体/字段重置（PARAMS→new、数值→0/ZERO、串→""） |
| SET | `_t_set` | `SET a [b] TO value`（数值/字段；TRUE/ON 等交 LLM） |
| ADD | `_t_add` | `ADD a TO b [GIVING c]`（含 BigDecimal `.add`） |
| SUBTRACT | `_t_subtract` | `SUBTRACT a FROM b [GIVING c]`（含 `.subtract`） |
| MULTIPLY | `_t_multiply` | `MULTIPLY a BY b [GIVING c]`（含 `.multiply`） |
| DIVIDE | `_t_divide` | `DIVIDE … INTO/BY … [GIVING][ROUNDED]`（含 `.divide`/RoundingMode） |
| COMPUTE | `_t_compute` | `COMPUTE dst [ROUNDED] = expr`（整型中缀；BigDecimal 交 LLM） |

关联：
- 上位路线图：`架构演进…初步设计.md` §5-项3、§9-Q4（动词顺序 MOVE→IF→PERFORM→CALL→STRING …，本刀切"…"中的算术/赋值类）、§9-Q5（旧/新 diff 脚本）。
- 前序：`步骤21-…CALL迁visitor设计.md` §3（leaf 包结构、`translate_call(tokens,ctx)->(lines,bool)` 范式）、§4.3（诚实比对边界）；`步骤18-…MOVE迁visitor设计.md` §3.2（LeafCtx 契约）。
- 复用对象（只读复用）：`translator/leaf/expr.py`（`_operand`/`_assign`/`_lvalue`/`_is_bigdecimal`/`_is_numeric_field`/`_is_field`/`_bd`/`_struct_prefix`/`_struct_obj`/`_struct_cls` **全在盘**）、`asg.nodes.Leaf`（已含 `tokens`/`raw`，步骤17 就位）、`asg.visitor.LeafJavaVisitor.visit_Leaf`（已有，改为直译）。
- 受改造现状（本步动）：`translator/leaf/`（新建 `arith.py`）、`translator/rules.py`（删 7 定义 + `_arith_val` + 再导入回）、`asg/visitor.py`（`visit_Leaf` 改委托）、`scripts/diff_asg_vs_legacy.py`（加 `--verb ARITH`）。**不动 `nodes.py`/`builder.py`/`context.py`**。

---

## 1. 本步目标与非目标

**目标**：
1. **抽公用**：把 7 个译器 `_t_initialize`/`_t_set`/`_t_add`/`_t_subtract`/`_t_multiply`/`_t_divide`/`_t_compute` + 其私有助手 `_arith_val`
   下沉到新文件 `translator/leaf/arith.py`，逻辑零改；并提供单一门面分派器
   `translate_arith(tokens, ctx) -> tuple[list[str], bool]`——按 `tokens[0]` 路由到 7 个译器之一，非这 7 类 → `([], False)`，
   并**复刻 `_dispatch_leaf` 的 `try/except (ValueError, IndexError)` 兜底**（保证与旧路径同形）。
2. **rules 委托 + 再导入**：rules 顶部 `from translator.leaf.arith import (_t_initialize, _t_set, _t_add, _t_subtract, _t_multiply, _t_divide, _t_compute)`——
   `_dispatch_leaf` 的 7 个调用点（rules.py:1100-1112）**零改**。删除 rules 内 7 定义 + `_arith_val`（`_arith_val` 仅 4 算术译器内部用、随迁，不再导入）。**行为零变化**，旧单测 + `regress_config_snapshot` 零 diff 作硬闸。
3. **相3 visit_Leaf 改委托**：`asg/visitor.LeafJavaVisitor.visit_Leaf` 由「恒占位」改为
   `lines, ok = translate_arith(node.tokens, ctx); return lines if ok else [f"// TODO-LEAF: {node.raw}"]`——
   这 7 类直译，其余叶子动词（STRING/未固化）仍落 `// TODO-LEAF`（行为单调收敛：占位只减不增）。
4. **比对闸扩 ARITH**：`scripts/diff_asg_vs_legacy.py` 加 `--verb ARITH`——枚举每条 7 类语句，比对 `(lines, matched)` 两路逐字符
   （legacy `rules._dispatch_leaf` vs `leaf.translate_arith`，同函数同 ctx → 必然相等）。

**非目标（本步明确不做）**：
- **不升新节点、不改 builder**：这 7 类在 `builder._lift` 已统一落 `Leaf`（含 tokens/raw），visit_Leaf 经单一 `translate_arith` 分派即可
  ——**不为每类新增 InitializeStmt/AddStmt… 节点**（避免 7 个 dataclass + 7 个 _lift 分支 + 7 个 visit_ 的样板膨胀；
  叶子动词的「按 verb 选译器」本是叶子翻译层职责，封装在 `translate_arith` 内部，**非控制流嗅探**，不违背"_lift 唯一嗅探点"原则）。
- **不扩 LeafCtx 契约**：7 译器只读 `field_type_map` + struct 命名字段，**全在契约内**（同 IF/PERFORM 刀，零新字段）。
- **不固化 STRING/UNSTRING/INSPECT**：rules 本无 `_t_string`，这些仍交 LLM（属后续可选「新增固化」，非本刀）。
- **不接入主翻译**；旧 `build_skeleton`→`translate_leaf`→`_dispatch_leaf` 仍是产物正本，ASG visitor 仅供比对自证（下线旧路是 §5-项4）。
- **不改 config 正本**。

---

## 2. 待确认的决定（请认可后按 §6 落地）

- [范围] 本刀切 **7 个算术/赋值叶子动词**（INITIALIZE/SET/ADD/SUBTRACT/MULTIPLY/DIVIDE/COMPUTE）；STRING 等留可选后续。
- [策略] 沿用 A 案「抽公用、两路共调」：`leaf/arith.py` 持 7 译器 + `translate_arith` 分派，rules 委托、visit_Leaf 共调 → `(lines,matched)` 逐字符一致，零 diff。
- [文件] **单文件 `translator/leaf/arith.py`** 承载 7 译器 + `_arith_val` + `translate_arith`（逻辑行 ≈ 140，< 200）。
  "arith" 取**算术与赋值类叶子动词**的统称（含 INITIALIZE/SET 重置/赋值）——三点理由合一刀：① 同 `(tokens)→(lines,bool)` 形态、② 同 `leaf.expr` 底座、③ 同落 `Leaf` 节点。**若你倾向拆 `arith.py`(5算术)+`assign.py`(INITIALIZE/SET)两文件，请指出**（设计可改，dispatch 改为依次试两个译器）。
- [节点] **不动 nodes/builder**——7 类已落 `Leaf`，visit_Leaf 单点委托（本刀与 MOVE/CALL 刀的差异：不新增节点）。
- [visit_Leaf 语义] 由"恒 `// TODO-LEAF`"改为"先试 `translate_arith`、兜不住再占位"——**占位单调收敛**（只减不增）。
- [比对] 比对单位＝`translate_arith(tokens,ctx)` 的 `(lines, matched)`，与 `rules._dispatch_leaf` 逐字符比（含 try/except 兜底同形）。

---

## 3. `translator/leaf/arith.py` 抽取边界（瘦而专，逻辑行 < 200）

### 3.1 抽取依据：7 译器依赖闭包（探查结论，留痕）

7 译器 + `_arith_val` 的下沉依赖**已全部在 `leaf.expr`**（步骤18 已迁）：

```
translate_arith (新门面，按 verb 路由 + try/except 兜底)
 ├─ _t_initialize   _struct_prefix/_struct_obj/_struct_cls/_is_field/_is_bigdecimal/_is_numeric_field/_assign
 ├─ _t_set          _operand/_assign
 ├─ _t_add/_t_subtract/_t_multiply   _is_bigdecimal/_lvalue/_operand/_arith_val
 ├─ _t_divide       _is_bigdecimal/_lvalue/_operand（+ 输出 RoundingMode.HALF_UP 文本）
 ├─ _t_compute      _is_bigdecimal/_lvalue/_operand
 └─ _arith_val      _bd/_is_bigdecimal/re（本子系统私有，4 算术译器共用）
```

ctx 读取字段：仅 `field_type_map` + struct 命名字段——**已全在 `LeafCtx` 契约**（步骤18/21）。
`_arith_val` 与 7 个 `_t_*` **仅被 rules 内部引用**（全仓 grep 确认，无外部/测试直接引用）→ 随迁、`_arith_val` 不外泄门面。
结论：arith.py **零新依赖、零新契约字段**，纯迁址 + 复用 expr 底座。

### 3.2 文件职责与门面

```
translator/leaf/
├── __init__.py     门面：增导出 translate_arith
├── expr.py         (不变，被 arith 复用：operand/assign/lvalue/判型/struct/bd)
├── move.py / cond.py / loop.py / call.py / context.py   (不变)
└── arith.py        ← 新建：translate_arith + 7 译器 + _arith_val（迁自 rules，逻辑零改）
```

依赖方向（单向无环）：`rules → leaf.arith`、`asg.visitor → leaf.arith`、`leaf.arith → leaf.expr`。

- **`arith.py`**：7 译器函数体 + `_arith_val` **原样搬**（ctx 注解 `Ctx → LeafCtx`）；`import re`、`from translator.leaf.expr import (...)`。
  公开 `translate_arith(tokens, ctx)`：
  ```python
  _ARITH = {"INITIALIZE": _t_initialize, "SET": _t_set, "ADD": _t_add,
            "SUBTRACT": _t_subtract, "MULTIPLY": _t_multiply, "DIVIDE": _t_divide, "COMPUTE": _t_compute}
  def translate_arith(tokens, ctx):
      if not tokens:
          return [], False
      fn = _ARITH.get(tokens[0].upper())
      if not fn:
          return [], False
      try:
          return fn(tokens, ctx)
      except (ValueError, IndexError):    # 复刻 rules._dispatch_leaf 兜底
          return [], False
  ```
- **`__init__.py`**：增 `from translator.leaf.arith import translate_arith`，`__all__` 追加。

### 3.3 `rules.py` 改造（纯委托，行为零变化）

- 删除 `_t_initialize`/`_t_set`/`_arith_val`/`_t_add`/`_t_subtract`/`_t_multiply`/`_t_divide`/`_t_compute` 八处定义（rules.py:1120-1300）。
- 顶部增 `from translator.leaf.arith import (_t_initialize, _t_set, _t_add, _t_subtract, _t_multiply, _t_divide, _t_compute)`
  → `_dispatch_leaf` 7 个调用点（:1100-1112）**零改**。`_arith_val` 不再导入（已随 4 算术译器迁入 arith.py 内部）。
- 依赖单向 `rules → leaf`，无环。
- *验证*：旧单测 + `regress_config_snapshot` 零 diff（纯迁址+委托，硬闸）。

---

## 4. 相3 侧改造（visit_Leaf 改委托）

### 4.1 `asg/visitor.py`：`LeafJavaVisitor.visit_Leaf`

```python
def visit_Leaf(self, node) -> list[str]:
    """已迁的算术/赋值叶子动词（步骤22 绞杀项3⑤）直译；其余未迁动词仍诚实占位。

    经公用 translate_arith（与旧 rules._dispatch_leaf 同 7 译器同 ctx → 产物逐字符一致）固化
    INITIALIZE/SET/ADD/SUBTRACT/MULTIPLY/DIVIDE/COMPUTE；兜不住（STRING/未固化/解析失败）→ // TODO-LEAF 占位。
    占位单调收敛（只减不增）：本刀前恒占位，本刀后这 7 类直译、余类不变。"""
    lines, ok = translate_arith(node.tokens, self.ctx)
    return lines if ok else [f"// TODO-LEAF: {node.raw}"]
```

*设计思路*：
- **复刻 `_dispatch_leaf`**：`translate_arith` 与旧路调同 7 译器同 ctx → `(lines, matched)` 逐字符一致；兜底（try/except + 非 7 类 →`([],False)`）同形。
- **占位单调收敛**：visit_Leaf 由恒占位改为"试译再占位"——对这 7 类，IF/PERFORM body 内不再静默落 TODO、而是直译可见；其余动词占位不变。
- **无 verb 嗅探外泄**：visit_Leaf 仅调一个函数，verb 路由封装在 `translate_arith` 内（叶子翻译层职责），visitor 不出现 `if verb==`。

### 4.2 比对边界（honest scope，同前四刀）

本刀迁的是**算术/赋值叶子译器那一层**。比对落在 `translate_arith(tokens, ctx)` 的 `(lines, matched)`：
`rules._dispatch_leaf`（迁后内部即 7 个 leaf 译器）与 `translate_arith` 调**同一 7 译器同一 ctx** → 输出**逐字符必然相等**（含 `([], False)`）。
非这 7 类的叶子（STRING 等）两路同落 `([],False)`/`// TODO-LEAF`，亦相等。

---

## 5. `scripts/diff_asg_vs_legacy.py` 扩 `--verb ARITH`

- **入参**：`--verb {MOVE,IF,PERFORM,CALL,ARITH}`。
- **ARITH 流程**（复用 `_SAMPLERS` 字典分派 + `build_body_ctx` 单份 ctx）：
  - 旧路 `_legacy_arith`：`_walk_segmenter_stmts` 枚举 `kind=="simple"` 且 `tokens[0]∈7` 的 `Stmt`，跑 `rules._dispatch_leaf(toks, ctx)` → `(raw, (lines, matched))`；
  - 新路 `_asg_arith`：`build_asg` → `_ArithCollector(AsgVisitor).visit_Leaf`（filter `tokens[0]∈7`，容器由基类 `generic_visit` 默认递归捕 IF/PERFORM body 内的叶子），跑 `translate_arith(node.tokens, ctx)` → `(raw, (lines, matched))`；
  - 按源码序对齐，逐字符 diff `(lines, matched)`。
- **退出码**：全等 0 / 有差异 1。
- *设计思路*：脚手沿用步骤18-21，`_SAMPLERS["ARITH"]=(_legacy_arith,_asg_arith)`，比对主干不重写（§16 复用）。

---

## 6. 落地步骤（认可后严格按序，每步出产物即验）

1. 建 `translator/leaf/arith.py`：7 译器 + `_arith_val` 原样搬 + `translate_arith` 门面（含 try/except）+ import `leaf.expr`/`re`。改 `__init__.py` 门面增导出。
2. 改 `rules.py`：删 8 定义、加 7 名 import。**跑 `python -m unittest test_translation` + `scripts/regress_config_snapshot.py` → 须全绿/零 diff**（硬闸，先验旧路径无副作用）。
3. `asg/visitor.py`：`visit_Leaf` 改委托 `translate_arith`；import 增 `translate_arith`。跑既有单测须仍绿（**注意**：若既有用例曾断言含算术 body 的 `// TODO-LEAF`，按预期迁移更新为直译值，见 §7）。
4. `scripts/diff_asg_vs_legacy.py`：加 `--verb ARITH` + `_legacy_arith`/`_ArithCollector`/`_asg_arith` + `_SAMPLERS` 项。对样例程序跑，**两路 `(lines,matched)` 逐字符零差异**。
5. 加单测（§7）。全量 `test_translation` 全绿。
6. 回填本设计「实现结果」、更新 `docs/架构索引/项目总览.md`（`leaf/arith.py` + `visit_Leaf` 改委托 + 比对闸 `--verb ARITH`）、写 `docs/操作记录/步骤22-…操作记录.md`（命令/产物/校验/Token 分析）。

---

## 7. 自检与验收

- **旧路径零影响（硬闸）**：`test_translation` 旧用例全绿、`regress_config_snapshot` 零 diff（迁址+委托，行为不变）。
- **visit_Leaf 语义变化的预期更新**：步骤3 后若有「含算术语句的 IF/PERFORM body」既有用例断言 `// TODO-LEAF`，须改断言为直译值——这是**预期迁移**（占位收敛），非回归；须逐一核对、留痕。
- **新增单测**（`test_translation.py`）：
  - ① `TestLeafArithExtract`：`translate_arith` 抽出后，对 `ADD a TO b`（int `+=` / BigDecimal `.add`）、`SUBTRACT`、`MULTIPLY`、`DIVIDE …GIVING`、`COMPUTE`、`INITIALIZE X-PARAMS`/数值字段、`SET a TO n`、`SET a TO TRUE`→`([],False)`、非 7 类动词→`([],False)`——输出与抽取前 `rules._dispatch_leaf` 一致。
  - ② `TestAsgLeafArithVisitor`：含算术/赋值的 `Leaf` 节点 `visit_Leaf` 输出 == `translate_arith`（matched 时逐字符）；未固化动词（如 STRING）→ `// TODO-LEAF`；IF/PERFORM body 内算术直译可见。
  - ③ `TestDiffAsgVsLegacyArith`：内联程序（ADD/SUBTRACT/COMPUTE/INITIALIZE/SET，含嵌套于 IF）`--verb ARITH` 两路 `(lines,matched)` 逐字符一致。
- **不接受**：任何使旧用例/快照变化的副作用（除 §7 预期的 visit_Leaf 占位收敛）；7 类之外动词被改动；引入新节点/builder 改动；block 级被强行比对引入伪差异。

---

## 8. 开放问题（留后续刀）

- **Q1**：STRING/UNSTRING/INSPECT 新增固化（rules 现无 `_t_string`）——可选「扩固化」刀，非迁移。
- **Q2**：EVALUATE（`visit_EvaluateStmt`）、GO TO/CONTINUE/STOP（`GotoJavaVisitor`→`LeafJavaVisitor` 并入 + flow_label 状态机）——控制流刀。
- **Q3**：骨架装配层（PERFORM ②THRU 区间 / CALL ②结构吸收 / ③struct_rebind）——专项「骨架迁 visitor」刀。
- **Q4**：全动词 + 骨架迁完后，`_dispatch_leaf` 可整体下沉 leaf 成 `translate_leaf_stmt` 唯一入口，rules 仅委托；随 §5-项4 下线旧 token 通道统一回归。

---

## 9. 实现结果（落地后回填）

（待 §6 落地后补：公用包 / rules 改造 / 相3 visit_Leaf 改委托 / 比对闸扩 ARITH / 与设计偏差 / 验收回归闸。）
