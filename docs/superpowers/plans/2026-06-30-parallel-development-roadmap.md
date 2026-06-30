# Parallel Development Roadmap Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Define the post-first-batch task roadmap for the COBOL to Java translator so future development can be dispatched in parallel without guessing scope.

**Architecture:** Continue the approved four swimlanes from `docs/superpowers/specs/2026-06-30-parallel-development-design.md`: Leaf, ASG/Visitor, Skel, and Verification. Each task package names the files it may touch, the files it must avoid, and the focused verification command expected after implementation.

**Tech Stack:** Python 3.12, `unittest`, existing `translator/leaf`, `translator/skel`, `asg`, `scripts/diff_asg_vs_legacy.py`, `scripts/check.py`.

---

## Completion Definition

The whole project is not complete after the first four tasks. Treat the translator as complete only when these gates are satisfied:

- Core COBOL leaf verbs used by the target corpus are covered by deterministic translators or explicit documented fallbacks.
- Mainline SECTION rendering uses ASG/visitor paths by default where parity has been proven.
- Legacy `translator/rules.py` is reduced to thin compatibility wrappers for migrated behavior.
- `scripts/diff_asg_vs_legacy.py` has parity coverage for every migrated verb or structure family.
- `python scripts/check.py --suite all` passes.
- A representative large COBOL sample translates with no unexpected exceptions and produces review artifacts.

---

## Batch 1: Parallel Development Infrastructure

Status: planned in `docs/superpowers/plans/2026-06-30-parallel-development.md`.

### Task 1.1: Fast Verification Entry

Swimlane: D

Allowed files:

- `scripts/check.py`
- `test_smoke.py`
- `docs/操作记录/并行开发提速机制操作记录.md`

Do not modify:

- `translator/leaf/*.py`
- `translator/skel/*.py`
- `asg/*.py` translation semantics

Verification:

```powershell
python -m unittest test_smoke.TestCheckScriptSuites -v
python scripts/check.py --suite quick
python scripts/check.py --suite leaf
python scripts/check.py --suite asg
python scripts/check.py --suite all
```

### Task 1.2: UNSTRING Leaf

Swimlane: A

Allowed files:

- `translator/leaf/unstring.py`
- `translator/leaf/__init__.py`
- `test_translation.py`
- `docs/详细设计/步骤33-UNSTRING叶子语句固化设计.md`
- `docs/操作记录/步骤33-UNSTRING叶子语句固化操作记录.md`

Verification:

```powershell
python -m unittest test_translation.TestLeafUnstringExtract test_translation.TestUnifiedLeafEntry -v
python scripts/check.py --suite leaf
```

### Task 1.3: INSPECT Leaf

Swimlane: A

Allowed files:

- `translator/leaf/inspect.py`
- `translator/leaf/__init__.py`
- `test_translation.py`
- `docs/详细设计/步骤34-INSPECT叶子语句固化设计.md`
- `docs/操作记录/步骤34-INSPECT叶子语句固化操作记录.md`

Verification:

```powershell
python -m unittest test_translation.TestLeafInspectExtract test_translation.TestUnifiedLeafEntry -v
python scripts/check.py --suite leaf
```

### Task 1.4: ASG Leaf Fallback Diff

Swimlane: B

Allowed files:

- `asg/visitor.py`
- `scripts/diff_asg_vs_legacy.py`
- `test_translation.py`
- `docs/操作记录/ASG-leaf-fallback对比补强操作记录.md`

Verification:

```powershell
python scripts/check.py --suite asg
python scripts/check.py --suite all
```

---

## Batch 2: Remaining Leaf Verb Coverage

Goal: reduce LLM/manual fallback pressure by moving common leaf verbs into deterministic translators.

### Task 2.1: SEARCH Leaf Triage

Swimlane: A

Goal: classify `SEARCH` forms into supported deterministic subset and documented fallback subset.

Allowed files:

- `translator/leaf/search.py`
- `translator/leaf/__init__.py`
- `test_translation.py`
- `docs/详细设计/步骤35-SEARCH叶子语句分型设计.md`
- `docs/操作记录/步骤35-SEARCH叶子语句分型操作记录.md`

Do not modify:

- `translator/skel/*`
- `asg/structure_rewrite.py`

Verification:

```powershell
python -m unittest test_translation.TestLeafSearchExtract test_translation.TestUnifiedLeafEntry -v
python scripts/check.py --suite leaf
```

### Task 2.2: STRING Complex Fallback Audit

Swimlane: A

Goal: extend tests around unsupported `STRING` forms so pointer/overflow/multiple target behavior remains explicit.

Allowed files:

