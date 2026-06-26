# 步骤21　绞杀项3④ CALL 动词迁 visitor 设计（rules 逐类迁 visitor·第四刀）

状态：🟢已实现（2026-06-26 认可 + 落地，§9 回填）

定位：落地 `架构演进-三相分层(预处理-ASG-visitor)初步设计.md` **§5 迁移分期第 3 项「rules 逐类迁 visitor」的第四刀**——
动词顺序 MOVE → IF → PERFORM → **CALL** → STRING，承步骤18（MOVE）/19（IF）/20（PERFORM）同范式。
经范围决策（CALL 子系统三关注点见下表）：**本刀只切「① 散点 CALL 兜底翻译」**（`_t_call`）——纯函数、可零 diff 抽公用、镜像 MOVE/IF/PERFORM。

CALL 子系统三关注点（本刀只切①）：

| 关注点 | rules 函数 | 对 LeafCtx 依赖 | 本刀 |
|---|---|---|---|
| ① 散点 CALL 兜底翻译 | `_t_call` + `resolve_io_info`/`derive_io_info` | `io_programs`/`io_default_pattern`/`date_programs`/`system_programs`（**LeafCtx 待扩**）+ `struct_function`（已在契约）+ `_struct_obj`（已在 leaf.expr） | ✅ 切 |
| ② setup+CALL+IF 结构吸收（步骤10/11） | `_match_begn_single`/`_match_readr_single`/`_match_write_single`/`_render_*` | 读写 `struct_function`/`io_struct_prefixes` + 多语句窗口扫描（骨架装配层，超 LeafCtx 单语句口径） | ❌ 留后 |
| ③ struct_rebind / BEGN foreach（步骤18 §8-Q1） | `_render_begn_foreach`/`_tag_rebind` | 混 IO 映射 + 骨架递归 + 叶子重绑定标记 | ❌ 留后 |

关联：
- 上位路线图：`架构演进…初步设计.md` §5-项3、§9-Q4（动词顺序）、§9-Q5（旧/新 diff 脚本）。
- 前序：`步骤18-…MOVE迁visitor设计.md` §3（leaf 包结构、`translate_move(tokens,ctx)->(lines,bool)` 范式）、§3.2（LeafCtx 契约）；
  `步骤19-…IF迁visitor设计.md` §4.2（诚实比对边界）；`步骤20-…PERFORM循环子句迁visitor设计.md` §1（②③留后的诚实分期范式）、§4.2。
- 复用对象（只读复用）：`translator/leaf/expr.py`（`_struct_obj` 已在盘）、`asg/builder._lift`（CallStmt 提升**已就位**，本刀仅给节点补 `tokens`）、`asg/visitor.LeafJavaVisitor`。
- 受改造现状（本步动）：`translator/leaf/`（新建 `call.py`）、`translator/leaf/context.py`（LeafCtx 扩 4 字段）、`translator/rules.py`（删 `_t_call`/`resolve_io_info`/`derive_io_info` 定义 + 别名/再导入回）、`asg/nodes.py`（CallStmt 加 `tokens`）、`asg/builder.py`（`_lift` 填 `tokens`）、`asg/visitor.py`（加 `visit_CallStmt`）、`scripts/diff_asg_vs_legacy.py`（加 `--verb CALL`）。

---

## 1. 本步目标与非目标

**目标**：
1. **抽公用**：把 rules 的散点 CALL 兜底翻译 `_t_call` + 其私有依赖 `resolve_io_info` / `derive_io_info` 下沉到新文件
   `translator/leaf/call.py`，对外名 `translate_call(tokens, ctx) -> tuple[list[str], bool]`（与 `translate_move` 同签名）。
   复用 `leaf.expr._struct_obj`。`resolve_io_info`/`derive_io_info` 一并迁（IO 映射解析底座，被 ② 结构吸收等多处复用）。
