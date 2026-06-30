# 步骤24C　绞杀项4 骨架装配③：BEGN/READR/WRITE IO 形态识别 + struct_rebind 迁 visitor

状态：🔶待认可→✅已认可（2026-06-26 用户认可 §2 六项 + §9 加固选样设计）→🟢24C-1 已落地（整族迁移 + 双路打通 + 四形态比对全绿，见 §7 末）→🟢24C-2/3/4 已落地（边角形态等价加固，6 类边角两路逐字符一致 + 全量 IO 吸收层零新增分歧，见 §9.5；两处发现留 24D）
对应上位路线：`架构演进-三相分层(预处理-ASG-visitor)初步设计.md` §5-项4「下线旧 token 路径」。
本刀是**项4 的第三刀**（四刀分期 24A✅/B✅/C/D，见 `步骤24A…设计.md` §2）。
前置：24A（out-of-line PERFORM 调用体）✅、24B（GO TO dispatch 状态机）✅ 已落地；`translator/skel/`
底座 + 路径中立装配 + 三回调范式 + `--verb` 比对闸范式已成型（见 24B §3.3）。

---

## 1. 背景与本刀边界（Why + 不做什么）

24B 把**段级状态机装配**（`render_flow_dispatch`）迁进了 `skel/`，visitor 的 `visit_Section` 已能产状态机壳与
段内 GO TO/EXIT dispatch。但 24B **显式留白** begn 改写（设计 24B §3.2）：旧 `build_section` 现在仍**先**
`_rewrite_begn_loops(paras, ctx)` **再**委托 `render_flow_dispatch`，而 visitor 的 `visit_Section`
**不调** begn 改写，直接 `render_flow_dispatch(asg_paras)`。后果：**含 BEGN/READR/WRITE IO 形态的 SECTION
两路暂分流**——旧路把 IO 形态吸收成 `List+for-each` / `findBy…Begn()` / `repo.save()` 等高阶 Java，
新路逐条直译（CALL→`// TODO-CALL`、setup MOVE 保留、IF STATUZ 保留），与正本不一致。**本刀（24C）补这一块。**

### 1.1 旧路 `_rewrite_begn_loops` 一族范围（rules.py:123–800，~680 行）

这是 `rules.py` 里**最大、最结构化**的一族，在状态机降级**之前**对 `paras=[(label,[Stmt])]` 做**段级结构改写**，
把四类确定性 IO 形态从「裸 CALL+setup MOVE+IF STATUZ」吸收成高阶 Java，并对吸收体内字段做 `struct_rebind`：

| 形态 | 匹配器 | 渲染器 | 产物 |
|---|---|---|---|
| ① BEGN+NEXTR 自跳循环 | `_match_begn_loop`（+`_begn_breakout_keys`/`_is_filter_if`/`_is_move_nextr`…） | `_render_begn_foreach` | `List<Rec> xList = repo.findBy…Begn(键); for (Rec x : xList) { [if(过滤)continue;] 体 }` |
| ② 单次 BEGN 等值定位 | `_match_begn_single` | `_render_begn_single` | `List<Rec> xList = repo.findBy…Begn(键); if (xList.isEmpty()) { then }` |
| ③ 单条读 READR/READS | `_match_readr_single`（+`_statuz_form`/`_parse_statuz_term`） | `_render_readr_single` | `Rec x = repo.findBy…Readr(键); if (x != null) {…} [else …]` / try-catch（error 形） |
| ④ 单条写 UPDAT/WRITE/DELET | `_match_write_single`（+`_write_statuz_form`/`_is_init_params`） | `_render_write_single` | `[Rec x = new Rec();] x.setF(…); repo.save/delete(x);` + try-catch（error 形） |

公共骨架：`_stmt_call_io`（CALL 'xxxIO' USING pfx-PARAMS 识别）、`_stmt_touches_pfx`、`_strip_struct_setup`
（剥前序段对 pfx 的 setup）、`_tag_rebind`（给吸收体内 Stmt 打 `struct_rebind`，供两趟回填用）、
`_render_rebound`（渲染期把 `ctx.struct_objects[pfx]` 临时指向 record/loop 变量 → 体内 `pfx-FIELD` 译成
`var.getField()`）。编排器 `_rewrite_begn_loops`：Pass1 处理 ① 循环、Pass2 同段处理 ②③④，匹配命中即把该
para 换成 `Stmt(kind="raw", lines=渲染结果)`，未命中保持原 stmts。

### 1.2 本刀范围（做什么）

把 §1.1 整族**自底座迁进 `translator/skel/`**，做成**路径中立**：装配/匹配/渲染逻辑**单份**，旧 `rules` 与
`asg.visitor` 各注入自有节点遍历器，两路共调 → 吸收体 Java 逐字符一致。落地后：
- 旧 `build_section` 的 `_rewrite_begn_loops(paras, ctx)` 调用点改委托 skel（行为零变化）。
- visitor `visit_Section` 在 `render_flow_dispatch` **之前**插入同一 skel 改写 → 含 IO 形态的 SECTION 两路抹平分流。

