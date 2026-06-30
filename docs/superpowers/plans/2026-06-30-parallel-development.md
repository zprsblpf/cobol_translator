# Parallel Development Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the lightweight process and verification infrastructure needed to run multiple COBOL translator development tasks in parallel with low file conflict.

**Architecture:** Keep the approved swimlane design in `docs/superpowers/specs/2026-06-30-parallel-development-design.md` as the source of truth, then add concrete task-package docs under `docs/并行开发/`. Add a small suite selector to `scripts/check.py` so each worker can run focused checks before the full local gate.

**Tech Stack:** Markdown docs, Python 3.12, `unittest`, existing `scripts/check.py`, existing project command conventions.

---

## File Structure

- Create: `docs/并行开发/README.md`
  - Human-facing index for the parallel development operating model.
- Create: `docs/并行开发/任务包模板.md`
  - Reusable task-package template with file boundaries, dependencies, tests, and merge notes.
- Create: `docs/并行开发/第一批/任务01-UNSTRING叶子固化.md`
  - First lane A task package.
- Create: `docs/并行开发/第一批/任务02-INSPECT叶子固化.md`
  - Second lane A task package.
- Create: `docs/并行开发/第一批/任务03-ASG-leaf-fallback对比补强.md`
  - Lane B task package.
- Create: `docs/并行开发/第一批/任务04-快速验证入口.md`
  - Lane D task package.
- Modify: `scripts/check.py`
  - Add `--suite` to run focused checks: `quick`, `leaf`, `asg`, `all`.
- Modify: `test_smoke.py`
  - Add a small unit test that checks `scripts.check` exposes expected suites without running subprocesses.
- Create: `docs/操作记录/并行开发提速机制操作记录.md`
  - Record files changed, verification commands, and usage.

---

### Task 1: Parallel Development Docs Index

**Files:**
- Create: `docs/并行开发/README.md`
- Create: `docs/并行开发/任务包模板.md`

- [ ] **Step 1: Create the docs directory**

Run:

```powershell
New-Item -ItemType Directory -Force -Path 'docs/并行开发' | Out-Null
```

Expected: command exits with code 0.

- [ ] **Step 2: Add the index doc**

Create `docs/并行开发/README.md` with this content:

```markdown
# 并行开发

本目录固化 COBOL 到 Java 翻译器的并行开发任务包。

源设计：

- `docs/superpowers/specs/2026-06-30-parallel-development-design.md`

固定泳道：

- A：Leaf 动词固化
- B：ASG/Visitor 迁移
- C：Skel 结构吸收
- D：验证与样例

执行原则：

- 每个任务先写清允许修改文件和禁止修改文件。
- 公共底座任务先合并，ASG 接入任务后合并，主线切换最后合并。
- 每个任务必须有独立验收命令。
- 最终合并前必须通过 `python scripts/check.py --suite all`。

第一批任务：

- `第一批/任务01-UNSTRING叶子固化.md`
- `第一批/任务02-INSPECT叶子固化.md`
- `第一批/任务03-ASG-leaf-fallback对比补强.md`
- `第一批/任务04-快速验证入口.md`
```

- [ ] **Step 3: Add the task package template**

Create `docs/并行开发/任务包模板.md` with this content:

```markdown
# 任务包模板

## 目标

一句话说明本任务完成后新增什么能力。

## 泳道

A / B / C / D 中选择一个。

## 允许修改

- `path/to/file`

## 禁止修改

- `path/to/high_risk_file`

## 依赖

说明依赖的公共入口、前置任务或设计文档。

## 实施步骤

1. 写失败测试。
2. 运行单测确认失败原因正确。
3. 实现最小代码。
4. 运行单任务验收命令。
5. 更新设计文档或操作记录。
6. 运行最终本地闸口。

## 验收命令

```powershell
python -m unittest path.to.TestClass -v
python scripts/check.py --suite all
```

## 合并备注

说明是否必须先于其它任务合并，以及可能冲突的测试类位置。
```

