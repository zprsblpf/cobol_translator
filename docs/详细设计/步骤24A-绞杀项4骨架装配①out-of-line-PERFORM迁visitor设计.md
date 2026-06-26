# 步骤24A　绞杀项4 骨架装配①：out-of-line PERFORM（含 THRU 合成区间 + proc_order 路由）迁 visitor

状态：🟢已实现（2026-06-26；设计 🔶→✅认可→🟢落地，实测见 §7 与操作记录）
对应上位路线：`架构演进-三相分层(预处理-ASG-visitor)初步设计.md` §5-项4「下线旧 token 路径」。
本刀是**项4 的第一刀**（四刀分期 24A/B/C/D 已与用户对齐，见 §2 已确认的决定）。
操作记录：`../操作记录/步骤24A-绞杀项4骨架装配①out-of-line-PERFORM迁visitor操作记录.md`。

---

## 1. 背景与本刀边界（Why + 不做什么）

绞杀项3（步骤18–23）已把**所有有旧确定性译器的叶子动词**迁进 `translator/leaf/`，旧/新两路共用同一份纯函数 → 逐字符一致。但旧 `rules.py`（1103 行）里**叶子翻译只占一半**，另一半是**骨架装配层**，新路 `LeafJavaVisitor` 完全没有，故新路尚产不出与正本（`skeleton_gen.body_context` → `rules.build_section`）逐字符一致的整份程序，**不能直接下线旧 token 路径**。项4 因此拆四刀自底向上补齐骨架装配，最后一刀才真正 cutover+删除。

**本刀（24A）只切骨架装配的第一块：out-of-line PERFORM 的调用体生成**——即旧 `_sk_perform` 在 `st.children` 为空、走 `target` 分支时调用的 `_perform_range` 及其下属 `_perform_single_paragraph` / `_perform_range_paragraph`，连同它们对 `ctx.pending_range_methods` 的**合成区间方法登记**。迁移后 `visit_PerformStmt` 的 out-of-line 分支由现在的 `// TODO-PERFORM-CALL` 占位改为产出与旧路逐字符一致的 `this.xxx();` / THRU 区间展开 / 合成区间方法调用。

**本刀明确不做（守界，留后续刀）：**
- ② GO TO dispatch 状态机（`flow_label`/`__pc`/`continue FLOW`）—— 留 **24B**。
- ③ BEGN/NEXTR foreach、BEGN/READR/WRITE 单次 IO 形态识别 + `struct_rebind`（`_rewrite_begn_loops` 一族 ~600 行）—— 留 **24C**。
- ④ 程序级装配 + `body_context` 改吃 visitor + 删旧 `build_section`/segmenter token 通道 —— 留 **24D**（真·下线）。
- 合成区间方法的**渲染落地**（`pending_range_methods` 在 `render_skeleton` 收尾 drain 成类级方法）—— 那是渲染期编排，本刀只需保证**登记的副作用与旧路一致**，drain 仍由现有 `render_skeleton` 负责，不动。
- inline PERFORM（`st.children` 非空）—— 循环壳已在步骤20迁完，body 递归直译亦已在 visitor，本刀不碰。

---

## 2. 已确认的决定（待用户认可后固化）

- [分期] 项4 拆 24A/B/C/D 四刀自底向上，最后一刀 cutover+删除。✅（2026-06-26 用户认可）
- [本刀范围] 只迁 out-of-line PERFORM 调用体（`_perform_range` 三件套 + `pending_range_methods` 登记）。✅
- [复用方式] **token-based 原样迁址**：抽出的公用函数仍以 header token + ctx 为输入（与旧 `_perform_range` 同签名同逻辑，零改），旧 `_sk_perform` 与 `visit_PerformStmt` 共调 → 逐字符一致。**不**改走 ASG 已解析的 `PerformStmt.target/thru`/`resolve_thru`（理由见 §3.3）。✅
- [落点] 新建**相3 骨架装配公用底座**目录 `translator/skel/`（与 `translator/leaf/` 平行），本刀落 `translator/skel/perform_call.py`。✅
- [ctx 契约] 新增窄协议 `SkelCtx`（在 `translator/skel/context.py`），声明骨架装配读取的字段（`proc_order`/`section_order`/`known_sections`/`section_to_method`/`pending_range_methods`）；**不**污染 `LeafCtx`。`rules.Ctx` 与 `body_context` 产物 duck-type 满足之。✅
- [比对闸] `scripts/diff_asg_vs_legacy.py` 扩 `--verb PERFORMCALL`：比对 out-of-line PERFORM 的**调用体行** + **pending_range_methods 登记副作用**。✅