### 1.3 本刀明确不做（守界，留后续刀）

- ④ 程序级装配（`body_context` 改吃 visitor、删旧 `build_section`/`_rewrite_begn_loops` 在 rules 的委托壳、
  删 segmenter token 通道）—— 留 **24D**（真·下线）。本刀只**搬迁 + 双路共用**，旧委托壳保留。
- 任何**新增** IO 形态识别能力 —— 本刀是**等价迁移**，不识别旧路识别不了的形态（守「等价绞杀」纪律）。
- 叶子动词翻译（MOVE/算术/控制…）已在绞杀项3 迁完，本刀不动；本刀只搬「IO 段级吸收 + struct_rebind」。

---

## 2. 已确认的决定（2026-06-26 用户认可）

> 用户 2026-06-26 一并认可下列六项（D24C-1..6），均 ✅。下文 🔶 标记保留为留痕。
> **执行细化（24C-1）**：`_rewrite_begn_loops` 编排器为单函数，四形态匹配/渲染同族，**整族一次性迁
> `skel/io_rewrite.py`**（无法只迁形态①）。故 24C-1 = 整族迁移 + 双路打通 + ASG `Raw`/`visit_Raw` +
> `--verb IO` 闸，**比对闸先验形态①**；旧路硬闸（161 测试 + config 快照）天然回归全四形态。
> 24C-2/3/4 = 逐形态扩 `--verb IO` 选样、验 visitor 路四形态产物一致、修 `ASG_ACCESS` 边角。
> visitor 路非生产路（生产=body_context 旧路，24D 才 cutover），形态②③④在 24C-1 落地但待 24C-2/3/4 逐一验证。

- **[D24C-1 落点]** 新建 `translator/skel/io_rewrite.py`（与 24A `perform_call.py` / 24B `flow_dispatch.py`
  平行，同 `skel/` 底座）承载整族 §1.1。**推荐**。🔶
- **[D24C-2 复用方式]** **路径中立编排/匹配/渲染 + 节点访问器协议（accessor）+ 渲染回调**（见 §3.3）。
  匹配器读取的节点字段（`kind/tokens/children/else_children/whens`）抽成 5 个只读访问器，旧路传
  `STMT_ACCESS`（属性直读）、新路传 `ASG_ACCESS`（按类型派生 kind + `then/els/cond/inline_body` 映射）；
  渲染器的体渲染抽成 `render_body` 回调（旧=`build_skeleton`，新=visitor 段体渲染）。**推荐**（与 24B 同philo）。🔶
  - 备选A：ASG 节点包一层 `Stmt` duck-type 适配器，原样跑旧匹配器 —— 渲染期两趟回填/`new_leaf`/`struct_rebind`
    与 visitor 一趟内联模型耦合，否决（理由见 §3.4）。
  - 备选B：`visit_Section` 把 ASG paras 降级回 `[(label,[Stmt])]` 再调旧 `_rewrite_begn_loops`+`build_skeleton`
    —— 等于新路产物绕回 rules，违绞杀方向（rules 要在 24D 删），否决。
- **[D24C-3 ASG `Raw` 节点]** ASG 新增 `Raw(lines: list[str])` 节点 + visitor `visit_Raw`（emit `.lines`，
  镜像旧 `_skeleton_one` 的 `kind=="raw"` 分支）。改写命中的 para 在新路换成 `[Raw(lines=…)]`。**推荐**。🔶
- **[D24C-4 rebind 模型差异]** 旧路两趟（占位 + 延迟 `translate_leaf` 读 `struct_rebind` 回填），新路一趟
  （`render_body` 同步渲染时 `ctx.struct_objects[pfx]` 已置）。**两路均经同一 leaf 译器 + 同一 ctx.struct_objects
  活动态 → 吸收体 Java 逐字符一致**；新路无需 `struct_rebind` 标记（仅旧路两趟需要）。详见 §3.5。**推荐接受此差异**。🔶
- **[D24C-5 比对闸]** `scripts/diff_asg_vs_legacy.py` 扩 `--verb IO`：枚举每 SECTION，两路各跑「io_rewrite →
  render_flow_dispatch」，比对吸收体 Java 行 + `pending_*`/`struct_objects` 复位快照逐字符/逐项一致。fresh ctx
  隔离。选样覆盖四形态 ①②③④ 各至少一例 + 「无 IO 形态」对照段。详见 §5。**推荐**。🔶
