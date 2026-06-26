# 步骤20　绞杀项3③ PERFORM 循环子句迁 visitor 设计（rules 逐类迁 visitor·第三刀）

状态：🟢已实现（2026-06-26 认可 + 落地，§9 回填）

定位：落地 `架构演进-三相分层(预处理-ASG-visitor)初步设计.md` **§5 迁移分期第 3 项「rules 逐类迁 visitor」的第三刀**——
动词顺序 MOVE → IF → **PERFORM** → CALL → STRING，承步骤18（MOVE）/19（IF）同范式。
经范围决策（PERFORM 三关注点见下表）：**本刀只切「① 循环子句翻译」**——纯函数、可零 diff 抽公用、镜像 MOVE/IF。

PERFORM 子系统三关注点（本刀只切①）：

| 关注点 | rules 函数 | 对 LeafCtx 依赖 | 本刀 |
|---|---|---|---|
| ① 循环子句翻译 | `_perform_loop`/`_has_test_after`/`_parse_varying_clauses` | **纯**（`_operand`/`translate_condition`/`_ind`，全在 leaf） | ✅ 切 |
| ② THRU 区间 + 目标解析（步骤12-15） | `_perform_range`/`_perform_range_paragraph`/`_perform_single_paragraph` | 读写 `proc_order`/`section_order`/`pending_range_methods`/`section_to_method`（骨架态，**不在 LeafCtx**） | ❌ 留后 |
| ③ BEGN foreach + struct_rebind（步骤18 §8-Q1） | `_render_begn_foreach`/`_tag_rebind`/`_match_begn_*` | 混 IO 映射 + 骨架递归 + 叶子重绑定标记 | ❌ 留后 |

关联：
- 上位路线图：`架构演进…初步设计.md` §5-项3、§9-Q4（动词顺序）、§9-Q5（旧/新 diff 脚本）。
- 前序：`步骤18-…MOVE迁visitor设计.md` §3（leaf 包结构）、§8-Q1（struct_rebind 随 PERFORM/loop 刀——本刀**只切循环子句、重绑定仍留③**，见 §1 非目标）；`步骤19-…IF迁visitor设计.md` §3.3（cond 委托范式）、§4.2（诚实比对边界）。
- 复用对象（只读复用）：`translator/leaf/expr.py`（`_operand`）、`translator/leaf/cond.py`（`translate_condition`，已在盘）、`asg/builder._lift_perform`（PerformStmt 提升 + target/thru/inline_body **已就位**）、`asg/visitor.AsgVisitor`。
- 受改造现状（本步动）：`translator/rules.py`（抽出 `_perform_loop` 三件套 + 改委托）、`asg/visitor.py`（加 `visit_PerformStmt`）、`scripts/diff_asg_vs_legacy.py`（加 `--verb PERFORM`）。

---

## 1. 本步目标与非目标

**目标**：
1. **抽公用**：把 rules 的循环子句翻译 `_perform_loop` + `_has_test_after` + `_parse_varying_clauses` 下沉到新文件
   `translator/leaf/loop.py`，对外名 `translate_perform_loop(header, ctx, indent) -> tuple[list[str], list[str]] | None`
   （`([], [])`＝无循环、`None`＝兜不住落 LLM、否则 `(open_lines, close_lines)`）。复用 `leaf.expr`/`leaf.cond` 底座。
2. **rules 委托**：rules 顶部 `from translator.leaf.loop import _perform_loop`（保旧名，`_sk_perform` 调用点零改），
   删除 rules 内三函数定义。**行为零变化**，旧单测 + `regress_config_snapshot` 零 diff 作硬闸。
3. **相3 visit_PerformStmt**：`asg/visitor.LeafJavaVisitor` 加 `visit_PerformStmt`——经 `translate_perform_loop` 渲染循环壳
   （while/for/do-while/嵌套 for），递归 `inline_body`，复刻 `_sk_perform` 的 `loop is None → 整条交 LLM` 兜底。
4. **比对闸扩 PERFORM**：`scripts/diff_asg_vs_legacy.py` 加 `--verb PERFORM`——枚举每条 PERFORM，比对**循环壳 (open, close)**
   两路逐字符（legacy `_perform_loop` vs `translate_perform_loop`，同函数同 ctx → 必然相等）。