- [ ] **Step 4: Verify docs exist**

Run:

```powershell
Test-Path 'docs/并行开发/README.md'; Test-Path 'docs/并行开发/任务包模板.md'
```

Expected: two `True` lines.

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add docs/并行开发/README.md docs/并行开发/任务包模板.md
git commit -m "docs: add parallel task package template"
```

Expected: commit succeeds.

---

### Task 2: First Batch Task Packages

**Files:**
- Create: `docs/并行开发/第一批/任务01-UNSTRING叶子固化.md`
- Create: `docs/并行开发/第一批/任务02-INSPECT叶子固化.md`
- Create: `docs/并行开发/第一批/任务03-ASG-leaf-fallback对比补强.md`
- Create: `docs/并行开发/第一批/任务04-快速验证入口.md`

- [ ] **Step 1: Create the first-batch directory**

Run:

```powershell
New-Item -ItemType Directory -Force -Path 'docs/并行开发/第一批' | Out-Null
```

Expected: command exits with code 0.

- [ ] **Step 2: Create UNSTRING task package**

Create `docs/并行开发/第一批/任务01-UNSTRING叶子固化.md`:

```markdown
# 任务01：UNSTRING 叶子固化

## 目标

为保守子集的 `UNSTRING ... DELIMITED BY ... INTO ...` 增加确定性翻译，并接入统一 leaf 入口。

## 泳道

A：Leaf 动词固化

## 允许修改

- `translator/leaf/unstring.py`
- `translator/leaf/__init__.py`
- `test_translation.py`
- `docs/详细设计/步骤33-UNSTRING叶子语句固化设计.md`
- `docs/操作记录/步骤33-UNSTRING叶子语句固化操作记录.md`

## 禁止修改

- `translator/skel/*`
- `asg/structure_rewrite.py`
- `translator/rules.py` 中非委托逻辑

## 依赖

- `translator.leaf.translate_leaf_stmt`
- `translator.leaf.expr._operand`
- `translator.leaf.expr._lvalue`

## 实施步骤

1. 新增 `TestLeafUnstringExtract`，覆盖支持子集和不支持形态。
2. 扩展 `TestUnifiedLeafEntry`，验证 `translate_leaf_stmt` 统一入口命中。
3. 扩展 ASG leaf visitor 测试，验证 visitor 共享输出。
4. 新建 `translator/leaf/unstring.py`。
5. 在 `translator/leaf/__init__.py` 接入 `translate_unstring`。
6. 更新设计文档和操作记录。

## 验收命令

```powershell
python -m unittest test_translation.TestLeafUnstringExtract test_translation.TestUnifiedLeafEntry -v
python scripts/check.py --suite leaf
python scripts/check.py --suite all
```

## 合并备注

该任务只依赖 leaf 公共入口，可与 INSPECT 并行开发，但合并时需要协调 `translator/leaf/__init__.py` 和 `test_translation.py` 的插入位置。
```

- [ ] **Step 3: Create INSPECT task package**

Create `docs/并行开发/第一批/任务02-INSPECT叶子固化.md`:

```markdown
# 任务02：INSPECT 叶子固化

## 目标

为保守子集的 `INSPECT ... REPLACING` 或 `INSPECT ... TALLYING` 增加确定性翻译。

## 泳道

A：Leaf 动词固化

## 允许修改

- `translator/leaf/inspect.py`
- `translator/leaf/__init__.py`
- `test_translation.py`
- `docs/详细设计/步骤34-INSPECT叶子语句固化设计.md`
- `docs/操作记录/步骤34-INSPECT叶子语句固化操作记录.md`

## 禁止修改

- `translator/skel/*`
- `asg/structure_rewrite.py`
- `translator/rules.py` 中非委托逻辑

## 依赖

- `translator.leaf.translate_leaf_stmt`
- `translator.leaf.expr._operand`
- `translator.leaf.expr._lvalue`

## 实施步骤