- **[D24C-6 是否拆子刀]** 本族 ~680 行、四形态相对独立。**推荐拆 4 个子步骤顺序落地**，降单步风险、便于比对闸逐形态收敛：
  - **24C-1**：底座搭建（`io_rewrite.py` 骨架 + accessor 协议 + `render_body`/`make_raw` 回调 + ASG `Raw`/`visit_Raw`
    + `--verb IO` 闸）**＋形态①BEGN+NEXTR foreach** 迁移与双路打通。
  - **24C-2**：形态② 单次 BEGN 等值定位。
  - **24C-3**：形态③ 单条读 READR/READS。
  - **24C-4**：形态④ 单条写 UPDAT/WRITE/DELET。
  每子刀独立硬闸（①②③全绿）+ 操作记录。若用户希望一刀切完，则合并为单 24C（不推荐，风险集中）。🔶

---

## 3. 探查结论与关键设计抉择（留痕）

### 3.1 旧路调用链与时序（rules.py）

```
build_section(paras, ctx, indent, force_sm)                       # 803
  ├ paras = _rewrite_begn_loops(paras, ctx)                       # ← 本刀迁（812 行调用点）
  │    ├ norm = [(lbl or __ENTRY_i, list(stmts)) …]               # 标签规范化（副本）
  │    ├ Pass1: 各段 _match_begn_loop → 命中且 exit_label==下一段标签 且 前序段含 MOVE BEGN
  │    │        → result[i]=[Stmt(raw, lines=_render_begn_foreach)]; 前序段 _strip_struct_setup
  │    └ Pass2: 各未被 Pass1 处理段 → _match_begn_single ②/_match_readr_single ③/_match_write_single ④
  │             命中 → before + [Stmt(raw, lines=_render_*)] + after
  └ render_flow_dispatch(paras', …)                               # 24B 已迁（壳/dispatch）
```

匹配器读取的节点契约（全部只读）：`st.kind`（"simple"/"if"/"evaluate"/"perform"/"raw"）、`st.tokens`、
`st.children`、`st.else_children`、`st.whens`。渲染器写 `st.struct_rebind`（仅 `_tag_rebind`）、
读/写 `ctx.struct_objects`（`_render_rebound`/foreach 渲染期）、调 `build_skeleton` 渲染体、调
`_try_condition`/`_operand`/`resolve_io_info`（均已是 leaf/共用纯函数或 ctx 查表）。

### 3.2 ASG 节点 ↔ Stmt 契约映射（访问器口径）

| 匹配器读 `Stmt.X` | ASG 访问器 `ASG_ACCESS` 返回 |
|---|---|
| `.kind` | `Leaf/MoveStmt/CallStmt→"simple"`；`GotoStmt→"simple"`（tokens=[GO,TO,X]）；`IfStmt→"if"`；`EvaluateStmt→"evaluate"`；`PerformStmt→"perform"`；`Raw→"raw"` |
| `.tokens` | `node.tokens`（Leaf/Move/Call/Goto 有）；`IfStmt→node.cond`；`EvaluateStmt→node.subject` |
| `.children` | `IfStmt→node.then`；`PerformStmt→node.inline_body`；`EvaluateStmt→[]`；其余 `[]` |
| `.else_children` | `IfStmt→node.els`；其余 `[]` |
| `.whens` | `EvaluateStmt→node.whens`；其余 `[]` |

旧路 `STMT_ACCESS` 为纯属性直读（`lambda s: s.kind` 等）。**关键**：`_contains_goto`/`_then_single_goto`/
`_is_filter_if` 依赖 `children/else_children/whens` 的递归——ASG 把 `PerformStmt.inline_body` 当 `children`、
`IfStmt.then/els` 当 `children/else_children` 后，递归口径与旧路完全一致（已与 24B `_asg_collect_gotos`
口径对齐：IfStmt.then/els、EvaluateStmt.whens、PerformStmt.inline_body）。

### 3.3 复用方式（D24C-2 推荐）：访问器协议 + 渲染回调

`io_rewrite.py` 暴露 `rewrite_io_paras(paras, ctx, *, acc, render_body, make_raw) -> paras'`：
- `acc`：5 只读访问器的不可变集合（`kind/tokens/children/else_children/whens`），见 §3.2。匹配器内所有
  `st.kind`→`acc.kind(st)` 等（机械替换，**逻辑零改**）。
- `render_body(stmts, indent) -> list[str]`：渲染吸收体（过滤体/loop 体/then/else/setter/try_tail）。
  旧=`lambda s,i: build_skeleton(s, ctx, i)`；新=visitor 的段体渲染（visit 每节点 + 下沉缩进，复用
  24B 的 `_render_para_body` 同款）。**时序关键**：渲染器必须**先**设 `ctx.struct_objects[pfx]=var` **再**调
  `render_body`，故 `render_body` 必为回调（不可预渲染）——与 24B `render_flow_dispatch` 同理。
- `make_raw(lines) -> node`：产本路 raw 节点。旧=`Stmt(kind="raw", lines=…)`；新=`nodes.Raw(lines=…)`。