2. **rules 委托 + 再导入**：rules 顶部
   `from translator.leaf.call import translate_call as _t_call, resolve_io_info, derive_io_info`——
   - `_dispatch_leaf` 的 `_t_call(toks, ctx)` 调用点（rules.py:1110）**零改**；
   - 结构吸收 4 处 `resolve_io_info(...)`（rules.py:277/374/570/706）**零改**；
   - **公开面零变化**：`rules.resolve_io_info`/`rules.derive_io_info` 被 graph/nodes.py、main.py、translator/context.py、
     translator/skeleton.py、scripts/regress_config_snapshot.py 以 `rules.resolve_io_info` 引用——再导入后仍是 rules 模块属性，全部照常解析。
   删除 rules 内三定义。**行为零变化**，旧单测 + `regress_config_snapshot` 零 diff 作硬闸。
3. **扩 LeafCtx 契约**：`translator/leaf/context.py` 的 `LeafCtx` Protocol 增 4 字段
   `io_programs` / `io_default_pattern` / `date_programs` / `system_programs`（本刀首次扩契约；MOVE 刀已含 `struct_function` 及 struct 命名字段）。
   `rules.Ctx` 与 `build_body_ctx` 产物**均已有这 4 字段**（rules.py:60-63、body_context.py:79-80）→ duck-type 自动满足，**两路 ctx 无需改造**。
4. **节点补 token**：`asg.nodes.CallStmt` 加 `tokens: list[str]` 字段，`asg.builder._lift` 填 `tokens=list(st.tokens)`。
   *理由*：`translate_call` 吃原始 token 串（自行解析 USING/参数），镜像 `MoveStmt.tokens` 口径；
   CallStmt 现仅存 name/using（GO-TO demo 期为别的用途建），无消费者，补 tokens 是最小且必要的节点增益（**本刀与前三刀的唯一节点差异**，§2 列为待确认）。
5. **相3 visit_CallStmt**：`asg/visitor.LeafJavaVisitor` 加 `visit_CallStmt`——经 `translate_call(node.tokens, ctx)` 直译，
   `matched=False` → `// TODO-CALL: <raw>` 占位（body 诚实可见，复刻散点 CALL 兜不住→交 LLM 的形状）。
6. **比对闸扩 CALL**：`scripts/diff_asg_vs_legacy.py` 加 `--verb CALL`——枚举每条 CALL，比对 `translate_call(tokens, ctx)` 输出
   `(lines, matched)` 两路逐字符（legacy `rules._t_call` vs `leaf.call.translate_call`，同函数同 ctx → 必然相等）。

**非目标（本步明确不做）**：
- **不切 ② setup+CALL+IF 结构吸收**：`_match_begn_single`/`_match_readr_single`/`_match_write_single` 及其
  `_render_*`、`_rewrite_begn_loops` 编排**全留 rules**（多语句窗口扫描 + struct_function 时序写入，属骨架装配层，超 LeafCtx 单语句口径）。
- **不切 ③ struct_rebind / BEGN foreach**（步骤18 §8-Q1）：与 IO 查表 + 骨架递归耦合，留专项重绑定刀。
- **不复刻 struct_function 的时序填充**：真实管线里 `MOVE … TO X-FUNCTION` 顺序执行先写 `ctx.struct_function`，CALL 才命中固化方法；
  visit_CallStmt / 比对闸**不重放**该 MOVE 序列（见 §4.2 诚实边界——两路同 ctx 同 struct_function 态 → 输出必然相等，比对仍成立）。
- **不接入主翻译**；旧 `build_skeleton`→`translate_leaf`→`_t_call` 仍是产物正本，ASG visitor 仅供比对自证（下线旧路是 §5-项4）。
- **不改 config 正本**；不动 `io_mappings.yaml` / `spec_loader`。

---

## 2. 待确认的决定（请认可后按 §6 落地）

- [范围] 本刀**只切① 散点 CALL 兜底翻译** `_t_call`；②结构吸收、③struct_rebind 留后续「骨架装配 / IO 结构吸收迁 visitor」刀。
- [策略] 沿用 A 案「抽公用、两路共调」：`leaf/call.py` 持 `translate_call`，rules 委托、visit_CallStmt 共调 → `(lines, matched)` 逐字符一致，零 diff。
- [文件] CALL 兜底翻译归入 **`translator/leaf/call.py`**（与 move/cond/loop 并列）；`resolve_io_info`/`derive_io_info` 随迁入同文件
  （IO 映射解析底座，rules 结构吸收再导入复用，依赖单向 rules → leaf，无环）。