**非目标（本步明确不做）**：
- **不切 ②THRU 区间 / 目标解析**：`_perform_range`/`_perform_range_paragraph`/`_perform_single_paragraph` 及其
  `pending_range_methods`/`proc_order`/`section_to_method` 依赖**全留 rules**（骨架装配层，超出 LeafCtx）。
  visit_PerformStmt 对 out-of-line（无 inline_body 仅 target）落 `// TODO-PERFORM-CALL: <target>[ THRU <thru>]` 占位，**不复刻区间合成**。
- **不切 ③BEGN foreach / struct_rebind**：步骤18 §8-Q1 的循环内结构体重绑定仍留 rules（与 IO 查表耦合）。
- **不做 block 级比对**：PERFORM body（inline_body）旧路占位 vs 新路直译本就不等（渐进迁移预期态），比对**只在循环壳边界**
  （同 IF 刀 §4.2；body 完整一致待全动词迁完，§5-项4）。
- **不接入主翻译**；**不改 config 正本**；**不改 `nodes.py`/`builder.py`**（PerformStmt 与 `_lift_perform` 步骤17 已就位）。

---

## 2. 待确认的决定（请认可后按 §6 落地）

- [范围] 本刀**只切①循环子句翻译**（用户经 AskUserQuestion 选定）；②③留后续「骨架装配迁 visitor」刀。
- [策略] 沿用 A 案「抽公用、两路共调」：`leaf/loop.py` 持 `translate_perform_loop`，rules 委托、visit_PerformStmt 共调 → 循环壳产物逐字符一致，零 diff。
- [文件] 循环子句归入 **`translator/leaf/loop.py`**（与 `move.py`/`cond.py` 并列；loop 是「循环子句→Java 循环壳」层，复用 cond/expr）。
- [委托] rules 用 `from ... import _perform_loop`（原名），`_sk_perform` 调用点零改；`_has_test_after`/`_parse_varying_clauses` 为子系统私有，随迁、不外泄门面。
- [节点] PerformStmt 已有（target/thru/header/inline_body），`_lift_perform` 提升已就位，**不动 nodes/builder**。
- [范围-壳] visit_PerformStmt 复刻循环壳 + loop=None 兜底；inline_body 递归直译已迁动词、未迁落占位；out-of-line 目标落 `// TODO-PERFORM-CALL` 占位；比对只在循环壳边界。

---

## 3. `translator/leaf/loop.py` 抽取边界（瘦而专，逻辑行 < 200）

### 3.1 抽取依据：`_perform_loop` 依赖闭包（探查结论，留痕）

`rules._perform_loop`（rules.py:1029）→ `_has_test_after`（:1002）+ `_parse_varying_clauses`（:1007）三者构成循环子句子系统，
其下沉依赖**已全部在 leaf**：

```
translate_perform_loop (_perform_loop)       VARYING→嵌套 for / UNTIL→while / TEST AFTER→do-while / TIMES→for
 ├─ _has_test_after                          纯 token 扫描（TEST 紧跟 AFTER）
 ├─ _parse_varying_clauses                    VARYING…AFTER 切子句 [(v,a,b,cond)]
 │   ├─ _operand                              (leaf.expr) FROM/BY 值、循环变量
 │   └─ translate_condition (_try_condition)  (leaf.cond) UNTIL 条件
 ├─ _operand / translate_condition            (leaf.expr/cond) UNTIL/TIMES 条件与计数
 └─ _ind                                       缩进（trivial，loop.py 本地定义）
```

ctx 读取：仅 `field_type_map`（经 `_operand`/`translate_condition`，已在 `LeafCtx` 契约）。**零新依赖、零新契约字段**。

### 3.2 文件职责与门面

```
translator/leaf/
├── __init__.py     门面：增导出 translate_perform_loop
├── expr.py         (不变，被 loop 复用：_operand)
├── cond.py         (不变，被 loop 复用：translate_condition)
├── move.py / context.py  (不变)
└── loop.py         ← 新建：translate_perform_loop + _perform_loop + _has_test_after + _parse_varying_clauses + _ind
```