- `translator/leaf/string.py`
- `test_translation.py`
- `docs/操作记录/步骤32-STRING复杂形态回归操作记录.md`

Do not modify:

- `translator/skel/*`
- `asg/structure_rewrite.py`

Verification:

```powershell
python -m unittest test_translation.TestLeafStringExtract test_translation.TestUnifiedLeafEntry -v
python scripts/check.py --suite leaf
```

### Task 2.3: COPY/INITIALIZE Group Assignment Coverage

Swimlane: A

Goal: harden `INITIALIZE` and group assignment semantics for known WSAA structures without moving structure-level logic into leaf.

Allowed files:

- `translator/leaf/assign.py`
- `translator/leaf/expr.py`
- `test_translation.py`
- `docs/详细设计/步骤36-组字段赋值覆盖设计.md`
- `docs/操作记录/步骤36-组字段赋值覆盖操作记录.md`

Do not modify:

- `translator/skel/io_rewrite.py`
- `asg/structure_rewrite.py`

Verification:

```powershell
python -m unittest test_translation.TestLeafArithExtract test_translation.TestUnifiedLeafEntry -v
python scripts/check.py --suite leaf
```

---

## Batch 3: ASG/Visitor Parity Expansion

Goal: make ASG visitor output demonstrably equivalent to legacy output for every migrated family.

### Task 3.1: Diff Tool Verb Matrix

Swimlane: D

Goal: add a stable verb-family matrix to `scripts/diff_asg_vs_legacy.py` so workers can request exact parity checks.

Allowed files:

- `scripts/diff_asg_vs_legacy.py`
- `test_translation.py`
- `docs/操作记录/diff工具动词矩阵操作记录.md`

Do not modify:

- `translator/leaf/*.py`
- `translator/skel/*.py`

Verification:

```powershell
python -m unittest test_translation.TestDiffAsgVsLegacy test_translation.TestDiffAsgVsLegacyIf test_translation.TestDiffAsgVsLegacyArith -v
python scripts/check.py --suite asg
```

### Task 3.2: ASG Node Lift Coverage

Swimlane: B

Goal: ensure `asg.builder` lifts all migrated statement families into typed nodes or documented `Leaf` fallback.

Allowed files:

- `asg/nodes.py`
- `asg/builder.py`
- `test_translation.py`
- `docs/操作记录/ASG节点提升覆盖操作记录.md`

Do not modify:

- `translator/leaf/*.py`
- `translator/skel/*.py`

Verification:

```powershell
python -m unittest test_translation.TestAsgBuild test_translation.TestAsgMoveLift -v
python scripts/check.py --suite asg
```

### Task 3.3: SectionJavaVisitor Default Readiness

Swimlane: B

Goal: define and test the readiness gate for using `SectionJavaVisitor` as the default mainline SECTION renderer.

Allowed files:

- `asg/section_visitor.py`
- `translator/skeleton_gen/body_context.py`
- `test_translation.py`
- `docs/详细设计/步骤37-SectionJavaVisitor主线默认闸口设计.md`
- `docs/操作记录/步骤37-SectionJavaVisitor主线默认闸口操作记录.md`

Do not modify:

- `translator/leaf/*.py`
- `translator/skel/*.py` semantics

Verification:

```powershell
python -m unittest test_translation.TestMainlineSectionViaAsg test_translation.TestMainlinePendingRangeViaAsg -v
python scripts/check.py --suite asg
python scripts/check.py --suite all
```

---

## Batch 4: Skel Structure Hardening

Goal: finish the highest-risk段级 structure families before defaulting more mainline rendering to ASG.

### Task 4.1: BEGN/NEXTR Multi-Shape Fixtures

Swimlane: C

Goal: add representative BEGN/NEXTR structure fixtures and parity checks beyond the current minimal selected forms.

Allowed files:

- `translator/skel/io_rewrite.py`
- `asg/structure_rewrite.py`
- `asg/section_visitor.py`
- `test_translation.py`
- `docs/操作记录/BEGN-NEXTR多形态样例操作记录.md`

Verification:

```powershell
python -m unittest test_translation.TestAsgBegnForeachRewrite test_translation.TestAsgBegnForeachVisitor -v
python scripts/check.py --suite asg
```

### Task 4.2: READR/READS Error Path Coverage

Swimlane: C

Goal: harden READ single-record paths, not-found behavior, and generated try/catch shape.

Allowed files:

- `translator/skel/io_rewrite.py`
- `asg/structure_rewrite.py`
- `asg/section_visitor.py`
- `test_translation.py`
- `docs/操作记录/READR-READS错误路径覆盖操作记录.md`

Verification:

```powershell
python -m unittest test_translation.TestAsgReadrSingleRewrite test_translation.TestAsgReadrSingleVisitor -v
python scripts/check.py --suite asg
```