- [契约] **LeafCtx 扩 4 字段**（io_programs/io_default_pattern/date_programs/system_programs）——本刀首次扩契约；两路 ctx 已具备，零改造。
- [节点] **CallStmt 加 `tokens` 字段、`_lift` 填充**——本刀**须动 nodes.py/builder.py**（与前三刀「不动 nodes/builder」不同；
  IF/PERFORM 所需 cond/header 当时已在节点，CALL 所需原始 token 串则缺，故必须补，且为最小增益）。
- [委托] rules 用 `translate_call as _t_call` 别名 + `resolve_io_info`/`derive_io_info` 再导入，5+ 处调用点 / 外部引用零改。
- [范围-占位] visit_CallStmt：`matched=False → // TODO-CALL: <raw>`；比对只在 `translate_call` 纯函数输出边界（§4.2）。

---

## 3. `translator/leaf/call.py` 抽取边界（瘦而专，逻辑行 < 200）

### 3.1 抽取依据：`_t_call` 依赖闭包（探查结论，留痕）

`rules._t_call`（rules.py:1164）的下沉依赖：

```
translate_call (_t_call)                     CALL 'xxxIO'/日期/系统子程序 → 固化 Java；兜不住 → ([],False)
 ├─ resolve_io_info(name, io_programs, pat)   IO 映射解析：派生范式做基底 + io_programs 显式条目深合并
 │   └─ derive_io_info(name, pat)             *IO 命名范式派生（base→PascalCase/camelCase + 操作码）
 ├─ _struct_obj(prefix, ctx)                  (leaf.expr，已在盘) 前缀 → Java 对象名
 └─ re.sub                                    {entity} 占位替换为对象名
```

ctx 读取字段：`io_programs` / `io_default_pattern` / `date_programs` / `system_programs`（**LeafCtx 待扩**）、
`struct_function`（已在契约）、struct 命名字段（经 `_struct_obj`，已在契约）。

`resolve_io_info`/`derive_io_info` 为**纯函数**（仅吃 name + 两个 dict，不碰 ctx 其它态），且被 ② 结构吸收（rules.py:277/374/570/706）
与外部模块（graph/nodes、main、context、skeleton、regress）复用 → 随 `_t_call` 一并迁入 call.py，rules 再导入回（保 `rules.*` 公开面）。

### 3.2 文件职责与门面

```
translator/leaf/
├── __init__.py     门面：增导出 translate_call
├── context.py      LeafCtx 契约 ← 扩 io_programs/io_default_pattern/date_programs/system_programs
├── expr.py         (不变，被 call 复用：_struct_obj)
├── move.py / cond.py / loop.py   (不变)
└── call.py         ← 新建：translate_call + resolve_io_info + derive_io_info（迁自 rules，逻辑零改）
```

依赖方向（单向无环）：`rules → leaf.call`、`asg.visitor → leaf.call`、`leaf.call → leaf.expr`、`leaf.call → leaf.context`。

- **`call.py`**：`translate_call(tokens, ctx) -> tuple[list[str], bool]` ＝ `_t_call` 函数体**原样搬**（ctx 注解 `Ctx → LeafCtx`）；
  `resolve_io_info`、`derive_io_info` 一并搬（逻辑零改）。`import re`、`from translator.leaf.expr import _struct_obj`。
- **`context.py`**：`LeafCtx` Protocol 增 4 字段声明（注释同 rules.Ctx）。
- **`__init__.py`**：增 `from translator.leaf.call import translate_call`，`__all__` 追加。

### 3.3 `rules.py` 改造（纯委托 + 再导入，行为零变化）

- 删除 `_t_call`（:1164-1225）、`resolve_io_info`（:1143-1161）、`derive_io_info`（:1116-1140）三定义。
- 顶部增 `from translator.leaf.call import translate_call as _t_call, resolve_io_info, derive_io_info`：
  - `_dispatch_leaf` 的 `_t_call(toks, ctx)`（:1110）零改；
  - 结构吸收 `resolve_io_info(...)`（:277/374/570/706）零改；
  - `rules.resolve_io_info`/`rules.derive_io_info` 公开面经再导入保留（外部 5 处引用零改）。
