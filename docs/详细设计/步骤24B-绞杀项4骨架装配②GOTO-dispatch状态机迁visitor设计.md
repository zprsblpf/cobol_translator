# 步骤24B　绞杀项4 骨架装配②：GO TO dispatch 状态机（段内回跳 → `FLOW`/`__pc`/`continue FLOW`）迁 visitor

状态：🟢已实现（2026-06-26；设计 🔶→✅认可→🟢落地，实测见 §7 末与操作记录）
对应上位路线：`架构演进-三相分层(预处理-ASG-visitor)初步设计.md` §5-项4「下线旧 token 路径」。
本刀是**项4 的第二刀**（四刀分期 24A✅/B/C/D，见 `步骤24A…设计.md` §2）。
前置：24A（out-of-line PERFORM 调用体）已🟢落地，建立 `translator/skel/` 底座与 token-based 迁址 + `--verb` 比对闸范式。

---

## 1. 背景与本刀边界（Why + 不做什么）

24A 把**叶子级**与**单语句级**骨架（PERFORM 调用体）迁进了 visitor，但 visitor 仍是**纯语句级**遍历——`generic_visit` 把 `Section.paragraphs` / `Paragraph.stmts` 拍平递归，**没有段级装配**。而旧路 `rules.build_section`（rules.py:803）是**段级**降级器：把一个 SECTION 的若干 paragraph 拼成方法体，遇**段内回跳 GO TO**（back-edge，目标 paragraph 索引 ≤ 当前）时降级成带标签的状态机：

```java
String __pc = "FIRST";   // 段内 GO TO 回跳 → 状态机
FLOW: while (true) {
  switch (__pc) {
    case "FIRST": { … __pc = "NEXT"; continue FLOW;  /* fall-through */ }
    case "NEXT":  { … break FLOW; }
    default: break FLOW;
  }
}
```

配套的**单语句级** dispatch 行由旧 `_sk_control`（rules.py:964）在 `ctx.flow_label` 为真时产出：
- `GO TO X`（X∈段内标签）→ `__pc = "X"; continue FLOW;`
- `EXIT` → `break FLOW;`

visitor 现状对此**显式留白**：`visit_GotoStmt`（visitor.py:100）注释「dispatch 模式…留骨架装配刀」，`EXIT`（Leaf 节点）也未感知 `flow_label`。故新路对含段内回跳 GO TO 的 SECTION 产不出状态机，与正本不一致。**本刀（24B）补这一块**：段级状态机装配 + 单语句 dispatch 行。

**本刀只切 GO TO dispatch 状态机：**
1. **段级装配**：把 `build_section` 的「label 规范化 + 跳转探测 + `FLOW` while/switch 壳 + `flow_label`/`flow_paragraphs` 副作用」迁成 `translator/skel/` 段级公用函数；visitor 新增 `visit_Section`/`visit_Paragraph` 走同一函数。
2. **单语句 dispatch**：`GO TO X→__pc/continue FLOW`、`EXIT→break FLOW` 两行抽成 skel 公用判定；旧 `_sk_control` 与 visitor（`visit_GotoStmt` + `visit_Leaf` 的 EXIT 入口）共调 → 逐字符一致。

**本刀明确不做（守界，留后续刀）：**
- ③ BEGN/NEXTR for-each、IO 形态识别 + `struct_rebind`（`_rewrite_begn_loops` 一族）—— 留 **24C**。
  注：`build_section` 现在**先** `_rewrite_begn_loops` **再**状态机降级；本刀只迁状态机部分，begn 改写仍留在旧 `build_section` 里（见 §3.2）。visitor 段级入口本刀**不做** begn 改写 → 对含 begn 循环的 SECTION 两路暂分流（诚实，留 24C 抹平；比对闸据此选样，见 §5）。
- ④ 程序级装配（`body_context` 改吃 visitor、删旧 `build_section`/segmenter token 通道）—— 留 **24D**（真·下线）。
- `back_edge_state_machine()` 关时的扁平拼接路径**也迁**（它与状态机同属 `build_section` 段级装配，是状态机的「另一支」，一并搬走才完整；非新增能力）。
- 前向 GO TO（非回跳，`build_section` 默认按 EXIT/return 退化）译法不变，仍由 `translate_control`（leaf）处理；本刀只接管「回跳 → 状态机」与状态机内的 dispatch。

---

## 2. 已确认的决定（2026-06-26 用户认可）