### Task 4.3: WRITE/UPDAT/DELET Structure Coverage

Swimlane: C

Goal: complete write-side IO structure coverage and parity tests for save/delete style generated Java.

Allowed files:

- `translator/skel/io_rewrite.py`
- `asg/structure_rewrite.py`
- `asg/section_visitor.py`
- `test_translation.py`
- `docs/操作记录/WRITE-UPDAT-DELET结构覆盖操作记录.md`

Verification:

```powershell
python -m unittest test_translation.TestAsgWriteSingleRewrite test_translation.TestAsgWriteSingleVisitor -v
python scripts/check.py --suite asg
```

---

## Batch 5: Parser and Preprocess Stability

Goal: reduce upstream parse variance so downstream parallel work is not invalidated by input normalization differences.

### Task 5.1: Preprocess Regression Fixtures

Swimlane: D

Goal: add fixtures for comment, disabled line, continuation, and dialect normalization cases.

Allowed files:

- `preprocess/*.py`
- `parser/cobol_columns.py`
- `test_translation.py`
- `tests/fixtures/*`
- `docs/操作记录/预处理回归样例操作记录.md`

Verification:

```powershell
python -m unittest test_translation.TestDialectNormalize test_translation.TestProcStartCommentImmune -v
python scripts/check.py --suite quick
```

### Task 5.2: Parser Section Boundary Audit

Swimlane: D

Goal: strengthen parser tests around SECTION detection, disabled section headers, COPY boundaries, and paragraph extraction.

Allowed files:

- `parser/cobol_parser.py`
- `test_translation.py`
- `tests/fixtures/*`
- `docs/操作记录/parser-section-boundary-audit操作记录.md`

Verification:

```powershell
python -m unittest test_translation.TestProcStartCommentImmune test_translation.TestAsgBuild -v
python scripts/check.py --suite all
```

---

## Batch 6: Full-Corpus Translation Gates

Goal: move from unit-level parity to end-to-end confidence on representative COBOL inputs.

### Task 6.1: Large Sample Translation Smoke

Swimlane: D

Goal: add a parameterized script or documented command for running deterministic translation on a larger COBOL sample path supplied by the user.

Allowed files:

- `scripts/check.py`
- `scripts/translate_skeleton.py`
- `docs/运行验收.md`
- `docs/操作记录/大样本翻译冒烟操作记录.md`

Do not modify:

- Translation semantics in `translator/*`
- Parser behavior in `parser/*`

Verification:

```powershell
python scripts/check.py --suite all
```

### Task 6.2: Java Artifact Review Checklist Expansion

Swimlane: D

Goal: make generated Java artifact review actionable by expanding checklist output for TODO counts, fallback counts, IO structures, and unresolved GO TO.

Allowed files:

- `validator/java_validator.py`
- `translator/assemble.py`
- `test_translation.py`
- `docs/操作记录/Java产物审查清单扩展操作记录.md`

Verification:

```powershell
python -m unittest test_translation.TestPostprocessJavaBody -v
python scripts/check.py --suite all
```

### Task 6.3: Project Completion Audit

Swimlane: D

Goal: produce a final audit document that lists completed families, remaining fallbacks, and the commands proving the current project state.

Allowed files:

- `docs/运行验收.md`
- `docs/架构索引/项目总览.md`
- `docs/操作记录/项目完成度审计操作记录.md`

Verification:

```powershell
python scripts/check.py --suite all
```

---

## Recommended Dispatch Order

- First dispatch Batch 1, Task 1.1 before other implementation tasks because it gives every worker faster local checks.
- Then dispatch Batch 1, Tasks 1.2, 1.3, and 1.4 in parallel.
- Dispatch Batch 2 leaf tasks in parallel only after `--suite leaf` exists.
- Dispatch Batch 3 ASG parity tasks after Batch 1.4 lands.
- Dispatch Batch 4 skel hardening after Batch 3.1 lands, so each structure family can use the same diff matrix.
- Dispatch Batch 5 parser/preprocess tasks independently, but merge carefully because upstream parser changes can affect all downstream tests.
- Dispatch Batch 6 only after the leaf, ASG, and skel gates are stable.

## Self-Review

Spec coverage:

- The original four swimlanes are preserved.
- The first four tasks are retained and clarified.
- Later leaf, ASG, skel, parser, and full-corpus work is decomposed into concrete batches.
- Each task lists allowed files and verification commands.

Scope check:

- This roadmap does not claim project completion after Batch 1.
- Project completion is tied to explicit gates, not to task count.

Placeholder scan:

- No task uses open-ended placeholders for files or verification commands.