- `Ctx` 留 rules（已含 4 字段，天然满足扩后 LeafCtx）。依赖单向 `rules → leaf`，无环。
- *验证*：旧单测 + `regress_config_snapshot`（含 `resolve_io_info` 快照）零 diff（纯迁址+委托，硬闸）。

---

## 4. 相3 侧改造（节点补 token + visit_CallStmt）

### 4.1 `asg/nodes.py` + `asg/builder.py`

- `CallStmt` 增 `tokens: list[str] = field(default_factory=list)`（name/using/raw/lineno 保留）。
- `builder._lift` 的 CALL 分支：`return nodes.CallStmt(name=name, using=using, tokens=list(st.tokens), raw=st.raw)`。

### 4.2 `asg/visitor.py`：`LeafJavaVisitor.visit_CallStmt`

```python
def visit_CallStmt(self, node) -> list[str]:
    """复刻 rules 散点 CALL 兜底（步骤21 绞杀项3④·只切① _t_call）：
    经公用 translate_call（与旧 _t_call 同函数同 ctx → 产物逐字符一致）直译固化 CALL；
    matched=False（游标/非IO/未映射，或 struct_function 未命中功能码）→ // TODO-CALL 占位，body 诚实可见。
    ②setup+CALL+IF 结构吸收 / ③struct_rebind 属骨架装配层，留后续刀（设计 §1 非目标）；
    比对只在 translate_call 纯函数边界（设计 §4.2），不重放 struct_function 时序。"""
    lines, matched = translate_call(node.tokens, self.ctx)
    return lines if matched else [f"// TODO-CALL: {node.raw}"]
```

*设计思路*：
- **复刻 `_t_call`**：`translate_call` 与旧 `_t_call` 同函数同 ctx → `(lines, matched)` 逐字符一致。
- **未命中占位**：散点 CALL 大量未命中（非 IO 子程序、游标、struct_function 未设功能码）→ `// TODO-CALL`，
  使 IF/PERFORM body 内的 CALL 不被静默吞行（同 `visit_Leaf` 诚实占位口径）。
- **不重放 struct_function**：真实固化（如 `obj = repo.save(obj)`）依赖前序 `MOVE … TO X-FUNCTION` 写 `struct_function`——
  此为 ② 结构吸收/时序层，本刀不复刻；比对两路同 ctx（同 struct_function 态）→ 输出仍必然相等。

### 4.3 比对边界（honest scope，同 PERFORM 刀）

本刀迁的是**散点 CALL 兜底翻译那一层**。比对落在 `translate_call(tokens, ctx)` 的 `(lines, matched)`：
`rules._t_call`（迁后即 `translate_call`）与 `translate_call` 调**同一函数同一 ctx** → 输出**逐字符必然相等**（含 `([], False)`）。

**不验证 IO 固化语义**：固化结果（findBy/save 等）取决于 `struct_function` 的时序填充与 ② 结构吸收——本刀不重放、不比对该路径，
仅断言「`_lift` 提升 + ctx 装配」未漂移 CALL 翻译（同 MOVE/IF/PERFORM 刀的诚实边界范式）。block 级一致待 ②③及全动词迁完（§5-项4）。

---

## 5. `scripts/diff_asg_vs_legacy.py` 扩 `--verb CALL`

- **入参**：`--verb {MOVE,IF,PERFORM,CALL}`。
- **CALL 流程**（复用 `_SAMPLERS` 字典分派 + `build_body_ctx` 单份 ctx）：
  - 旧路 `_legacy_calls`：`_walk_segmenter_stmts` 枚举 `kind=="simple"` 且 `tokens[0]=="CALL"` 的 `Stmt`，跑 `rules._t_call(toks, ctx)` → `(raw, (lines, matched))`；
  - 新路 `_asg_calls`：`build_asg` → `_CallCollector(AsgVisitor).visit_CallStmt`（`generic_visit` 递归 then/els/inline_body 捕嵌套 CALL），跑 `translate_call(node.tokens, ctx)` → `(raw, (lines, matched))`；
  - 按源码序对齐，逐字符 diff `(lines, matched)`。