---

## 3. 探查结论与关键设计抉择（留痕）

### 3.1 旧路 out-of-line PERFORM 调用链（`rules.py`）

```
_sk_perform(st)                         # 884 行起
  ├ _perform_loop(...)                  # 循环壳，已迁 leaf.loop（步骤20），本刀不动
  ├ st.children 非空  → build_skeleton  # inline，本刀不动
  └ target 非空       → _perform_range(header, hu, target, ctx, inner_indent)   ← 本刀迁这条
        ├ 无 THRU → _perform_single_paragraph(target, ctx, indent)
        │     ├ target ∈ known_sections          → ["this.<m>();"]
        │     ├ proc_order 中唯一 paragraph 且不撞段方法名
        │     │     → 登记 pending_range_methods[mname]=[(target, body)]，返 ["this.pXxx();"]
        │     └ 兜不住                            → ["// TODO 单条 PERFORM…", "this.pXxx();"]
        ├ THRU 且 a,b 均已知 SECTION 且 b 在 a 后 → 按 section_order 展开每段 ["this.<s>();" …]
        ├ THRU paragraph 级 → _perform_range_paragraph(a, b, ctx, indent)
        │     ├ proc_order 解析 [a..b] 闭区间，两端各唯一、b 在 a 后、无畸形单元
        │     │     → 登记 pending_range_methods[mname]=[(label, body) …]，返 ["// PERFORM…", "this.aThruB();"]
        │     └ 否则 → None（交回 ③ TODO 退化）
        └ ③ 端点缺失/区间不定 → ["// TODO PERFORM a THRU b…", "this.<m>();"]
```

### 3.2 落点：为何新建 `translator/skel/` 而非塞进 `leaf/`

`_perform_range` 是**骨架装配**（解析过程拓扑、登记类级合成方法），不是"叶子动词翻译"。塞进 `leaf/` 会撑破 `leaf` 的语义（"单条语句 → Java 片段，无程序级副作用"）。故仿 `leaf/` 另起平行底座 `translator/skel/`（skeleton-assembly 公用层），本刀落 `perform_call.py`，后续 24B/24C 的状态机、IO 形态可续落同目录。**备选**：落 `leaf/perform_call.py`（省一个目录，但语义混淆）——不推荐。

### 3.3 复用方式：为何 token-based 而非 ref-based

ASG 侧 `PerformStmt` 已带**已解析**的 `target: ProcRef` / `thru: ProcRef`，`ProcRegistry.resolve_thru` 也能一次算清 [a..b] 区间——理论上更干净。但：
1. `resolve_thru` 返回的 `ProcUnit` 只有 `(name, kind, section, order)`，**不带段体 body**；而 `pending_range_methods` 登记**需要带标签的段体序列** `[(label, body), …]`（旧 `_perform_range_paragraph` 取 `proc_order` 四元的 `u[3]`）。改走 ref 需先给 `ProcUnit`/`resolve_thru` 补 body 字段——扩面、且偏离"逐字符一致最小风险"。
2. 绞杀前 6 刀的成功范式都是**原样迁址、token-based、两路共调同函数**。本刀沿用：抽出的 `perform_call.*` 仍吃 `(header, hu, target, ctx, indent)`，逻辑与旧 `_perform_range` 零改；旧 `_sk_perform` 与新 `visit_PerformStmt` 都把 `node.header`/`st.tokens` 传进去 → 天然逐字符一致。
3. ref-based 清洗（让 visitor 直接消费 `resolve_thru`、`ProcUnit` 带 body）属**可选精炼**，可在 24D cutover 后单独做，不绑死本刀。

→ **本刀 token-based**。visitor 的 out-of-line 分支改为 `perform_call.render_perform_call(node.header, hu, target, ctx, 0)`，与旧路同函数。

### 3.4 ctx 契约：新增 `SkelCtx` 窄协议

`perform_call` 读取的 ctx 字段：`proc_order`（四元，带 body）、`section_order`、`known_sections`、`section_to_method`（callable）、`pending_range_methods`（可写 dict）。其中 `pending_range_methods` 是**程序级可写状态**——`LeafCtx` 的 docstring 明令"不依赖 rules.Ctx 的 skeleton 层状态"，故**不扩 LeafCtx**，另声明 `translator/skel/context.py::SkelCtx`（Protocol）。`rules.Ctx`（已有全部字段）与 `body_context.build_body_ctx` 产物（同为 `rules.Ctx`）duck-type 满足之。visitor 侧 ctx 即 `body_context` 产的 `rules.Ctx`，本就携带这些字段 → 直接可用。

