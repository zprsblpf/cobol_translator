# 步骤18　项3 地基：混合全程序 JavaVisitor + 双路 diff 工具（甲案）

状态：🔶待认可（2026-06-26 设计）

上位路线：`架构演进-三相分层(预处理-ASG-visitor)初步设计.md` §5-项3「rules 逐类迁 visitor」。
本步是项3 的**第一刀**，只打地基、**不迁任何真动词**，零行为变化。

承接：步骤17（🟢已实现）只立了相2 ASG + 单点 `GotoJavaVisitor`，**吐不出整份 Java**。
项3 要逐类迁移、每迁一类逐字符比对旧路，前提是先让新路**能产出整份 Java** 且**有比对工具当回归闸**。

---

## 0. 已确认的决定（来自本轮对齐，落定不再问）

- [双路] 绞杀式**双路并存**：旧路（`segmenter→rules`）原封不动当黄金基准；新路（`相2 ASG→visitor`）单独长起来。✅
- [甲案] 新路全程序渲染碰到**未迁动词**时**回落旧 rules**（旧 rules 一行不改，纯只读复用）；迁完最后一类回落清零、旧路下线。✅
- [步骤18 边界] **只建地基、不迁真动词**：混合 visitor 此刻 100% 回落 → 新旧两路逐字符全等 → diff 工具立即成回归闸。第一个真动词（MOVE）迁移留**步骤19**。✅
- [范围纪律] 步骤18 不碰 §7-Q1/Q2/Q3（符号表判型、`_lift` 判定归一、THRU 归一），那些随具体动词迁移再定。✅

---

## 1. 目标 / 非目标

**目标**：
1. 新增**混合全程序 `JavaSectionVisitor`**：遍历相2 ASG，对每个 SECTION 产出 Java 方法体行；
   未迁动词（步骤18=全部）回落旧 `rules.build_section`，产物与旧路**逐字符一致**。
2. 新增**双路 diff 工具** `scripts/diff_dual_path.py`（参数化、保留为正式脚本）：
   对给定 `.cob`，逐 SECTION 渲染「旧路 vs 新路」两份方法体，逐字符比对，定位首个差异并给退出码。
3. 把「全等」断言纳入 `test_translation.py`（53→54+），diff 工具成**长期回归闸**。

**非目标（本步明确不做，留步骤19+）**：
- **不写任何真 `visit_<动词>`**：MOVE/IF/PERFORM/CALL/STRING 一律走回落，不在本步改写。
- **不改旧路任何文件**：`rules.py / segmenter.py / parser/ / config/` 零改（回归基准不动）。
- **不接全文件组装**（imports/字段声明/postprocess）：比对**粒度=SECTION 方法体**，即 `build_section`
  的产出面——动词迁移正发生在这里，比对它即可精确归因；全文件级组装是后续事。

---

## 2. 命门：为什么回落粒度是 SECTION（设计依据）

实测旧路 `rules.build_section(paras, ctx)`（rules.py:1040）内部先 `_rewrite_begn_loops(paras, ctx)`
做**跨语句融合**（BEGN→for-each、READR/WRITE single 把**相邻多条 Stmt 合成一段**）。结论：

- **逐节点回落无法逐字符复刻**：融合是 section 级、跨多条语句的，单条节点回落拿不到上下文。
- **相2 ASG 已丢源 `Stmt`**：`builder._lift` 只留 `raw/tokens`，旧 rules 要的 `Stmt`（含 `kind/children/whens`）没了。

故步骤18 回落桥取**SECTION 级**：新路对一个未迁 SECTION，整段回落 `build_section`，输入用**回落桥保留的源 paras**。
此粒度下「新路 = 调同一个 `build_section`、喂同一份 paras」⇒ 产物**按构造逐字符全等**——
这恰好验证了**遍历骨架 + 段产物拼接**与旧路逐字节一致，从而步骤19 迁 MOVE 后任何 diff 都**只能**归因于 MOVE 改写。

> 回落粒度未来随迁移自然收窄（SECTION→段→单句）；BEGN/READR 这类融合类动词迁得最晚、回落最久。本步不展开。

---

## 3. 回落桥：源 paras 怎么留

最小改动、零重建风险方案——**builder 把源 paras 顺手挂到 Section 节点**（只读快照，不重建 Stmt）：

- `asg/nodes.py`：`Section` 增字段 `src_paras: list = field(default_factory=list)`
  （元素＝`(label, list[Stmt])`，即旧 `build_section` 的入参形态）。
- `asg/builder.py::build`：每 SECTION 在 `split_paragraphs→segment` 时**额外收**一份
  `src_paras=[(lbl, segment(body)) for lbl, body in split_paragraphs(s.lines)]` 挂到 `Section`。
  （segment 本就在跑，这里只是把结果同时留一份；旧逻辑不变。）

**为何不重建 Stmt**：从类型节点反推 `Stmt`（kind/children/whens 全要精确复原）极脆、易破坏逐字符一致；
保留源快照 O(1) 改动、零风险，符合「复用优先」。绞杀完成、回落清零后该字段自然废弃。

---