- **退出码**：全等 0 / 有差异 1。
- *设计思路*：脚手沿用步骤18/19/20，`_SAMPLERS["CALL"]=(_legacy_calls,_asg_calls)`，比对主干不重写（§16 复用）。

---

## 6. 落地步骤（认可后严格按序，每步出产物即验）

1. 建 `translator/leaf/call.py`：`translate_call`+`resolve_io_info`+`derive_io_info` 原样搬 + import `leaf.expr._struct_obj`/`re`。
   扩 `context.py` LeafCtx 4 字段。改 `__init__.py` 门面增导出 `translate_call`。
2. 改 `rules.py`：删三定义、加别名+再导入。**跑 `python -m unittest test_translation` + `scripts/regress_config_snapshot.py` → 须全绿/零 diff**（硬闸，先验旧路径无副作用）。
3. `asg/nodes.py`+`asg/builder.py`：CallStmt 加 `tokens`、`_lift` 填充。跑既有 ASG 单测须仍绿。
4. `asg/visitor.py`：`LeafJavaVisitor` 加 `visit_CallStmt`；import 增 `translate_call`。跑既有单测须仍绿（不破 MOVE/IF/PERFORM 比对）。
5. `scripts/diff_asg_vs_legacy.py`：加 `--verb CALL` + `_legacy_calls`/`_CallCollector`/`_asg_calls` + `_SAMPLERS` 项。对样例程序跑，**两路 `(lines,matched)` 逐字符零差异**。
6. 加单测（§7）。全量 `test_translation` 全绿。
7. 回填本设计「实现结果」、更新 `docs/架构索引/项目总览.md`（`leaf/call.py` + LeafCtx 扩字段 + CallStmt.tokens + `visit_CallStmt` + 比对闸 `--verb CALL`）、写 `docs/操作记录/步骤21-…操作记录.md`（命令/产物/校验/Token 分析）。

---

## 7. 自检与验收

- **旧路径零影响（硬闸）**：`test_translation` 旧用例全绿、`regress_config_snapshot` 零 diff（含 `resolve_io_info` 快照不变）。
- **新增单测**（`test_translation.py`）：
  - ① `TestLeafCallExtract`：`translate_call` 抽出后，对 IO 固化（struct_function 命中 → `obj = repo.method(obj)`）、
    功能码未设 → `([],False)`、未映射子程序 → `([],False)`、日期/系统子程序 → 对应固化——输出与抽取前 `rules._t_call` 一致。
  - ② `TestAsgCallVisitor`：含 CALL 的节点 `visit_CallStmt` 输出 == `translate_call`（matched 时逐字符）；
    `matched=False` → `// TODO-CALL`；IF/PERFORM body 内嵌 CALL 经 `_body` 占位可见。
  - ③ `TestDiffAsgVsLegacyCall`：内联程序（IO 固化 CALL / 非 IO CALL / 嵌套于 IF）`--verb CALL` 两路 `(lines,matched)` 逐字符一致。
- **不接受**：任何使旧用例/快照变化的副作用；CALL 之外动词被改动；②③被半迁；block 级被强行比对引入伪差异；
  `rules.resolve_io_info`/`derive_io_info` 公开面被破（外部引用报错）。

---

## 8. 开放问题（留后续刀）

- **Q1**：② setup+CALL+IF 结构吸收（`_match_*_single`/`_render_*`/`_rewrite_begn_loops`）迁 visitor——需先把多语句窗口扫描 + `struct_function` 时序层迁入相3，属「IO 结构吸收迁 visitor」专项刀。
- **Q2**：③ struct_rebind / BEGN foreach（步骤18 §8-Q1）——与 IO 查表 + 骨架递归耦合，随 ② 或专项重绑定刀。
- **Q3**：visit_CallStmt 固化语义（findBy/save）的端到端验证——须 struct_function 时序回放，随 ② 落地。
- **Q4**：STRING（第五刀）——CALL 后按动词序续切；其后即可评估 §5-项4 下线旧 token 通道。

---

## 9. 实现结果（回填，2026-06-26）