依赖方向（单向无环）：`rules → leaf.loop`、`asg.visitor → leaf.loop`、`leaf.loop → leaf.expr`、`leaf.loop → leaf.cond`。

- **`loop.py`**：`_perform_loop(header, hu, ctx, indent)`＋`_has_test_after(hu)`＋`_parse_varying_clauses(header, hu, ctx)`
  **原样搬**（逻辑零改，ctx 注解 `Ctx → LeafCtx`）；本地 `_ind(n)='    '*n`；
  公开 `translate_perform_loop(header, ctx, indent)`＝计算 `hu=[h.upper() for h in header]` 后调 `_perform_loop`（薄壳，便于 visitor/比对免传 hu）。
  import：`from translator.leaf.expr import _operand`、`from translator.leaf.cond import translate_condition as _try_condition`。
- **`__init__.py`**：增 `from translator.leaf.loop import translate_perform_loop`，`__all__` 追加。

### 3.3 `rules.py` 改造（纯委托，行为零变化）

- 删除 `_has_test_after`（:1002-1004）、`_parse_varying_clauses`（:1007-1026）、`_perform_loop`（:1029-1055）三定义。
- 顶部增 `from translator.leaf.loop import _perform_loop` → `_sk_perform`（:1066）的 `_perform_loop(header, hu, ctx, indent)` **零改**。
- `Ctx` 留 rules（天然满足 LeafCtx）。依赖单向 `rules → leaf`，无环。
- *验证*：旧单测 + `regress_config_snapshot` 零 diff（纯迁址+委托，硬闸）。

---

## 4. 相3 侧改造（visit_PerformStmt 循环壳渲染）

### 4.1 `asg/visitor.py`：`LeafJavaVisitor.visit_PerformStmt`

```python
def visit_PerformStmt(self, node) -> list[str]:
    """复刻 rules._sk_perform 的循环壳：经 translate_perform_loop 渲染 while/for/do-while/嵌套 for；
    loop is None → 整条交 LLM（// TODO-PERFORM 占位）。
    inline_body 递归直译已迁动词（MOVE/IF/嵌套 PERFORM），未迁落 visit_Leaf 占位；
    out-of-line（仅 target、无 inline_body）落 // TODO-PERFORM-CALL 占位——区间/目标解析属②，留后续刀（设计 §1 非目标）。
    比对只在循环壳边界（§4.2），body/目标占位不比。"""
    loop = translate_perform_loop(node.header, self.ctx, 0)
    if loop is None:
        return [f"// TODO-PERFORM: {node.raw}"]
    open_lines, close_lines = loop
    if node.inline_body:
        body = self._body(node.inline_body)
    elif node.target:
        thru = f" THRU {node.thru.name}" if node.thru else ""
        body = [f"// TODO-PERFORM-CALL: {node.target.name}{thru}"]
    else:
        return [f"// TODO-PERFORM: {node.raw}"]
    return (open_lines + body + close_lines) if open_lines else body
```

*设计思路*：
- **循环壳复刻 `_sk_perform`**：`translate_perform_loop` 与旧 `_perform_loop` 同函数同 ctx → open/close 行逐字符一致；
  `loop is None` 兜底与 `_sk_perform`（:1067-1068 整条 `ctx.new_leaf`）形状对齐（visitor 侧 → `// TODO-PERFORM`）。
- **body 仅直译已迁动词**：复用步骤19 的 `_body`（递归 + 一级缩进）；未迁动词 `visit_Leaf` 占位。
  注：VARYING 多层 open 时旧路 body 进最内层（`indent+len(open)`），visitor `_body` 单级缩进——**body 缩进非比对项**（block 级保真待全迁，§4.2），不影响循环壳一致性。
- **out-of-line 目标**：②THRU/区间属骨架装配层，本刀落 `// TODO-PERFORM-CALL` 占位（诚实呈现绞杀进度，不臆造方法名）。

### 4.2 比对边界（honest scope，同 IF 刀）

本刀迁的是**循环子句翻译那一层**。比对落在 PERFORM 的**循环壳 `(open_lines, close_lines)`**：
`rules._perform_loop` 与 `translate_perform_loop` 同函数同 ctx → 逐字符必然相等（含 `None`/`([],[])` 三态）。