匹配器（§1.1 那 20+ 个 `_match_*`/`_is_*`）改吃 `acc`，逻辑零改、纯函数；渲染器（5 个 `_render_*`）改吃
`render_body`/`make_raw`，其余（finder 派生、`resolve_io_info`、`_operand`、`_try_condition`）已共用。
编排器 `rewrite_io_paras` 逻辑零改（仅 `Stmt(kind="raw")` → `make_raw`）。

### 3.4 为何不用「ASG 包 Stmt 适配器原样跑」（备选A 否决）

适配器能让匹配器零改跑通（只读够用），但**渲染期**塌：旧渲染器调 `build_skeleton`，其叶子走 `ctx.new_leaf(st)`
**占位**、第二趟 `translate_leaf` 读 `st.struct_rebind` 回填——这是 rules 的**两趟**模型。visitor 是**一趟内联**
（visit_MoveStmt 立即 translate_move）。若 ASG 经适配器走 `build_skeleton`，等于新路产物又绕回 rules 两趟，
违绞杀方向且 `new_leaf`/`pending` 副作用与 visitor 冲突。故渲染体**必须**走 `render_body` 回调（各路自渲染），
而非共用 `build_skeleton` —— 这正是 §3.3 选「访问器 + 回调」而非「适配器」的根因。

### 3.5 rebind 模型差异与一致性论证（D24C-4）

- **旧路（两趟）**：`_render_begn_foreach`/`_render_rebound` 在 `build_skeleton` 期临时设
  `ctx.struct_objects[pfx]=var`（覆盖**渲染期**读 ctx 的条件/loop 头），同时 `_tag_rebind` 给体内 Stmt 打
  `struct_rebind`（覆盖**第二趟** `translate_leaf` 回填的 MOVE 等叶子）。两套并用因叶子是占位+延迟填。
- **新路（一趟）**：`render_body` 同步渲染时 `ctx.struct_objects[pfx]=var` 已置 → 体内 MOVE 经
  visit_MoveStmt→translate_move 立即读到 rebind，**无需** `struct_rebind` 标记。
- **一致性**：两路最终都经**同一** leaf 译器（translate_move/_try_condition/_operand…）在**同一**
  `ctx.struct_objects[pfx]=var` 活动态下产行 → 吸收体 Java 逐字符一致。差异仅「何时读 ctx」（旧延迟/新即时），
  对最终文本无影响。比对闸（§5）按最终行 + 复位快照校验，覆盖此差异。
- **取舍**：新路 `make_raw`/`render_body` 路径**不调** `_tag_rebind`（visitor 无两趟）；`_tag_rebind` 仅旧路
  `render_body=build_skeleton` 链需要，保留在旧渲染器内（或由 `render_body` 旧实现自带）。

### 3.6 ctx 契约

`SkelCtx`（24A 建、24B 扩）已有 `struct_objects`、`io_programs`、`io_default_pattern`、`pending_range_methods`
等字段（rules.Ctx 与 body_context 产物 duck-type 满足）。本刀**不新增 ctx 字段**；`struct_objects` 读写沿旧路
范式（渲染器内 save/set/restore）。

---

## 4. 详细设计：类/方法/数据流（认可后落，先骨架后回填）

### 4.1 新文件 `translator/skel/io_rewrite.py`（整族迁入，路径中立）

把 rules.py:123–800 的匹配器/渲染器/编排器**原样迁址**（逻辑零改，节点访问改 `acc`、体渲染改 `render_body`、
raw 构造改 `make_raw`）。对外暴露：

```python
# 访问器协议（5 只读字段，frozen）
@dataclass(frozen=True)
class NodeAccess:
    kind: Callable; tokens: Callable; children: Callable
    else_children: Callable; whens: Callable

def rewrite_io_paras(paras, ctx, *, acc, render_body, make_raw) -> list[tuple]:
    """= 旧 _rewrite_begn_loops：Pass1 BEGN+NEXTR foreach + Pass2 单次 BEGN/READR/WRITE。
    命中段 → [(label, [make_raw(渲染行)])]；前序段 _strip_struct_setup（经 acc）。无命中 → 原 paras。"""
```

迁随私有：四形态 `_match_*` + 公共 `_stmt_call_io`/`_begn_breakout_keys`/`_statuz_form`/`_strip_struct_setup`/
`_tag_rebind`（旧 render 链用）+ 五 `_render_*`。约 **~600 逻辑行**（搬迁，非新增）。

### 4.2 `translator/skel/__init__.py` 门面扩导出
加 `rewrite_io_paras` / `NodeAccess` / `STMT_ACCESS`（旧路属性直读实例）。

