# T18 Stage Closeout And Mainline Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the current T10-T17 development batch into a documented, reproducible, commit-ready state before adding new translator features.

**Architecture:** Do not change translation behavior unless a verification inconsistency is found. Add a stage closeout document that maps each task to files, tests, and verification suites, then make `scripts/check.py` and the docs agree on what `quick`, `leaf`, `asg`, and `all` mean. Finish by running the project gates and recording the exact result.

**Tech Stack:** Python `unittest`, existing `scripts/check.py` verification runner, Markdown project docs.

---

### Task 1: Add Stage Closeout Checklist

**Files:**
- Create: `docs/操作记录/T18-阶段收口与主线准入加固.md`
- Read: `docs/操作记录/T10-T12-control-flow.md`
- Read: `docs/操作记录/T13-T14-ws-field-view.md`
- Read: `docs/操作记录/T15-ASG-fallback-observability.md`
- Read: `docs/操作记录/T16-deterministic-report-output.md`
- Read: `docs/操作记录/T17-文档状态同步操作记录.md`
- Read: `scripts/check.py`

- [x] **Step 1: Write the closeout document shell**

Create `docs/操作记录/T18-阶段收口与主线准入加固.md` with this content:

````markdown
# T18 阶段收口与主线准入加固

## 目标

把当前 T10-T17 开发批次收口为可审查、可复验、可提交的状态。T18 不新增 COBOL 翻译功能，只同步文档、验收入口和提交前检查。

## 范围

- 盘点 T10-T17 对应的代码、测试、文档和验收入口。
- 确认 `scripts/check.py --suite quick|leaf|asg|all` 与 `docs/运行验收.md` 描述一致。
- 记录提交前必须通过的验证命令。
- 记录当前工作区还有哪些文件属于本批次。

## 不在范围

- 不迁移新的 COBOL 动词。
- 不调整 ASG/visitor 产物语义。
- 不删除 legacy fallback。
- 不引入 LLM、MongoDB、Chroma 或外部服务依赖。

## 批次任务索引

| 任务 | 主要文件 | 验收入口 | 状态 |
|---|---|---|---|
| T10-T12 control-flow | `asg/builder.py`, `asg/section_visitor.py`, `asg/visitor.py`, `translator/leaf/control.py`, `translator/leaf/expr.py`, `test_t10_t12_control_flow.py` | `python scripts/check.py --suite asg` | 待复验 |
| T13-T14 WS field view | `translator/naming.py`, `translator/wsaa/render_class.py`, `translator/wsaa/render_view.py`, `test_t13_t14_ws_views.py` | `python scripts/check.py --suite leaf` | 待复验 |
| T15 ASG fallback observability | `translator/rules.py`, `translator/skeleton_gen/body_context.py`, `test_translation.py`, `scripts/check.py` | `python scripts/check.py --suite asg` | 待复验 |
| T16 deterministic report output | `scripts/deterministic_report.py`, `translator/skeleton_gen/render_skeleton.py`, `test_t16_deterministic_report.py`, `scripts/check.py` | `python scripts/check.py --suite quick` | 待复验 |
| T17 docs status sync | `docs/架构索引/项目总览.md`, `docs/运行验收.md`, `docs/翻译标准/*.md` | `rg -n "T15|T16|VERB_MATRIX|quick\\|leaf\\|asg\\|all" docs -S` | 待复验 |

## 主线准入命令

```powershell
python scripts/check.py --suite quick
python scripts/check.py --suite leaf
python scripts/check.py --suite asg
python scripts/check.py
```

## 验证记录

| 命令 | 结果 |
|---|---|
| `python scripts/check.py --suite quick` | 待记录 |
| `python scripts/check.py --suite leaf` | 待记录 |
| `python scripts/check.py --suite asg` | 待记录 |
| `python scripts/check.py` | 待记录 |

## 提交前检查

- `git status --short` 中的 T10-T17/T18 文件均已确认属于当前批次。
- 无临时输出文件被纳入提交。
- `docs/superpowers/plans/2026-07-02-t18-stage-closeout-mainline-gate.md` 的任务状态已同步。
````

- [x] **Step 2: Check the document exists**

Run: `Get-Content -LiteralPath 'docs/操作记录/T18-阶段收口与主线准入加固.md'`

Expected: the file prints the T18 goal, scope, batch task index, and mainline gate commands.

- [x] **Step 3: Commit checkpoint**