**body / 目标占位不比对**：inline_body 旧路占位 vs 新路直译、out-of-line 目标旧路区间合成 vs 新路 TODO 占位——本就不等（渐进迁移预期态）。
block 级一致须待②③及全动词迁完（§5-项4），故本刀比对脚本对 PERFORM **只取循环壳**。

---

## 5. `scripts/diff_asg_vs_legacy.py` 扩 `--verb PERFORM`

- **入参**：`--verb {MOVE,IF,PERFORM}`。
- **PERFORM 流程**（复用 §_SAMPLERS 字典分派 + `build_body_ctx` 单份 ctx）：
  - 旧路：`_walk_segmenter_stmts` 枚举 `kind=="perform"` 的 `Stmt`，跑 `rules._perform_loop(header, hu, ctx, 0)` → `(raw, loop)`；
  - 新路：`build_asg` → 遍历 `PerformStmt`（新增 `_PerformCollector.visit_PerformStmt`，`generic_visit` 递归 inline_body 捕嵌套 PERFORM），跑 `translate_perform_loop(header, ctx, 0)` → `(raw, loop)`；
  - 按源码序对齐，逐字符 diff 循环壳（`None`/`([],[])` 也比）。
- **退出码**：全等 0 / 有差异 1。
- *设计思路*：脚手沿用步骤18/19，`_SAMPLERS["PERFORM"]=(_legacy_performs,_asg_performs)`，比对主干不重写（§16 复用）。

---

## 6. 落地步骤（认可后严格按序，每步出产物即验）

1. 建 `translator/leaf/loop.py`：三函数原样搬 + `translate_perform_loop` 薄壳 + `_ind`。改 `__init__.py` 门面增导出。
2. 改 `rules.py`：删三定义、加 `_perform_loop` import。**跑 `python -m unittest test_translation` + `regress_config_snapshot.py` → 须全绿/零 diff**（硬闸）。
3. `asg/visitor.py`：`LeafJavaVisitor` 加 `visit_PerformStmt`；import 增 `translate_perform_loop`。跑既有单测须仍绿（不破 MOVE/IF 比对）。
4. `scripts/diff_asg_vs_legacy.py`：加 `--verb PERFORM` + `_legacy_performs`/`_PerformCollector`/`_asg_performs` + `_SAMPLERS` 项。对样例程序跑，**循环壳两路逐字符零差异**。
5. 加单测（§7）。全量 `test_translation` 全绿。
6. 回填本设计「实现结果」、更新 `docs/架构索引/项目总览.md`（`leaf/loop.py` + `visit_PerformStmt` + 比对闸 `--verb PERFORM`）、写 `docs/操作记录/步骤20-…操作记录.md`（命令/产物/校验/Token 分析）。

---

## 7. 自检与验收

- **旧路径零影响（硬闸）**：`test_translation` 旧用例全绿、`regress_config_snapshot` 零 diff。
- **新增单测**（`test_translation.py`）：
  - ① `TestLeafLoopExtract`：`translate_perform_loop` 对 `UNTIL`→while、`UNTIL`+`TEST AFTER`→do-while、`TIMES`→for、
    `VARYING…`→for、`VARYING…AFTER…`→嵌套 for、无循环→`([],[])`、UNTIL 条件兜不住→`None`——逐项断言 open/close。
  - ② `TestAsgPerformVisitor`：含 PERFORM 的节点 `visit_PerformStmt` 循环壳 == `_perform_loop`（逐字符）；
    inline_body 内 MOVE 直译；out-of-line 目标 → `// TODO-PERFORM-CALL`；loop=None → `// TODO-PERFORM`。
  - ③ `TestDiffAsgVsLegacyPerform`：内联程序（UNTIL/TIMES/VARYING 多形）`--verb PERFORM` 两路循环壳逐字符一致。
- **不接受**：任何使旧用例/快照变化的副作用；PERFORM 之外动词被改动；②③被半迁；block 级被强行比对引入伪差异。

---

## 8. 开放问题（留后续刀）