- [分期] 项4 拆 24A✅/B/C/D，本刀=②GO TO dispatch 状态机。（24A §2 已对齐）✅
- [本刀范围] 段级状态机装配（`build_section` 状态机部分，**不含** begn 改写）+ 单语句 dispatch（`GO/EXIT` 两行）。✅
- [落点] 落 `translator/skel/flow_dispatch.py`（与 24A 的 `perform_call.py` 平行，同 `skel/` 底座）。✅
- [复用方式] **路径中立的段级装配函数 + 三个回调**（`render_body`/`collect_gotos`/`ends_transfer`），两路各传自有节点遍历器；装配逻辑（label 规范化、跳转探测、`FLOW` 壳、`flow_label` 副作用）零改单份。见 §3.3。✅（用户认可推荐：非纯 token-based、非 visitor 内复刻）
- [visitor 新增段级入口] 新增 `visit_Section` + `_render_para_body`（visitor 首次具备段级遍历；不单设 `visit_Paragraph`）。✅
- [ctx 契约] `SkelCtx` 扩 `flow_label`(可写 str|None)、`flow_paragraphs`(可写 set)；`rules.Ctx` 已有这两字段，duck-type 满足。✅
- [begn 守界] `_rewrite_begn_loops` 留旧 `build_section`，本刀 visitor 不做；含 begn 的 SECTION 两路暂分流，`--verb FLOW` 选样回避，24C 抹平。✅
- [比对闸] `scripts/diff_asg_vs_legacy.py` 扩 `--verb FLOW`：比对状态机壳 + dispatch 行 + `flow_label`/`flow_paragraphs` 副作用，fresh ctx 隔离，选样限**无 begn 循环**且**体内动词均已迁**的 SECTION（见 §5）。✅

---

## 3. 探查结论与关键设计抉择（留痕）

### 3.1 旧路段级装配调用链（`rules.py`）

```
build_section(paras, ctx, indent, force_sm)            # 803 行
  ├ _rewrite_begn_loops(paras, ctx)                    # 24C，本刀不迁（留旧 build_section）
  ├ label 规范化：首段无标号 → __ENTRY_i               # ← 本刀迁
  ├ 跳转探测：_collect_gotos 取目标，j<=i(回跳) 或 force_sm 前向 → has_jump   # ← 迁
  ├ not has_jump or not back_edge_state_machine() → 扁平拼接 build_skeleton    # ← 迁（状态机另一支）
  └ has_jump → 状态机：__pc/FLOW while/switch/case/fall-through/break          # ← 迁
        set flow_label="FLOW", flow_paragraphs=set(labels) → 渲染各段体 → 复位

_sk_control(st, ctx, indent)                           # 964 行（dispatch 半）
  ├ GO + flow_label + target∈flow_paragraphs → ['__pc="X"; continue FLOW;']   # ← 迁
  ├ EXIT + flow_label → ['break FLOW;']                                        # ← 迁
  └ 其余 → translate_control（leaf，flow_label 无关，已迁）                     # 不动
```

### 3.2 为何只迁状态机、begn 改写留旧 `build_section`

`build_section` 头一步 `_rewrite_begn_loops` 属 ③（24C）。本刀若把它一并搬走会越界。处置：**抽出状态机部分**为 `render_flow_dispatch`（吃**已规范化前**的 paras），旧 `build_section` 改为「`_rewrite_begn_loops` → 委托 `render_flow_dispatch`」（begn 改写仍在旧路，零行为变化）。visitor 段级入口本刀**不调** begn 改写，直接 `render_flow_dispatch(asg_paras)`。后果：含 begn 循环的 SECTION 两路暂时分流（visitor 缺 for-each 改写）——这是绞杀渐进的**诚实暴露**，24C 补齐；比对闸选样回避（§5）。不含 begn 的纯 GO-TO-dispatch SECTION 两路逐字符一致。

### 3.3 复用方式：路径中立装配 + 回调（为何不能纯 token-based 迁址）

24A 的 `render_perform_call(header, hu, target, ctx, indent)` 吃**裸 token**，两路同源 → 天然一致。但段级装配的输入是**结构化 paragraph**，两路节点类型不同：旧路 `Stmt`（`.kind/.tokens/.children/.whens`），新路 ASG 节点（`GotoStmt/IfStmt/Leaf…`）。`_collect_gotos`/`_ends_with_transfer`/段体渲染都依赖具体节点结构，**无法纯 token 共用**。

故采**装配逻辑路径中立 + 三回调**：`render_flow_dispatch` 只做与节点类型无关的**纯装配**（label 规范化、`label_index`、跳转探测的成环判定、`FLOW`/switch/case 壳行拼装、`flow_label`/`flow_paragraphs` 副作用设置与复位、fall-through/break 决策），把三个节点相关动作外包给回调：