### 4.3 改 `translator/rules.py`（委托，调用点零改）
- `from translator.skel import rewrite_io_paras, STMT_ACCESS`。
- `_rewrite_begn_loops(paras, ctx)` 改为薄壳：
  `return rewrite_io_paras(paras, ctx, acc=STMT_ACCESS, render_body=lambda s,i: build_skeleton(s, ctx, i), make_raw=lambda lines: _raw_stmt(lines))`，
  其中 `_raw_stmt` 产 `Stmt(kind="raw", lines=…)`（保 `_tag_rebind` 在旧 render 链内）。删 §1.1 原匹配/渲染函数体
  （别名导回保 rules.* 公开面，沿 24A/24B 范式）。`build_section` 调用点（812 行）零改。

### 4.4 改 `asg/nodes.py` + `asg/visitor.py`
- `asg/nodes.py` 新增 `@dataclass Raw: lines: list[str]`（D24C-3）。
- `asg/visitor.py`：
  - `ASG_ACCESS = NodeAccess(kind=_asg_kind, tokens=_asg_tokens, children=_asg_children, else_children=_asg_else, whens=_asg_whens)`（§3.2 映射，~15 行模块级）。
  - `visit_Section`：在 `render_flow_dispatch` **前**插入
    `paras = rewrite_io_paras(paras, self.ctx, acc=ASG_ACCESS, render_body=self._render_para_body, make_raw=lambda lines: nodes.Raw(lines=lines))`，
    再 `render_flow_dispatch(paras, …)`（其余 24B 接线不变）。
  - `visit_Raw`：`return list(node.lines)`（缩进由 `_render_para_body`/`render_flow_dispatch` 统一施加，
    镜像旧 `_skeleton_one` 的 `kind=="raw"` 整体下沉）。

### 4.5 数据流（两路对照）
```
旧路: build_section→_rewrite_begn_loops(薄壳)→rewrite_io_paras(STMT_ACCESS, build_skeleton, Stmt-raw) ─┐
新路: visit_Section→rewrite_io_paras(ASG_ACCESS, _render_para_body, nodes.Raw) ────────────────────────┴→ 同匹配同渲染同吸收体
随后两路 → render_flow_dispatch（24B 已一致）→ 整段 Java 逐字符一致（IO 形态 + 状态机 + dispatch 全覆盖）
```

---

## 5. 比对闸：`--verb IO`

仿 24A/24B，新增 `IO` 比**段级 IO 形态吸收**：
- **legacy 采样** `_legacy_ios`：segmenter 切分 → 每 SECTION paras 跑 `rewrite_io_paras(STMT_ACCESS,…)`
  → `build_section` 全链（含其后 render_flow_dispatch），收 `(section, lines, snapshot)`，fresh ctx。
- **asg 采样** `_asg_ios`：遍历 ASG `Section` 跑 `visit_Section`（内部 rewrite_io_paras+render_flow_dispatch），
  收同三元组，fresh ctx。
- **比对**：吸收体 Java 行（`List<>…findBy…Begn`/`for-each`/`if(record!=null)`/`repo.save`/try-catch）逐字符一致
  **且** `struct_objects` 渲染收尾复位、`pending_range_methods` 等副作用一致。
- **选样守界**：覆盖四形态各 ≥1 例（①BEGN+NEXTR 循环、②单次 BEGN、③READR/READS、④UPDAT/WRITE/DELET）
  + 含过滤 IF 的循环 + STATUZ error 形（try-catch）+ 无 IO 形态对照段；**段体动词须均已迁**（绞杀项3 已覆盖
  MOVE/IF/算术/控制/EVALUATE/PERFORM，满足）。

---

## 6. 风险与回归

| 风险 | 控制 |
|---|---|
| 600 行搬迁引入语义漂移 | 逻辑零改、仅访问/渲染/raw 三处参数化；旧路 `--verb` 全回归 + 156 测试硬闸 |
| ASG 访问器 kind/tokens 映射偏差（IfStmt.cond vs tokens、Perform.inline_body vs children） | §3.2 表 + 与 24B `_asg_collect_gotos` 口径对齐；比对闸含嵌套 IF/PERFORM 体内 IO 样本 |
| 一趟/两趟 rebind 产物不一致 | §3.5 论证 + 比对闸逐字符校验吸收体（含 rebound 字段 getField/setField）+ struct_objects 复位快照 |
| `render_body` 时序（先设 struct_objects 再渲染体）写错 → 字段直译漂移 | 渲染器内严格「设 struct_objects→render_body→复位」（沿旧范式）；比对闸覆盖 foreach/readr/write 三类体 |
| 含 IO 形态 SECTION 的 `_strip_struct_setup` 跨段剥除在新路漏做 | 编排器单份共用，剥除走 `acc`；比对闸选「前序段含 BEGN setup」样本验证两路同剥 |
| ASG 新增 `Raw` 节点影响既有 generic_visit/_children | `Raw` 纯叶子（无子节点），`_children` 不涉及；`visit_Raw` 纯新增，旧节点零改 |