> 注：`section_to_method` / `known_sections` 已在 `LeafCtx`（步骤23 扩入），此处在 `SkelCtx` 重声明以自洽；`proc_order`/`section_order`/`pending_range_methods` 为 `SkelCtx` 新增。

---

## 4. 详细设计：类/方法/数据流

### 4.1 新文件 `translator/skel/__init__.py`
瘦门面：导出 `SkelCtx`、`render_perform_call`（+ 后续刀的导出）。仿 `leaf/__init__.py`。

### 4.2 新文件 `translator/skel/context.py`
```python
class SkelCtx(Protocol):
    proc_order: list                 # [(name, kind, section, body_lines), …]（带段体，THRU 合成区间登记用）
    section_order: list              # 全程序 SECTION 名顺序（大写）——SECTION 级 THRU 展开用
    known_sections: set              # 所有 SECTION 名（大写）
    section_to_method: object        # callable: 段/paragraph 名 → java 方法名
    pending_range_methods: dict      # 可写：合成区间方法登记表 {方法名: [(label, body), …]}
```

### 4.3 新文件 `translator/skel/perform_call.py`
把旧 `rules._perform_range` / `_perform_single_paragraph` / `_perform_range_paragraph` **原样迁址**（逻辑零改，仅 ctx 注解 `rules.Ctx → SkelCtx`，`_proc_call`/`_ind` 随迁或从 rules 复用）。对外暴露统一入口：

```python
def render_perform_call(header: list[str], hu: list[str], target: str,
                        ctx: SkelCtx, indent: int) -> list[str]:
    """out-of-line PERFORM 的调用体（= 旧 _perform_range，零改）。
    无 THRU→单段/合成单单元；SECTION 级 THRU→按 section_order 展开；
    paragraph 级 THRU→proc_order 解析+登记合成区间方法；兜不住→TODO 退化。"""
```

迁随的私有助手：`_render_single`(=`_perform_single_paragraph`)、`_render_range_paragraph`(=`_perform_range_paragraph`)、`_proc_call`、`_ind`。命名正本 `spec_loader.perform_range_method` 调用照搬。

### 4.4 改 `translator/rules.py`（委托，调用点零改）
- 顶部 `from translator.skel import render_perform_call`。
- 删除 `_perform_range` / `_perform_single_paragraph` / `_perform_range_paragraph` 函数体，改为**别名再导回**保 `rules.*` 公开面（若有外部/测试引用），或直接让 `_sk_perform` 的 `target` 分支调 `render_perform_call(header, hu, target, ctx, inner_indent)`。`_proc_call` 若仍被 rules 其它处用则保留一份或从 skel 再导入。
- `_sk_perform` 其余（循环壳、inline 分支）零改。

### 4.5 改 `asg/visitor.py`（`visit_PerformStmt` out-of-line 分支接线）
现状（visitor.py:139-141）out-of-line 落 `// TODO-PERFORM-CALL`。改为：
```python
elif node.target:
    hu = [h.upper() for h in node.header]
    target = node.target.name          # 已是大写过程名
    body = render_perform_call(node.header, hu, target, self.ctx, 0)
```
`self.ctx` 即 `body_context` 产的 `rules.Ctx`（满足 SkelCtx）。indent 传 0，外层 `_body` 施加缩进（与现有 visitor body 缩进范式一致；比对在 indent 0，见 §5）。

> 注：`node.target.name` 等价旧 `header[0].upper()`（builder `_lift` 时 `target=registry.resolve(header[0])`）；THRU 端点 `b` 仍由 `render_perform_call` 内部从 `header` 的 `THRU` 后一 token 取（token-based，与旧路同源），**不**走 `node.thru`，确保两路解析同源。

### 4.6 数据流（两路对照）
```
旧路:  body_context → rules.build_section → _sk_perform(target分支) → render_perform_call(header,…,ctx) ─┐
新路:  asg.build_asg → visit_PerformStmt(target分支) → render_perform_call(node.header,…,ctx)            ─┴→ 同函数同ctx → 逐字符一致 + 同一 pending_range_methods 副作用
```

---

## 5. 比对闸：`--verb PERFORMCALL`