| 回调 | 旧路实参 | 新路实参 |
|---|---|---|
| `render_body(stmts, indent)→list[str]` | `build_skeleton(stmts, ctx, indent)` | visitor 段体渲染（visit 每 stmt 加 `_ind`） |
| `collect_gotos(stmts)→list[str]` | `_collect_gotos`（迁 skel 或留 rules 导入） | `_asg_collect_gotos`（走 ASG 节点，新增 ~12 行） |
| `ends_transfer(stmts)→bool` | `_ends_with_transfer` | `_asg_ends_transfer`（看末节点类型，新增 ~5 行） |

**关键时序**：`render_flow_dispatch` 必须**先**设 `ctx.flow_label/flow_paragraphs` **再**调 `render_body`——因为段体内 `GO TO X` 经 dispatch 判定读这两字段。故 `render_body` 必须是回调（不可预渲染）。装配单份零改 → 壳 + 副作用逐字符一致；dispatch 行（§3.4）单份 → 也一致。

**备选**：visitor 内复制一份状态机小逻辑（不抽 skel）——违 DRY、逐字符一致全靠手抄、易漂移，否决。

### 3.4 单语句 dispatch 抽成 skel 判定

`_sk_control` 的两行 dispatch 抽成 `flow_dispatch` 两个纯判定：

```python
def dispatch_goto(target_upper, ctx, indent) -> list[str] | None:   # GO TO X→__pc/continue，否则 None
def dispatch_exit(tokens, ctx, indent) -> list[str] | None:         # EXIT+flow_label→break，否则 None
```

- 旧 `_sk_control`：先调这俩，命中即返，否则落 `translate_control`（零行为变化）。
- visitor `visit_GotoStmt`：先 `dispatch_goto`，命中即返，否则现有 `translate_control` 分支（visitor.py:101 不变）。
- visitor `visit_Leaf`：开头先 `dispatch_exit`，命中即返，否则现有「算术→控制叶子→占位」链（visitor.py:88 不变）。

`target_upper` 两路同源：旧路从 `st.tokens` 取，新路 `node.target.name`（builder `_lift` `GotoStmt(target=proc.resolve(_goto_target(tokens)))` → `.name` 即大写目标），与 24A `node.target.name` 同范式。EXIT 仍是 `Leaf`（builder 只把 GO 升 `GotoStmt`），故 EXIT dispatch 入口在 `visit_Leaf`。

### 3.5 ctx 契约

`SkelCtx`（24A 建）扩两字段：`flow_label: str | None`（可写）、`flow_paragraphs: set`（可写）。`rules.Ctx`（rules.py:63-64 已有）与 `body_context` 产物 duck-type 满足。visitor 的 `self.ctx` 即 `body_context` 产的 `rules.Ctx`，本就携带 → 直接可用。

---

## 4. 详细设计：类/方法/数据流

### 4.1 改 `translator/skel/context.py`（`SkelCtx` 扩 2 字段）
```python
class SkelCtx(Protocol):
    # …24A 5 字段…
    flow_label: object        # str | None，可写：状态机循环标签（"FLOW" / None）
    flow_paragraphs: object   # set，可写：本 SECTION paragraph 标签集（大写）
```

### 4.2 新文件 `translator/skel/flow_dispatch.py`（段级装配 + dispatch 判定）
把 `build_section` 的状态机部分**原样迁址**（逻辑零改，节点相关动作改回调）：

```python
def render_flow_dispatch(paras, ctx, indent, *, render_body, collect_gotos,
                         ends_transfer, force_sm=False) -> list[str]:
    """段内控制流降级（= 旧 build_section 状态机部分，begn 改写除外）。
    paras: [(label_or_None, stmts_opaque), …]；stmts 仅经三回调消费，本函不识其类型。
    无跳转/正本关状态机 → 扁平拼接；有回跳(或 force_sm 前向) → FLOW while/switch 状态机。
    副作用：状态机分支期间设 ctx.flow_label="FLOW"/flow_paragraphs=labels，收尾复位 None/空。"""

def dispatch_goto(target_upper, ctx, indent) -> list[str] | None: ...   # §3.4
def dispatch_exit(tokens, ctx, indent) -> list[str] | None: ...         # §3.4
```
迁随私有：`_ind`（复用 rules 或随迁）、label 规范化 inline。`grammar_loader.back_edge_state_machine()` 调用照搬。约 **~45 逻辑行**（装配 30 + 两 dispatch 10 + 辅助）。

