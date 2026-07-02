# Diff Verb Matrix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a stable verb-family matrix to `scripts/diff_asg_vs_legacy.py` so future workers can inspect parity coverage without reverse-engineering `_SAMPLERS`.

**Architecture:** Keep `_SAMPLERS` as the executable dispatch table. Add a read-only metadata table beside it and test that every matrix entry maps to a sampler, preserving current script behavior.

**Tech Stack:** Python 3.12, `unittest`, existing `scripts/diff_asg_vs_legacy.py` dynamic import pattern.

---

### Task 1: Matrix Tests

**Files:**
- Modify: `test_translation.py`

- [ ] **Step 1: Add a failing test class**

Add `TestDiffAsgVsLegacyVerbMatrix` near the existing diff-tool tests. It imports `scripts/diff_asg_vs_legacy.py`, asserts the stable verb order, checks each row has a sampler, and verifies the row fields are explicit strings.

- [ ] **Step 2: Run red verification**

Run:

```powershell
python -m unittest test_translation.TestDiffAsgVsLegacyVerbMatrix -v
```

Expected: failure because `VERB_MATRIX` is not defined yet.

### Task 2: Matrix Implementation

**Files:**
- Modify: `scripts/diff_asg_vs_legacy.py`

- [ ] **Step 1: Add `VERB_MATRIX`**

Define a tuple of dictionaries after `_SAMPLERS`, one row per supported sampler key. Fields: `verb`, `family`, `scope`, and `status`.

- [ ] **Step 2: Run green verification**

Run:

```powershell
python -m unittest test_translation.TestDiffAsgVsLegacyVerbMatrix -v
```

Expected: all matrix tests pass.

### Task 3: Documentation and Regression

**Files:**
- Create: `docs/操作记录/diff工具动词矩阵操作记录.md`

- [ ] **Step 1: Add operation record**

Document the matrix purpose, modified files, and verification commands.

- [ ] **Step 2: Run roadmap verification**

Run:

```powershell
python -m unittest test_translation.TestDiffAsgVsLegacy test_translation.TestDiffAsgVsLegacyIf test_translation.TestDiffAsgVsLegacyArith -v
python scripts/check.py --suite asg
python scripts/check.py --suite all
```

Expected: all commands exit 0.

## Self-Review

Spec coverage: covers stable matrix, sampler linkage, documentation, and roadmap verification.

Placeholder scan: no TODO/TBD placeholders.

Scope check: no CLI expansion and no translation semantics changes.