1. 新增 `TestLeafInspectExtract`，覆盖 `REPLACING`、`TALLYING` 和不支持形态。
2. 扩展 `TestUnifiedLeafEntry`，验证 `translate_leaf_stmt` 统一入口命中。
3. 扩展 ASG leaf visitor 测试，验证 visitor 共享输出。
4. 新建 `translator/leaf/inspect.py`。
5. 在 `translator/leaf/__init__.py` 接入 `translate_inspect`。
6. 更新设计文档和操作记录。

## 验收命令

```powershell
python -m unittest test_translation.TestLeafInspectExtract test_translation.TestUnifiedLeafEntry -v
python scripts/check.py --suite leaf
python scripts/check.py --suite all
```

## 合并备注

该任务与 UNSTRING 同属 leaf 泳道，默认可以并行开发。合并顺序以先完成、先通过 `--suite leaf` 为准。
```

- [ ] **Step 4: Create ASG fallback task package**

Create `docs/并行开发/第一批/任务03-ASG-leaf-fallback对比补强.md`:

```markdown
# 任务03：ASG leaf fallback 对比补强

## 目标

补齐未固化 leaf 在 ASG visitor 下的占位输出对比，避免新增动词时误改 fallback 行为。

## 泳道

B：ASG/Visitor 迁移

## 允许修改

- `asg/visitor.py`
- `scripts/diff_asg_vs_legacy.py`
- `test_translation.py`
- `docs/操作记录/ASG-leaf-fallback对比补强操作记录.md`

## 禁止修改

- `translator/leaf/*.py`
- `translator/skel/*.py`
- `parser/*`

## 依赖

- `asg.Leaf`
- `asg.LeafJavaVisitor`
- `scripts/diff_asg_vs_legacy.py`

## 实施步骤

1. 新增或扩展 `TestDiffAsgVsLegacy*`，覆盖未固化动词的 fallback 输出。
2. 运行测试确认当前对比缺口。
3. 在 `scripts/diff_asg_vs_legacy.py` 增加必要的 leaf fallback 采集或报告。
4. 如 visitor fallback 文案不一致，只在 `asg/visitor.py` 做最小修正。
5. 更新操作记录。

## 验收命令

```powershell
python -m unittest test_translation.TestAsgLeafArithVisitor test_translation.TestUnifiedLeafEntry -v
python scripts/check.py --suite asg
python scripts/check.py --suite all
```

## 合并备注

该任务不改变任何已固化动词语义，应在 UNSTRING/INSPECT 主线接入前或同时合并。
```

- [ ] **Step 5: Create quick verification task package**

Create `docs/并行开发/第一批/任务04-快速验证入口.md`:

```markdown
# 任务04：快速验证入口

## 目标

为单个动词族和 ASG 迁移任务提供快速验证命令，降低并行开发等待成本。

## 泳道

D：验证与样例

## 允许修改

- `scripts/check.py`
- `test_smoke.py`
- `docs/操作记录/并行开发提速机制操作记录.md`

## 禁止修改

- `translator/leaf/*.py`
- `translator/skel/*.py`
- `asg/*.py` 中翻译语义
- `parser/*`

## 依赖

- Python `unittest`
- 现有 `scripts/check.py`

## 实施步骤

1. 给 `scripts/check.py` 增加 `--suite quick|leaf|asg|all`。
2. 在 `test_smoke.py` 增加 suite 映射测试。
3. 运行 `quick`、`leaf`、`asg`、`all` 验证命令。
4. 更新操作记录。

## 验收命令

```powershell
python -m unittest test_smoke.TestCheckScriptSuites -v
python scripts/check.py --suite quick
python scripts/check.py --suite leaf
python scripts/check.py --suite asg
python scripts/check.py --suite all
```

## 合并备注