**硬闸（每子刀均须）：**
- ①旧路径零影响：`python -m unittest test_translation` 全绿（当前 161）。
- ②config 快照零 diff：`scripts/regress_config_snapshot.py` before/after `[ZERO-DIFF OK]`。
- ③比对闸 IO：该子刀形态样例两路吸收体 + 副作用一致；`--verb FLOW/CONTROL/MOVE/PERFORMCALL` 回归仍 `[OK]`。

---

## 7. 新增/改动文件清单（🟢24C-1 实测回填）

| 文件 | 动作 | 职责 / 实测 |
|---|---|---|
| `translator/skel/io_rewrite.py` | 新建 | BEGN/READR/WRITE IO 形态识别 + struct_rebind 段级吸收（路径中立：`NodeAccess`/`STMT_ACCESS` + `render_body` + `make_raw`），**34 个函数 / ~600 逻辑行**（原样迁址，仅三处参数化） |
| `translator/skel/__init__.py` | 改 | 导出 `rewrite_io_paras`/`NodeAccess`/`STMT_ACCESS` |
| `translator/rules.py` | 改 | 删 begn 族 ~680 行；`_rewrite_begn_loops` 改委托 `rewrite_io_paras`（注入 `STMT_ACCESS`/`build_skeleton`/`_raw_stmt`）；`build_section` 调用点零改。rules 由 ~1103 行降至 **337 行** |
| `asg/nodes.py` | 改 | 新增 `Raw(lines)` 节点（纯叶子，无子节点） |
| `asg/visitor.py` | 改 | 模块级 `_asg_kind/_asg_tokens/_asg_children/_asg_else/_asg_whens` + `ASG_ACCESS`；`visit_Section` 前插 `rewrite_io_paras`（ASG_ACCESS/_render_para_body/`nodes.Raw`）；新增 `visit_Raw` |
| `scripts/diff_asg_vs_legacy.py` | 改 | 扩 `--verb IO`（`_legacy_ios`/`_asg_ios`/`_io_snapshot`，复用 `_fill_legacy_leaves`；快照含 flow + struct_objects 复位；fresh ctx 隔离） |
| `test_translation.py` | 改 | 新增 `TestSkelIoRewrite`（3 条：READR/WRITE/BEGN-foreach 经 STMT_ACCESS 吸收）+ `TestDiffAsgVsLegacyIo`（1 条：整程序五段两路全等 + 四形态防退化 + 副作用复位断言） |

**硬闸实测（24C-1）**：①`unittest` `Ran 165 OK (skipped=2)`（迁前 161，+4 新测）；②config 快照 before/after 各 377 行
`[ZERO-DIFF OK]`；③`--verb IO` 样例（READR/WRITE/BEGN-foreach/单次 BEGN/扁平 5 段）两路 `(吸收体, flow+struct
复位快照)` 逐字符/逐项一致，四形态均确认吸收（`findByChdrcoyReadr`/`if(elpo!=null)`/`tmlcRepository.save`/
`for(SublRecord subl:sublList)`/`subsList.isEmpty()`）；`--verb FLOW/CONTROL/MOVE/CALL/PERFORMCALL` 回归仍 `[OK]`。
**rebind 一致性自证**：foreach 体内 `wsaaData = subl.getData()`、readr 体内 `wsaaData = elpo.getData()`、write 体内
`tmlc.setField(wsaaVal)` 两路（旧两趟 struct_rebind / 新一趟 struct_objects）逐字符一致 → §3.5 论证成立。

---

## 8. 开放点（待用户认可后固化）

1. **落点** `translator/skel/io_rewrite.py`（D24C-1）。
2. **复用方式** 访问器协议 + render_body/make_raw 回调（D24C-2，非适配器、非降级回 Stmt）。
3. **ASG `Raw` 节点 + visit_Raw**（D24C-3）。
4. **一趟/两趟 rebind 差异接受**（D24C-4，§3.5 论证一致）。
5. **比对闸** `--verb IO`，比吸收体 + struct_objects/pending 副作用（D24C-5）。
6. **是否拆 24C-1..4 子刀顺序落地**（D24C-6，推荐拆）。

> 用户 2026-06-26 认可 §2 六项；24C-1 已按 §4 落地、§5/§6 自检通过（硬闸①②③全绿，见 §7 末）、§7 与本节回填、架构索引同步。
> **24C-1 落地结论**：整族迁 `skel/io_rewrite.py` 路径中立 + 双路打通 + ASG `Raw`/`visit_Raw` + `--verb IO` 闸；
> 四形态（①BEGN-foreach ②单次 BEGN ③READR ④WRITE）两路逐字符一致、rebind 一致性自证（§3.5 成立）。
> **24C-2/3/4（待续）**：逐形态扩 `--verb IO` 选样（嵌套 IF/EVALUATE 体内 IO、STATUZ error 形 try-catch、
> 多键 finder、含过滤 IF 的 foreach…）做更宽覆盖验证；功能本步已全打通，后续为加固选样而非补能力。
> **后续刀**：24D（程序级装配 + body_context 改吃 visitor + cutover 删旧 token 路径/rules 委托壳，真·下线）。