## 4. 新增类与方法（职责 + 设计思路）

### 4.1 `asg/java_visitor.py`（新文件，瘦）—— 混合全程序翻译 visitor

> 单独成文件（不塞进 `visitor.py`，后者＝基类+goto demo），符合「单文件小而专」。

- **`class JavaSectionVisitor(AsgVisitor)`**：混合全程序方法体渲染。
  - `__init__(self, ctx)`：持旧路 `rules.Ctx`（类型/命名/IO 上下文，复用旧路 `build_body_ctx` 产出）。
  - `render_section(self, section) -> list[str]`：渲染一个 SECTION 的方法体行。
    - **步骤18 实现**：`return _rules.build_section(section.src_paras, self.ctx)`（整段回落）。
    - **设计思路**：方法体是**唯一**的"已迁/未迁"决策点；步骤19 起在此按节点分派——
      已迁动词走 `self.visit(node)`，残余仍交 `build_section`。本步只占位回落，结构留给后续长。
  - `render_program(self, program) -> dict[str, list[str]]`：遍历 `program.sections`，
    `{section.name: render_section(s)}`。只编排、不放逻辑。

### 4.2 `scripts/diff_dual_path.py`（新文件，瘦入口）—— 双路逐段 diff 工具

模块 docstring 写明：用途（绞杀期回归闸）、对应设计（本文）、用法 `python -m scripts.diff_dual_path X.cob`。

- **`render_old(program, ctx) -> dict[str, list[str]]`**：旧路基准——
  复用 `body_context` 既有逻辑，逐 SECTION `_rules.build_section(paras, ctx)`，得 `{name: lines}`。
- **`render_new(program, ctx) -> dict[str, list[str]]`**：新路——`build_asg(program)` 后
  `JavaSectionVisitor(ctx).render_program(asg)`。
- **`diff(old, new) -> list[str]`**：逐 SECTION 比对两份行，**逐字符**定位首个差异
  （段名 + 行号 + 列号 + 旧/新片段）；全等返回空。
- **`main(argv)`**：参数解析（cob 路径，可选 `--section`）→ 建 program+ctx（复用旧路 `build_body_ctx`）
  → render_old / render_new → diff → 打印结果，**全等 exit 0、有差异 exit 1**。

### 4.3 `test_translation.py`：`class TestDualPathEquivalence`

- `test_dual_path_char_identical`：拿步骤17 同款内联 cob（5 SECTION）建 program+ctx，
  断言 `render_old == render_new`（逐段逐字符全等）。**这是步骤18 的核心验收**，也防回归。

---

## 5. 调用关系（数据流）

```
diff_dual_path.main(X.cob)
   │  复用旧路（只读）：parser.parse → body_context.build_body_ctx → (program, ctx)
   ├─ render_old:  for s in program.sections: rules.build_section(s.paras, ctx)      ── 黄金基准
   └─ render_new:  asg.build_asg(program) → JavaSectionVisitor(ctx).render_program
                        └─ render_section(sec) → [步骤18] rules.build_section(sec.src_paras, ctx)
   → diff(old,new) 逐字符 → 步骤18 必全等 (exit 0)
```

新增/改动文件：
| 文件 | 动作 | 一句话职责 |
|---|---|---|
| `asg/nodes.py` | 改（+1 字段） | `Section.src_paras` 源快照，回落桥 |
| `asg/builder.py` | 改（+1 行收集） | build 时顺手挂 `src_paras`，旧逻辑不变 |
| `asg/java_visitor.py` | **新** | 混合全程序 `JavaSectionVisitor`，未迁动词回落 `build_section` |
| `asg/__init__.py` | 改（导出） | 暴露 `JavaSectionVisitor` |
| `scripts/diff_dual_path.py` | **新** | 双路逐段逐字符 diff 工具（回归闸） |
| `test_translation.py` | 改（+1 类） | `TestDualPathEquivalence` 全等断言 |

**零改**：`translator/rules.py`、`segmenter.py`、`parser/`、`config/`、旧 `asg/visitor.py`（`GotoJavaVisitor` 不动）。

---

## 6. 验收清单（落地后逐项自检）

1. `python -m scripts.diff_dual_path <样例.cob>` → **exit 0**，逐段无差异。
2. `python -m unittest test_translation -v` → 原 53 全过 + `test_dual_path_char_identical` 过（≥54，0 回归）。
3. `scripts/regress_config_snapshot.py` → exit 0（旧路快照不变，证明旧路零改）。
4. `asg/java_visitor.py` 逻辑行 ≤ ~100；`diff_dual_path.py` 为瘦入口（解析+编排，无业务逻辑）。

---

## 7. 开放问题（留步骤19+，本步不决）

- **Q1**：步骤19 迁 MOVE 时，回落粒度从 SECTION 收窄到「单句节点 + 残余段回落」的具体切法（BEGN 融合段怎么绕开）。
- **Q2**：全文件级（imports/字段声明/postprocess）双路比对是否要做、何时做——目前只比 SECTION 方法体。
- **Q3**：diff 工具是否纳入 `main.py` 子命令对外暴露（现仅 `scripts/` 直跑）。