该任务是并行开发基础设施，建议先于 UNSTRING 和 INSPECT 实现任务合并。
```

- [ ] **Step 6: Verify first-batch docs exist**

Run:

```powershell
Get-ChildItem -LiteralPath 'docs/并行开发/第一批' -File | Select-Object -ExpandProperty Name
```

Expected output includes:

```text
任务01-UNSTRING叶子固化.md
任务02-INSPECT叶子固化.md
任务03-ASG-leaf-fallback对比补强.md
任务04-快速验证入口.md
```

- [ ] **Step 7: Commit Task 2**

Run:

```powershell
git add docs/并行开发/第一批
git commit -m "docs: add first parallel task packages"
```

Expected: commit succeeds.

---

### Task 3: Focused Check Suites

**Files:**
- Modify: `scripts/check.py`
- Modify: `test_smoke.py`

- [ ] **Step 1: Add a failing smoke test for check suites**

Append this test class to `test_smoke.py`:

```python
class TestCheckScriptSuites(unittest.TestCase):
    """并行开发：验证 scripts.check 暴露固定快速验证套件。"""

    def test_suite_names_are_stable(self):
        from scripts import check

        self.assertEqual(set(check.SUITES), {"quick", "leaf", "asg", "all"})

    def test_all_suite_extends_quick_suite(self):
        from scripts import check

        quick = [tuple(cmd) for cmd in check.SUITES["quick"]]
        all_cmds = [tuple(cmd) for cmd in check.SUITES["all"]]

        for cmd in quick:
            self.assertIn(cmd, all_cmds)