**公用包**（`translator/leaf/call.py`，逻辑行 < 200）：
- `translate_call(toks, ctx) -> (lines, bool)` 迁自 `rules._t_call`；`resolve_io_info`/`derive_io_info` 一并迁，逻辑零改（ctx 注解 `Ctx → LeafCtx`）。
- import `re`、`leaf.expr._struct_obj`、`leaf.context.LeafCtx`。读 ctx 的 `io_programs`/`io_default_pattern`/`date_programs`/`system_programs`/`struct_function`（均在扩后 LeafCtx 契约）。
- `__init__.py` 门面增导出 `translate_call`。

**LeafCtx 扩字段**（`translator/leaf/context.py`）：Protocol 增 `io_programs`/`io_default_pattern`/`date_programs`/`system_programs` 4 字段声明（本刀首次扩契约）。`rules.Ctx` 与 `build_body_ctx` 产物均已具备 → duck-type 自动满足，**两路 ctx 零改造**。

**rules 改造**（纯迁址 + 委托 + 再导入）：删 `_t_call`/`resolve_io_info`/`derive_io_info` 三定义（原 rules.py:1116-1229）；
顶部增 `from translator.leaf.call import translate_call as _t_call, resolve_io_info, derive_io_info`：
`_dispatch_leaf` 的 `_t_call`（CALL 分支）零改；结构吸收 4 处 `resolve_io_info`（rules.py:277/374/570/706）零改；
`rules.resolve_io_info`/`rules.derive_io_info` 经再导入保留公开面（graph/nodes、main、translator/context、translator/skeleton、scripts/regress_config_snapshot 共 5 处外部引用零改）。依赖单向 `rules → leaf`，无环。

**节点补 token**：`asg.nodes.CallStmt` 增 `tokens: list[str]`（name/using/raw/lineno 保留）；`asg.builder._lift` 的 CALL 分支填 `tokens=list(st.tokens)`。

**相3 改造**：`asg.visitor.LeafJavaVisitor` 增 `visit_CallStmt`——`translate_call(node.tokens, ctx)` 直译，`matched=False → // TODO-CALL: <raw>`（body 诚实可见）；import 增 `translate_call`。

**比对闸扩 CALL**：`scripts/diff_asg_vs_legacy.py` `--verb` 增 CALL；新增 `_legacy_calls`（segmenter 枚举 `kind=="simple"` 且 `tokens[0]=="CALL"` 跑 `rules._t_call`）、`_CallCollector`/`_asg_calls`（遍历 CallStmt 跑 `translate_call`，IF/PERFORM 等容器由基类 `generic_visit` 默认递归捕嵌套 CALL）；`_SAMPLERS` 增项。比对单位＝`(lines, matched)`（按 §4.2 不重放 struct_function 时序，两路同 ctx → 必然相等）。

**与设计偏差**：无（按 §6 落地）。`_CallCollector` 未显式写 `visit_IfStmt`/`visit_PerformStmt`（依赖基类 `generic_visit` 默认递归，同 `_MoveCollector` 范式），较设计 §5 描述更简，行为等价。

**验收（§7 三项，落实为 `test_translation.py` 单测）**：
- `TestLeafCallExtract`（①，4 测）：struct_function 命中 READR → `elpoParams = elpoRepository.findByKey(elpoParams);`、功能码未设 → `([],False)`、未映射 → `([],False)`、系统子程序 java_code → 补分号。
- `TestAsgCallVisitor`（②，2 测）：matched 时 `visit_CallStmt` == `rules._t_call(...)[0]`（逐字符）、matched=False → `// TODO-CALL: <raw>`。
- `TestDiffAsgVsLegacyCall`（③）：内联程序（IO 固化 / 非 IO / 嵌套于 IF 与 PERFORM，4 条 CALL）两路 `(lines,matched)` 逐字符一致。

**回归闸**：`python -m unittest test_translation` → **119 通过 / 2 skip / 0 失败**（旧 112 + 新 7）；
`scripts/regress_config_snapshot.py`（PYTHONIOENCODING=utf-8）exit 0（`resolve_io_info` 快照不变，rules→leaf import 完好）；
`scripts/diff_asg_vs_legacy.py <sample_call.cob> --verb CALL` → `[OK] 4 条 CALL 两路逐字符一致` exit 0；`--verb MOVE/IF/PERFORM` 同样 exit 0（前三刀回归未破）。