### 4.3 `translator/skel/__init__.py`（门面扩导出）
加 `render_flow_dispatch` / `dispatch_goto` / `dispatch_exit`。

### 4.4 改 `translator/rules.py`（委托，调用点零改）
- `from translator.skel import render_flow_dispatch, dispatch_goto, dispatch_exit`。
- `build_section`：保 `_rewrite_begn_loops(paras, ctx)`，其后 `return render_flow_dispatch(paras, ctx, indent, render_body=lambda s,i: build_skeleton(s, ctx, i), collect_gotos=_collect_gotos, ends_transfer=_ends_with_transfer, force_sm=force_sm)`。删原状态机/扁平拼接函数体。
- `_sk_control`：GO/EXIT 两分支改 `dispatch_goto`/`dispatch_exit` 命中即返；其余零改。
- `_collect_gotos`/`_ends_with_transfer` 保留在 rules（被 begn 改写等复用），由 `build_section` 作回调传入。

### 4.5 改 `asg/visitor.py`（新增段级入口 + dispatch 接线）
- 新增 `visit_Section`：`paras=[(p.label, p.stmts) for p in node.paragraphs]`；`return render_flow_dispatch(paras, self.ctx, 0, render_body=self._render_para_body, collect_gotos=_asg_collect_gotos, ends_transfer=_asg_ends_transfer)`。
- 新增 `visit_Paragraph`（备 generic 递归用，或 `visit_Section` 直接吃 `p.stmts` 不单独要）。
- `_render_para_body(stmts, indent)`：visit 每 stmt 加 `indent` 级缩进，扁平化。
- `_asg_collect_gotos(stmts)` / `_asg_ends_transfer(stmts)`：走 ASG 节点（`GotoStmt`/`IfStmt.then|els`/`EvaluateStmt.whens`/`PerformStmt.inline_body`）的小遍历（模块级函数，~17 行）。
- `visit_GotoStmt`：开头 `d=dispatch_goto(node.target.name if node.target else None, self.ctx, 0); if d is not None: return d`；其后现有 `translate_control` 分支不变。
- `visit_Leaf`：开头 `d=dispatch_exit(node.tokens, self.ctx, 0); if d is not None: return d`；其后不变。

### 4.6 数据流（两路对照）
```
旧路: body_context→build_section→[_rewrite_begn_loops]→render_flow_dispatch(stmt_paras, render_body=build_skeleton,…) ─┐
新路: asg.build_asg→visit_Section→render_flow_dispatch(asg_paras, render_body=_render_para_body,…)                    ─┴→ 同装配同壳同 flow 副作用
段体内 GO TO/EXIT：旧 _sk_control / 新 visit_GotoStmt|visit_Leaf → dispatch_goto/dispatch_exit（同函数同 ctx）→ 逐字符一致
```

---

## 5. 比对闸：`--verb FLOW`

仿 24A `--verb PERFORMCALL`，新增 `FLOW` 比**段级状态机装配**：
- **legacy 采样** `_legacy_flows`：segmenter 切分 → 枚举每个 SECTION 的 paras，跑 `render_flow_dispatch`（render_body=`build_skeleton`），收 `(section_name, lines, flow_snapshot)`，fresh ctx，indent=0。
- **asg 采样** `_asg_flows`：遍历 ASG `Section`，跑 `visit_Section`（内部 `render_flow_dispatch`），收同三元组，fresh ctx。
- **比对**：状态机壳行 + 段体内 dispatch 行（`__pc/continue FLOW`、`break FLOW`）逐字符一致 **且** `flow_label`/`flow_paragraphs` 副作用一致（装配中途为 `"FLOW"`/labels，收尾复位）。
- **选样守界**：仅采**无 begn 循环**（避 24C 分流）且**段体动词均已迁**（MOVE/IF/GO/EXIT/EVALUATE/已迁 PERFORM；未迁动词会令 visitor 落 `// TODO-LEAF` 与旧路体不一致）的 SECTION。样本覆盖四形态：①回跳 → 状态机；②无跳转 → 扁平；③fall-through（段尾非 transfer，补 `__pc=next; continue`）；④段尾 transfer（GO/EXIT/GOBACK/STOP，不补 fall-through）。

---

## 6. 风险与回归