Do not commit yet if the user wants one combined commit for T10-T18. If committing per task is approved, run:

```powershell
git add docs/操作记录/T18-阶段收口与主线准入加固.md
git commit -m "docs: add T18 stage closeout checklist"
```

Expected: commit succeeds.

### Task 2: Align Verification Suite Documentation

**Files:**
- Modify: `docs/运行验收.md`
- Modify: `docs/翻译标准/确定性验收.md`
- Read: `scripts/check.py`

- [x] **Step 1: Verify current suite definitions**

Run:

```powershell
python -c "from scripts.check import SUITES; [print(name, len(SUITES[name])) or [print('  ' + ' '.join(cmd[1:])) for cmd in SUITES[name]] for name in ('quick', 'leaf', 'asg', 'all')]"
```

Expected:
- `quick` contains py_compile, `test_smoke`, `test_t16_deterministic_report`, and `main.py --parse-only`.
- `leaf` contains leaf tests plus `test_t13_t14_ws_views`.
- `asg` contains ASG visitor tests, `TestMainlineSectionViaAsg`, and `test_t10_t12_control_flow`.
- `all` contains py_compile, full unittest, parse-only, skeleton generation, and no-LLM translation.

- [x] **Step 2: Update `docs/运行验收.md` if needed**

Ensure the grouped verification section explicitly says:

```markdown
- `quick`: smoke、T16 deterministic report、最小 COBOL parse-only。
- `leaf`: 统一 leaf 入口、STRING/UNSTRING/INSPECT/SEARCH、算术赋值、CALL、T13-T14 WS field view。
- `asg`: ASG/visitor、diff 工具主线样本、T10-T12 control-flow、T15 fallback observability。
- `all`: 默认完整本地准入，包含全量 unittest、最小 COBOL parse-only、skeleton generation、no-LLM translation。
```

- [x] **Step 3: Update `docs/翻译标准/确定性验收.md` if needed**

Ensure deterministic acceptance says:

```markdown
主线准入以 `python scripts/check.py` 为准；分组回归入口用于开发中缩小范围。T15 fallback observability 归属 `asg`，T16 deterministic report 归属 `quick`，T13-T14 WS field view 归属 `leaf`，T10-T12 control-flow 归属 `asg`。
```

- [x] **Step 4: Run documentation grep**

Run: `rg -n "quick|leaf|asg|all|T10|T13|T15|T16|fallback|deterministic" docs/运行验收.md docs/翻译标准/确定性验收.md -S`

Expected: output includes all four suite names and T10/T13/T15/T16 ownership text.

- [x] **Step 5: Commit checkpoint**

Do not commit yet if the user wants one combined commit for T10-T18. If committing per task is approved, run:

```powershell
git add docs/运行验收.md docs/翻译标准/确定性验收.md
git commit -m "docs: align verification suite ownership"
```

Expected: commit succeeds.

### Task 3: Verify Batch File Ownership

**Files:**
- Modify: `docs/操作记录/T18-阶段收口与主线准入加固.md`
- Read: current git status

- [x] **Step 1: Capture changed files**

Run: `git status --short`

Expected: changed files are limited to the current T10-T18 batch, docs, tests, and verification scripts. Generated output under `output/` must not appear.

- [x] **Step 2: Update T18 closeout with ownership list**

Append this section to `docs/操作记录/T18-阶段收口与主线准入加固.md`, replacing the bullet list with the actual grouped file names from `git status --short`:

```markdown
## 工作区文件归属

### T10-T12 control-flow

- `asg/builder.py`
- `asg/section_visitor.py`
- `asg/visitor.py`
- `translator/leaf/control.py`
- `translator/leaf/expr.py`
- `test_t10_t12_control_flow.py`
- `docs/操作记录/T10-T12-control-flow.md`

### T13-T14 WS field view

- `translator/naming.py`
- `translator/wsaa/render_class.py`
- `translator/wsaa/render_view.py`
- `test_t13_t14_ws_views.py`
- `docs/操作记录/T13-T14-ws-field-view.md`

### T15 fallback observability

- `translator/rules.py`
- `translator/skeleton_gen/body_context.py`
- `test_translation.py`
- `docs/操作记录/T15-ASG-fallback-observability.md`
- `docs/superpowers/plans/2026-07-02-t15-asg-fallback-observability.md`

### T16 deterministic report

- `scripts/deterministic_report.py`
- `translator/skeleton_gen/render_skeleton.py`
- `test_t16_deterministic_report.py`
- `docs/操作记录/T16-deterministic-report-output.md`
- `docs/翻译标准/确定性验收.md`

### T17 documentation sync

- `docs/架构索引/项目总览.md`
- `docs/运行验收.md`
- `docs/翻译标准/变量定义.md`
- `docs/翻译标准/流程结构.md`
- `docs/操作记录/T17-文档状态同步操作记录.md`

### T18 closeout

- `docs/操作记录/T18-阶段收口与主线准入加固.md`
- `docs/superpowers/plans/2026-07-02-t18-stage-closeout-mainline-gate.md`
```