- **Q1**：②THRU 区间 / 目标解析（`pending_range_methods`/`proc_order`）迁 visitor——需先把「骨架装配层」迁入相3（ASG 已有 target/thru/registry，可在 visitor 重建合成方法登记），属后续「骨架迁 visitor」刀。
- **Q2**：③BEGN foreach + struct_rebind（步骤18 §8-Q1）——与 IO 查表耦合，随 IO/CALL 刀或专项重绑定刀。
- **Q3**：visit_PerformStmt body 多层缩进保真（VARYING 嵌套 body 进最内层）——随②/block 级落地统一。
- **Q4**：旧/新 block 级一致何时可断言——全动词 + ②③迁完、§5-项4 下线旧 token 通道时。

---

## 9. 实现结果（回填，2026-06-26）

**公用包**（`translator/leaf/loop.py`，逻辑行 < 200）：
- `_perform_loop(header, hu, ctx, indent)`+`_has_test_after(hu)`+`_parse_varying_clauses(header, hu, ctx)` 迁自 rules，逻辑零改；本地 `_ind`。
- `translate_perform_loop(header, ctx, indent)` 薄壳：算 `hu` 后调 `_perform_loop`（visitor/比对免传 hu）。
- import `leaf.expr._operand`、`leaf.cond.translate_condition as _try_condition`。**零新依赖、零新契约字段**（仅 `field_type_map`，已在 LeafCtx）。
- `__init__.py` 门面增导出 `translate_perform_loop`。

**rules 改造**（纯迁址 + 委托）：删 `_has_test_after`/`_parse_varying_clauses`/`_perform_loop` 三定义；
顶部增 `from translator.leaf.loop import _perform_loop`（原名导回）→ `_sk_perform` 的 `_perform_loop(header, hu, ctx, indent)` **零改**。依赖单向 `rules → leaf`，无环。

**相3 改造**：`asg/visitor.LeafJavaVisitor` 增 `visit_PerformStmt`——`translate_perform_loop` 渲染循环壳、`loop is None → // TODO-PERFORM`、
inline_body 经 `_body` 递归直译（未迁落 `visit_Leaf`）、out-of-line 仅 target → `// TODO-PERFORM-CALL: <target>[ THRU <thru>]`；import 增 `translate_perform_loop`。`nodes.py`/`builder.py` **未动**（PerformStmt 与 `_lift_perform` 步骤17 已就位）。

**比对闸扩 PERFORM**：`scripts/diff_asg_vs_legacy.py` `--verb` 增 PERFORM；新增 `_legacy_performs`（segmenter 枚举 `kind=="perform"` 跑 `rules._perform_loop(...,0)`）、`_PerformCollector`/`_asg_performs`（遍历 PerformStmt 跑 `translate_perform_loop(...,0)`，`generic_visit` 递归 inline_body 捕嵌套）；`_SAMPLERS` 增项。比对单位＝**循环壳 (open, close)**（`None`/`([],[])` 也比），按 §4.2 不取 body/目标。

**与设计偏差**：无（按 §6 落地）。

**验收（§7 三项，落实为 `test_translation.py` 单测）**：
- `TestLeafLoopExtract`（①，8 测）：UNTIL→while、TEST AFTER→do-while、TIMES→for、VARYING→for、VARYING AFTER→嵌套 for（含缩进）、无循环→`([],[])`、UNTIL 兜不住→`None`、VARYING+TEST AFTER→`None`。
- `TestAsgPerformVisitor`（②，4 测）：循环壳首/尾行 == `rules._perform_loop`、inline MOVE 直译、out-of-line target/THRU → `// TODO-PERFORM-CALL`、loop=None → `// TODO-PERFORM`。
- `TestDiffAsgVsLegacyPerform`（③）：内联程序（UNTIL/TIMES/VARYING AFTER/out-of-line）两路循环壳逐字符一致。

**回归闸**：`python -m unittest test_translation` → **112 通过 / 2 skip / 0 失败**（旧 99 + 新 13）；
`scripts/regress_config_snapshot.py`（PYTHONIOENCODING=utf-8）exit 0（循环子句抽取未触碰 config）；
`scripts/diff_asg_vs_legacy.py <sample.cob> --verb PERFORM` → `[OK] 4 条 PERFORM 两路逐字符一致` exit 0；`--verb IF`/`--verb MOVE` 同样 exit 0（前两刀回归未破）。