| 风险 | 控制 |
|---|---|
| `flow_label`/`flow_paragraphs` 副作用跨样污染 | 两路 fresh ctx；装配收尾必复位（沿旧 build_section 范式） |
| visitor 首引段级遍历改变既有语句级行为 | `visit_Section`/`visit_Paragraph` 纯新增；旧 `generic_visit` 拍平路径不再用于段级，但语句级 visit_* 零改；硬闸①旧路 156 测试零回归 |
| begn 循环 SECTION 两路分流被误判为 bug | 选样回避 + 设计显式声明（§3.2），24C 抹平 |
| `render_body` 时序（先设 flow_label 再渲染体）写错 → dispatch 行漂移 | 装配函数内严格「设副作用→渲染体→复位」；比对闸覆盖 fall-through/transfer 四形态 |
| ASG `collect_gotos`/`ends_transfer` 漏嵌套（IF/EVALUATE/PERFORM 体内 GO TO） | 比对闸含嵌套 GO TO 样本；与旧 `_collect_gotos` 递归口径对齐 |

**硬闸：**
- ①旧路径零影响：`python -m unittest test_translation` 全绿（当前 156）。
- ②config 快照零 diff：`scripts/regress_config_snapshot.py` before/after `[ZERO-DIFF OK]`。
- ③比对闸 FLOW：四形态样例两路壳 + dispatch + 副作用一致。

---

## 7. 新增/改动文件清单（🟢实测回填）

| 文件 | 动作 | 职责 / 实测 |
|---|---|---|
| `translator/skel/flow_dispatch.py` | 新建 | 段级 GO TO dispatch 状态机装配（`render_flow_dispatch`，路径中立+三回调）+ 单语句 dispatch 判定（`dispatch_goto`/`dispatch_exit`），**~50 逻辑行** |
| `translator/skel/context.py` | 改 | `SkelCtx` 扩 `flow_label`/`flow_paragraphs`（可写） |
| `translator/skel/__init__.py` | 改 | 导出 `render_flow_dispatch`/`dispatch_goto`/`dispatch_exit` |
| `translator/rules.py` | 改 | `build_section` 删状态机/扁平体 → 委托 `render_flow_dispatch`（保 `_rewrite_begn_loops`）；`_sk_control` GO/EXIT 委托 `dispatch_goto`/`dispatch_exit`；调用点零改 |
| `asg/visitor.py` | 改 | 新增模块级 `_ind`/`_asg_collect_gotos`/`_asg_ends_transfer` + `visit_Section`/`_render_para_body`（不单设 `visit_Paragraph`，决定 §2）；`visit_GotoStmt`/`visit_Leaf` 前置接 dispatch |
| `scripts/diff_asg_vs_legacy.py` | 改 | 扩 `--verb FLOW`（`_legacy_flows`/`_asg_flows`/`_flow_snapshot`/`_fill_legacy_leaves`，各建 fresh ctx 隔离 flow 副作用；旧路占位叶子按同一 `translate_leaf` 回填以对齐内联直译） |
| `test_translation.py` | 改 | 新增 `TestSkelFlowDispatch`（4 条：扁平/状态机/段尾 transfer/dispatch_goto·exit）+ `TestDiffAsgVsLegacyFlow`（1 条整程序两路全等 + 防退化断言） |
| `docs/架构索引/项目总览.md` | 改 | 同步 `skel/flow_dispatch.py` + visitor 段级入口 + 项4②进度 |

**硬闸实测**：①`unittest` `Ran 161 OK (skipped=2)`（迁前 156）；②config 快照 before/after 各 377 行 `[ZERO-DIFF OK]`；
③`--verb FLOW` 样例（回跳状态机 + 前向 GO TO dispatch + EXIT→break FLOW + 段尾 transfer + 扁平段，2 SECTION）两路
`(装配行, flow 复位快照)` 逐字符/逐项一致；`--verb CONTROL`/`MOVE` 回归仍 `[OK]`（证 `_sk_control` 委托无漂移）。

---

## 8. 开放点（待用户认可后固化）

1. **落点** `translator/skel/flow_dispatch.py`（§2/§3.2）。
2. **复用方式** 路径中立装配 + 三回调（§3.3）——非纯 token-based（节点类型异构）。
3. **visitor 首引段级入口** `visit_Section`/`visit_Paragraph`（§4.5）。
4. **begn 改写留旧 build_section**，visitor 本刀不做 → 含 begn SECTION 两路暂分流，比对选样回避（§3.2/§5）。
5. **比对闸** `--verb FLOW`，比壳 + dispatch 行 + flow 副作用（§5）。

> 用户 2026-06-26 认可 §2 五项；已按 §4 落地、§5/§6 自检通过（硬闸①②③全绿，见 §7 末）、本节与 §7 回填、架构索引同步。
> **后续刀**：24C（BEGN/READR/WRITE IO 形态 + struct_rebind）、24D（程序级装配 + cutover 删旧 token 路径）。