仿现有 `--verb PERFORM`（步骤20，比循环壳），新增 `PERFORMCALL` 比 **out-of-line 调用体**：
- **legacy 采样** `_legacy_perform_calls`：segmenter 切分树枚举每条**无 inline body 且有 target**的 PERFORM，跑旧 `_sk_perform` 的 target 分支（或直接 `render_perform_call`），收 `(raw, lines, pending_snapshot)`，indent=0。
- **asg 采样** `_asg_perform_calls`：遍历 ASG `PerformStmt`，对 `not inline_body and target` 者跑 `render_perform_call(node.header,…,0)`，收同三元组。
- **比对**：调用体行逐字符一致 **且** 两路对 `pending_range_methods` 的登记（key + 带标签段体序列）一致。为隔离副作用，两路各用**全新 ctx**（同一 program 重建）或跑前 deep-copy `pending_range_methods` 比对增量。
- 容器节点（IF/EVALUATE/inline PERFORM 体内的嵌套 out-of-line PERFORM）由基类 `generic_visit` 递归捕获，源码序对齐。

---

## 6. 风险与回归

| 风险 | 控制 |
|---|---|
| `pending_range_methods` 副作用在比对中相互污染 | 两路各用独立 ctx / 增量快照比对（§5） |
| 迁址遗漏 `_proc_call`/`_ind`/`spec_loader` 依赖 | 原样迁址、import 显式接线；硬闸①旧路 151 测试零回归 |
| visitor indent 与旧路 inner_indent 不一致 | 比对统一 indent=0（沿用步骤20 范式）；真实缩进由各路外层施加，cutover（24D）再统一校 |
| `node.target.name` 与 `header[0].upper()` 偏差 | builder `_lift` 已用 `resolve(header[0])`，name 即大写首 token；THRU 端点仍 token-based 取，两路同源 |

**硬闸：**
- ①旧路径零影响：`python -m unittest test_translation` 全绿（当前 151，迁后含新增）。
- ②config 快照零 diff：`scripts/regress_config_snapshot.py` before/after `[ZERO-DIFF OK]`。
- 比对闸 PERFORMCALL：内联含 SECTION 级 THRU / paragraph 级 THRU / 单条 paragraph / 兜不住 TODO 四形态的程序，两路调用体 + 登记一致。

---

## 7. 新增/改动文件清单（🟢实测回填）

| 文件 | 动作 | 职责 / 实测 |
|---|---|---|
| `translator/skel/__init__.py` | 新建 | 相3 骨架装配公用底座门面（导出 `SkelCtx`/`render_perform_call`） |
| `translator/skel/context.py` | 新建 | `SkelCtx` 窄协议（5 字段） |
| `translator/skel/perform_call.py` | 新建 | out-of-line PERFORM 调用体（`_perform_range` 三件套迁址，**~76 逻辑行**） |
| `translator/rules.py` | 改 | 删四函数体 → 别名导回 `_perform_range`/`_perform_single_paragraph`/`_perform_range_paragraph`/`_proc_call`；`_sk_perform` 调用点零改 |
| `asg/visitor.py` | 改 | `visit_PerformStmt` out-of-line 分支接 `render_perform_call`（token-based，`node.target.name`） |
| `scripts/diff_asg_vs_legacy.py` | 改 | 扩 `--verb PERFORMCALL`（`_legacy_perform_calls`/`_PerformCallCollector`/`_asg_perform_calls` + `_pending_snapshot`，各建 fresh ctx 隔离副作用） |
| `test_translation.py` | 改 | 两旧占位用例转正为 `*_migrated`；新增 `TestSkelPerformCall`（4 条）+ `TestDiffAsgVsLegacyPerformCall`（1 条） |
| `docs/架构索引/项目总览.md` | 改 | 同步相3 骨架装配底座 `translator/skel/` + 项4①进度 |

**硬闸实测**：①`unittest` `Ran 156 OK (skipped=2)`（迁前 151）；②config 快照 before/after 各 377 行 `[ZERO-DIFF OK]`；
比对闸 `PERFORMCALL` 样例 3 条（paragraph 合成 / 单段 SECTION / SECTION 级 THRU 展开）两路 `(调用体, pending)` 逐字符/逐项一致。

---

## 8. 开放点处置（✅已落，留痕）

1. **落点**：✅ `translator/skel/`（§3.2）。
2. **ctx 契约**：✅ 新 `SkelCtx` 协议（§3.4）。
3. **复用方式**：✅ token-based 原样迁址（§3.3）。
4. **比对闸**：✅ `--verb PERFORMCALL`，比"调用体行 + pending 登记副作用"（§5）。

> 用户 2026-06-26 认可四项推荐；已按 §4 落地、§5/§6 自检通过、本节与 §7 回填，架构索引同步。
> **后续刀**：24B（GO TO dispatch 状态机）、24C（BEGN/READR/WRITE IO 形态 + struct_rebind）、24D（程序级装配 + cutover 删旧 token 路径）。