- [x] **Step 3: Check for unowned files**

Run: `git status --short`

Expected: every changed file is represented in the T18 ownership list. If a file is unrelated, stop and ask the user whether to exclude it.

- [x] **Step 4: Commit checkpoint**

Do not commit yet if the user wants one combined commit for T10-T18. If committing per task is approved, run:

```powershell
git add docs/操作记录/T18-阶段收口与主线准入加固.md
git commit -m "docs: record T10-T18 batch ownership"
```

Expected: commit succeeds.

### Task 4: Run Mainline Gates And Record Results

**Files:**
- Modify: `docs/操作记录/T18-阶段收口与主线准入加固.md`

- [x] **Step 1: Run quick gate**

Run: `python scripts/check.py --suite quick`

Expected: exit code 0.

- [x] **Step 2: Run leaf gate**

Run: `python scripts/check.py --suite leaf`

Expected: exit code 0.

- [x] **Step 3: Run ASG gate**

Run: `python scripts/check.py --suite asg`

Expected: exit code 0.

- [x] **Step 4: Run default all gate**

Run: `python scripts/check.py`

Expected: exit code 0. Local vLLM tests may be skipped when `http://localhost:8000` is unavailable.

- [x] **Step 5: Record exact verification results**

Update the verification table in `docs/操作记录/T18-阶段收口与主线准入加固.md` with the observed results. Use this format:

```markdown
| `python scripts/check.py --suite quick` | PASS |
| `python scripts/check.py --suite leaf` | PASS |
| `python scripts/check.py --suite asg` | PASS |
| `python scripts/check.py` | PASS; full unittest reported 246 tests, 2 skipped when local vLLM was unavailable |
```

- [x] **Step 6: Commit checkpoint**

Do not commit yet if the user wants one combined commit for T10-T18. If committing per task is approved, run:

```powershell
git add docs/操作记录/T18-阶段收口与主线准入加固.md
git commit -m "docs: record T18 verification results"
```

Expected: commit succeeds.

### Task 5: Final Commit-Readiness Review

**Files:**
- Modify: `docs/superpowers/plans/2026-07-02-t18-stage-closeout-mainline-gate.md`
- Read: current git status and diff

- [x] **Step 1: Mark completed plan steps**

Update this plan file by changing each completed checkbox from `[ ]` to `[x]`.

- [x] **Step 2: Review diff summary**

Run: `git diff --stat`

Expected: diff only includes T10-T18 code, tests, docs, and verification scripts. No generated Java output, logs, cache, virtualenv, or local config files should appear.

- [x] **Step 3: Review status**

Run: `git status --short --branch`

Expected: branch is `master` or the user's chosen working branch, and all changed files are intentional.

- [x] **Step 4: Present commit options**

Report the verification evidence and ask the user to choose:

```text
T10-T18 is commit-ready. Choose one:
1. Create one combined commit for the whole batch.
2. Create topic commits grouped by T10-T12, T13-T14, T15, T16, T17-T18.
3. Leave the worktree uncommitted for manual review.
```

- [ ] **Step 5: Commit only after user chooses**

If the user chooses a combined commit, run:

```powershell
git add asg/builder.py asg/section_visitor.py asg/visitor.py scripts/check.py scripts/deterministic_report.py scripts/diff_asg_vs_legacy.py test_translation.py test_t10_t12_control_flow.py test_t13_t14_ws_views.py test_t16_deterministic_report.py translator/leaf/control.py translator/leaf/expr.py translator/naming.py translator/rules.py translator/skeleton_gen/body_context.py translator/skeleton_gen/render_skeleton.py translator/wsaa/render_class.py translator/wsaa/render_view.py docs
git commit -m "chore: close out T10-T18 translator batch"
```

Expected: commit succeeds and `git status --short` is clean except for unrelated local files, if any.