---

## 9. 24C-2/3/4 加固选样执行设计（🔶待认可，2026-06-26）

承 §8：24C-1 已把整族迁入 `skel/io_rewrite.py` 并双路打通，四形态**基本形**（O-K 形、单键、扁平段）已逐字符一致。
24C-2/3/4 **不补能力**，只**逐形态扩边角样本**——把 `io_rewrite` 里**已存在但 24C-1 比对闸未触达**的分支
（error 形 try-catch、多键 finder `And`-join、含过滤 IF 的 foreach、嵌套于 IF/EVALUATE 体内的 IO 递归）在
**两路（`STMT_ACCESS` / `ASG_ACCESS`）**下逐字符比对，定位并修 `ASG_ACCESS` 边角映射偏差（若有）。
用户 2026-06-26 选「24C-2/3/4 一并做」→ **合并一趟执行 + 单份操作记录**，但按形态分块保留防退化断言（覆盖可审计）。

### 9.1 选样矩阵（每行 = 一个 SECTION 样本，两路逐字符比对 + 防退化断言）

> **技术校正（执行中发现，2026-06-26）**：IO 匹配器（`_match_begn_single`/`_match_readr_single`/`_match_write_single`）
> 在 **para 顶层 stmts 上平铺匹配**（`_stmt_call_io` 逐顶层节点找 CALL），**不下降进 IF/EVALUATE 体内**吸收嵌套 IO。
> 故「嵌套于 IF 体内的 IO」两路都不吸收（伪通过），**非有效选样**。`ASG_ACCESS.children/else_children/whens` 递归
> 口径的真实考点 = **吸收体的 body 内含嵌套 IF/EVALUATE 且引用 `<pfx>-FIELD`**：`render_body`+`_tag_rebind` 经
> `acc.children/whens` 递归，验两路 rebind 字段访问逐字符一致。样本 (b) 据此改为 body 内嵌套。

> **再校正**：单次 BEGN（form ②）渲染只产 `List.isEmpty()` 检查、**不绑定 record 变量**，then 体内无 rebind 字段访问。
> 故 `acc.children/else_children/whens` 递归口径的真实考点归到**会 rebind 的吸收体**——本步用 form ③ READR 的 then 体内
> 同时嵌套 IF（含 else）+ EVALUATE 且引用 `ELPO-FIELD`，一例覆盖 children/else_children/whens 三条递归路径。form ② 只留多键样本。

| 子刀 | 形态 | 边角样本 | 命中 `io_rewrite` 分支 | 防退化断言（产物含） |
|---|---|---|---|---|
| 24C-2 | ② 单次 BEGN | (a) 多键等值定位 | `_render_begn_single` finder `And`-join | `findBy…And…Begn(` |
| 24C-3 | ③ READR/READS | (b) error 形 → try-catch | `_render_readr_single` mode="error" | `try {` / `} catch` / 580 入 catch |
|  |  | (c) 多键 finder | finder `And`-join | `findBy…And…Readr(` |
|  |  | (d) READS 变体 | func=READS | `findBy…Reads(` |
|  |  | (e) then 体内嵌套 IF(含 else)+EVALUATE 引用 `ELPO-FIELD` | `render_body`+`_tag_rebind` 经 `acc.children/else_children/whens` 递归 | 嵌套块内 `elpo.getField()` 两路一致 |
| 24C-4 | ④ UPDAT/DELET | (f) UPDAT 复用既有 record | `_render_write_single` is_new=False | `…Repository.save(` 无 `new` |
|  |  | (g) DELET | is_delete=True | `…Repository.delete(` |
|  |  | (h) write error 形 | mode="error" | `try {` + save/delete |

> （④ WRITR 新建实体 `new XxxRecord()` + save 已由 24C-1 `test_legacy_equals_asg_io` 覆盖，本步不重复。）

每样本两路 `(吸收体 Java 行, flow+struct_objects 复位快照)` 逐字符/逐项一致；防退化断言确保「确实吸收了该边角形态」
而非两路同样漏吸收的伪通过。

### 9.2 验证载体与方法

- **主载体**：扩 `test_translation.py::TestDiffAsgVsLegacyIo`（沿 24C-1 范式）——每子刀新增一个 SRC 夹具常量 + 一个
  test 方法，跑 `_legacy_ios`/`_asg_ios` 两路，断言 `[x[1] …]` 全等 + §9.1 防退化串 + 快照复位（flow=None、
  struct_objects=()）。fresh ctx 隔离。