```

- [ ] **Step 2: Run the smoke test to verify RED**

Run:

```powershell
python -m unittest test_smoke.TestCheckScriptSuites -v
```

Expected: fail with `AttributeError: module 'scripts.check' has no attribute 'SUITES'`.

- [ ] **Step 3: Replace `scripts/check.py` with suite-aware implementation**

Replace the file with:

```python
#!/usr/bin/env python3
"""Project verification entry point.

This script intentionally runs checks that do not require a local LLM,
LangGraph, Chroma, or MongoDB service. Install requirements.txt before using
the full translation pipeline.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _py(*args: str) -> list[str]:
    """Build a Python command using the current interpreter."""
    return [sys.executable, *args]


SUITES: dict[str, list[list[str]]] = {
    "quick": [
        _py("-m", "py_compile", "main.py", "test_smoke.py"),
        _py("-m", "unittest", "test_smoke", "-v"),
        _py(
            "main.py",
            "tests/fixtures/minimal.cob",
            "--parse-only",
        ),
    ],
    "leaf": [
        _py(
            "-m",
            "unittest",
            "test_translation.TestLeafMoveExtract",
            "test_translation.TestLeafCondExtract",
            "test_translation.TestLeafLoopExtract",
            "test_translation.TestLeafCallExtract",
            "test_translation.TestLeafArithExtract",
            "test_translation.TestLeafStringExtract",
            "test_translation.TestUnifiedLeafEntry",
            "-v",
        ),
    ],
    "asg": [
        _py(
            "-m",
            "unittest",
            "test_translation.TestAsgBuild",
            "test_translation.TestAsgMoveVisitor",
            "test_translation.TestAsgIfVisitor",
            "test_translation.TestAsgPerformVisitor",
            "test_translation.TestAsgCallVisitor",
            "test_translation.TestAsgLeafArithVisitor",
            "test_translation.TestAsgControlVisitor",
            "test_translation.TestAsgSectionVisitorFlow",
            "test_translation.TestAsgSectionVisitorPerformTarget",
            "-v",
        ),
    ],
}

SUITES["all"] = [
    *SUITES["quick"],
    _py("-m", "unittest", "-v"),
    _py(
        "scripts/translate_skeleton.py",
        "--in",
        "tests/fixtures/minimal.cob",
        "--out",
        "output/check/Minismoke.java",
    ),
    _py(
        "main.py",
        "tests/fixtures/minimal.cob",
        "--no-llm",
        "--output",
        "output/check-main",
    ),
]


def run(args: list[str]) -> int:
    print("$ " + " ".join(args), flush=True)
    return subprocess.call(args, cwd=ROOT)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run project verification checks.")
    parser.add_argument(
        "--suite",
        choices=sorted(SUITES),
        default="all",
        help="Verification suite to run.",
    )
    args = parser.parse_args(argv)

    for cmd in SUITES[args.suite]:
        code = run(cmd)
        if code:
            return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the smoke test to verify GREEN**

Run:

```powershell
python -m unittest test_smoke.TestCheckScriptSuites -v
```

Expected: pass.

- [ ] **Step 5: Run focused suites**

Run:

```powershell
python scripts/check.py --suite quick
python scripts/check.py --suite leaf
python scripts/check.py --suite asg
```

Expected: each command exits with code 0.

- [ ] **Step 6: Run full gate**

Run:

```powershell
python scripts/check.py --suite all
```

Expected: exits with code 0.

- [ ] **Step 7: Commit Task 3**

Run:

```powershell
git add scripts/check.py test_smoke.py
git commit -m "test: add focused verification suites"
```

Expected: commit succeeds.

---

### Task 4: Operation Record

**Files:**
- Create: `docs/操作记录/并行开发提速机制操作记录.md`

- [ ] **Step 1: Create the operation record**

Create `docs/操作记录/并行开发提速机制操作记录.md` with this content:

```markdown
# 并行开发提速机制操作记录

## 目标

固化并行开发泳道、首批任务包和快速验证入口，让后续多个任务可以同时推进。

## 设计依据

- `docs/superpowers/specs/2026-06-30-parallel-development-design.md`
- `docs/superpowers/plans/2026-06-30-parallel-development.md`

## 本次新增

- `docs/并行开发/README.md`
- `docs/并行开发/任务包模板.md`
- `docs/并行开发/第一批/任务01-UNSTRING叶子固化.md`
- `docs/并行开发/第一批/任务02-INSPECT叶子固化.md`
- `docs/并行开发/第一批/任务03-ASG-leaf-fallback对比补强.md`
- `docs/并行开发/第一批/任务04-快速验证入口.md`

## 本次修改

- `scripts/check.py`：新增 `--suite quick|leaf|asg|all`
- `test_smoke.py`：新增 `TestCheckScriptSuites`

## 验证命令

```powershell
python -m unittest test_smoke.TestCheckScriptSuites -v
python scripts/check.py --suite quick
python scripts/check.py --suite leaf
python scripts/check.py --suite asg
python scripts/check.py --suite all
```

## 后续执行建议

优先合并 `任务04-快速验证入口`，再并行启动 `任务01-UNSTRING叶子固化` 和 `任务02-INSPECT叶子固化`。`任务03-ASG-leaf-fallback对比补强` 可与 leaf 任务并行，但合并前必须确认 fallback 文案未改变。
```

- [ ] **Step 2: Verify operation record exists**

Run:

```powershell
Test-Path 'docs/操作记录/并行开发提速机制操作记录.md'
```

Expected: `True`.

- [ ] **Step 3: Run final full gate**

Run:

```powershell
python scripts/check.py --suite all
```

Expected: exits with code 0.

- [ ] **Step 4: Commit Task 4**

Run:

```powershell
git add docs/操作记录/并行开发提速机制操作记录.md
git commit -m "docs: record parallel development workflow"
```

Expected: commit succeeds.

---

## Self-Review

Spec coverage:

- Fixed swimlanes are implemented by `docs/并行开发/README.md`.
- Task package format is implemented by `docs/并行开发/任务包模板.md`.
- First batch task packages are implemented under `docs/并行开发/第一批/`.
- Fast verification is implemented by `scripts/check.py --suite`.
- Operation record is implemented by `docs/操作记录/并行开发提速机制操作记录.md`.

Type and command consistency:

- `scripts.check.SUITES` is a `dict[str, list[list[str]]]`.
- `main(argv: list[str] | None = None)` keeps script and test usage compatible.
- `--suite all` preserves the original full local gate and adds focused suites without removing existing checks.