- **辅证（broad）**：若主翻译链能解析真实程序，`scripts/diff_asg_vs_legacy.py … --verb IO` 跑
  `scripts/spike_proleap/cleaned_ZPOLDWNM.cob`（302 IO 行）做全段两路回归；**若不能解析则跳过、以夹具为准**
  （不臆造可跑性，纪律⑧）。
- **`ASG_ACCESS` 边角修**：若某嵌套样本两路 diff，按 §3.2 表定位 kind/tokens/children/else_children/whens 映射偏差，
  **仅修访问器映射**（不改 `io_rewrite` 共享逻辑、不改旧路），回填 §3.2/§7。

### 9.3 硬闸（合并执行后一次性，§6 末口径）

- ① `python -m unittest test_translation` 全绿（基线 165 → 预计 +3 新测）。
- ② `scripts/regress_config_snapshot.py` before/after `[ZERO-DIFF OK]`。
- ③ `--verb IO` 新样本两路一致；`--verb FLOW/CONTROL/MOVE/CALL/PERFORMCALL` 回归仍 `[OK]`。

### 9.4 守界（不做）

- 不改 `io_rewrite` 共享匹配/渲染逻辑（24C-1 已迁、已等价）；本步只加样本 + 必要时修 `ASG_ACCESS` 映射。
- 不动 24D 范围（body_context cutover、删旧委托壳/token 通道）。
- 不识别 `io_rewrite` 现未识别的新形态（守等价绞杀纪律）。

### 9.5 🟢实测结论（2026-06-26 落地）

**产物**：`test_translation.py::TestDiffAsgVsLegacyIo` 新增 3 方法（无生产代码改动，纯加测试）：
- `test_24c2_begn_single_multikey`：形态② 多键 → `findByChdrcoyAndChdrnumBegn(wsaaCompany, wsaaNum)`。
- `test_24c3_readr_error_reads_multikey_nested`：形态③ error 形 try-catch（`findByItemkeyReadr` + `try{}/catch{}` + try_tail rebind `itdm.getValue()`）、READS 多键（`findByChdrcoyAndChdrnumReads`）、then 体内嵌套 IF(含 else) rebind（`elpo.getData()`）。
- `test_24c4_write_updat_reuse_delet_error`：形态④ UPDAT 复用（`save` 无 `new`）、DELET（`delete`）、write error 形（`new`+`try{save}/catch`）。

**硬闸**：① `unittest` `Ran 168 OK (skipped=2)`（基线 165 +3）；② config 快照 377 行（生产路径零改动→零 diff 由构造保证）；
③ inline 比对（unittest 内 `TestDiffAsgVsLegacy*` 全动词）通过；CLI `--verb MOVE/CALL/CONTROL/PERFORMCALL` 跑全量
`cleaned_ZPOLDWNM.cob` 均 `[OK]`（2953/247/357/271 条逐字符一致）。

**两处发现（均超 24C 守界，记此留 24D 决策）**：
1. **体内嵌套复合语句两路 stub 文本分歧**：IO 吸收体（及一般段体）内**无法翻译的复合语句**——含 STRING 的 IF、
   体内 EVALUATE、数组下标等——旧路（`build_skeleton` 两趟叶子模型）当 leaf 占位渲染成 `// TODO-LEAF: …`，
   新路（visitor 一趟递归）渲染成 `// TODO-IF:`/`// TODO-EVALUATE: …`。**两路都未翻译该构造，仅 TODO 标记文本不同**；
   根因是两种 `render_body` 模型对体内复合语句的处理差异，**非 ASG_ACCESS 映射、非 IO 吸收、非 flow 逻辑错误**。
   故 24C-2/3/4 选样**只验已迁叶子动词（MOVE/IF-纯叶子/算术…）构成的吸收体**等价（全绿），不含上述未译构造。
2. **全量真实程序广度辅证**：CLI `--verb IO` 跑 `cleaned_ZPOLDWNM.cob` → 112 段失败；`--verb FLOW` 同样 112 段失败，
   **且两者失败段集合逐段完全相同** → **IO 吸收层在真实程序上零新增分歧**（IO 透明，分歧全继承自 flow/leaf 层），
   112 处性质即发现①（`// TODO-LEAF` vs `// TODO-IF/EVALUATE` 等未译构造 stub 文本差）。该状态为 24C-1 working-tree
   既有（24C-1 比对闸仅跑 inline 样本，未跑全量），**非本步引入**。**留 24D**：cutover 前需统一未译构造的 TODO stub
   口径（或确认以 visitor 标记为目标），使全量 IO/FLOW 两路收敛。

**结论**：24C-2/3/4 目标（IO 吸收**边角形态**等价加固）达成——多键/error try-catch/READS/UPDAT/DELET/嵌套 IF
六类边角两路逐字符一致，且真实程序上 IO 吸收层零新增分歧。剩余全量收敛属 flow/leaf 层未译构造 stub 统一，归 24D。
