# Preprocess Regression Fixtures Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add fixture-backed regression coverage for preprocessing comments, disabled lines, continuations, and dialect normalization.

**Architecture:** Keep the change as a test and fixture gate around the existing preprocessing/parser APIs. Reuse `preprocess.line_stream.build`, `preprocess.dialect.normalize`, and `parser.cobol_parser.parse`; do not change translator, ASG, or diff behavior unless a fixture exposes a narrow upstream bug.

**Tech Stack:** Python 3.12, `unittest`, existing COBOL fixtures, `scripts/check.py`.

---

## File Structure

- Create `tests/fixtures/preprocess_regression.cob`: representative fixed-column COBOL sample containing comments, disabled section-looking lines, a continued literal, and a dialect `GO <target>` statement.
- Modify `test_translation.py`: extend `TestProcStartCommentImmune` and `TestDialectNormalize` with fixture-backed assertions and small local helper methods.
- Create `docs/操作记录/预处理回归样例操作记录.md`: record the scope, changed files, and verification commands.
- Avoid production changes unless a new test fails for a clear bug in `preprocess/columns.py`, `preprocess/line_stream.py`, or `parser/cobol_columns.py`.

## Task 1: Add The Regression Fixture

**Files:**
- Create: `tests/fixtures/preprocess_regression.cob`

- [ ] **Step 1: Create the fixture file**

Add this exact fixture:

```cobol
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TPREP.
      *   PROCEDURE DIVISION in a comment must not start proc parsing.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WSAA-TEXT PIC X(40) VALUE 'HELLO '.
!!!!!! 9000-DISABLED SECTION.
      /   9100-COMMENTED SECTION.
       PROCEDURE DIVISION.
       1000-MAIN SECTION.
           MOVE 'ABC'
      -         'DEF' TO WSAA-TEXT.
           GO 1090-EXIT
       1090-EXIT.
           GOBACK.
```

- [ ] **Step 2: Confirm the fixture is visible**

Run: `Get-Content -LiteralPath tests\fixtures\preprocess_regression.cob`

Expected: the output contains `!!!!!! 9000-DISABLED SECTION.`, `      -         'DEF' TO WSAA-TEXT.`, and `GO 1090-EXIT`.

## Task 2: Add Failing Fixture-Backed Tests

**Files:**
- Modify: `test_translation.py`
- Test: `test_translation.TestProcStartCommentImmune`
- Test: `test_translation.TestDialectNormalize`

- [ ] **Step 1: Add helper methods to `TestProcStartCommentImmune`**

Inside `class TestProcStartCommentImmune`, below `_parse_src`, add:

```python
    def _fixture_path(self, name: str) -> Path:
        return Path(__file__).parent / "tests" / "fixtures" / name

    def _parse_fixture(self, name: str):
        from parser.cobol_parser import parse
        return parse(str(self._fixture_path(name)))
```

- [ ] **Step 2: Add parser immunity test**

Still inside `TestProcStartCommentImmune`, add:

```python
    def test_fixture_comments_and_disabled_lines_do_not_create_sections(self):
        prog = self._parse_fixture("preprocess_regression.cob")
        names = {s.name.upper() for s in prog.sections}
        self.assertIn("1000-MAIN", names)
        self.assertNotIn("9000-DISABLED", names)
        self.assertNotIn("9100-COMMENTED", names)
        self.assertNotIn("WORKING-STORAGE", names)
```

- [ ] **Step 3: Add CleanSource immunity and dialect normalization test**

Inside `class TestDialectNormalize`, add:

```python
    def _fixture_lines(self, name: str) -> list[str]:
        path = Path(__file__).parent / "tests" / "fixtures" / name
        return path.read_text(encoding="utf-8").splitlines()

    def test_fixture_clean_source_skips_comment_disabled_and_normalizes_go(self):
        from preprocess.line_stream import build
        clean = build(self._fixture_lines("preprocess_regression.cob"))
        codes = [line.code.strip() for line in clean.clean_lines]
        joined = "\n".join(codes)
        self.assertNotIn("9000-DISABLED SECTION.", joined)
        self.assertNotIn("9100-COMMENTED SECTION.", joined)
        self.assertIn("GO TO 1090-EXIT", codes)
        self.assertIn("-         'DEF' TO WSAA-TEXT.", codes)
```

- [ ] **Step 4: Run the focused tests and verify the expected result**

Run:

```powershell
python -m unittest test_translation.TestDialectNormalize test_translation.TestProcStartCommentImmune -v
```

Expected before implementation fixes: these tests should pass if current behavior already satisfies the contract. If they fail because the fixture is missing, complete Task 1. If they fail on behavior, continue to Task 3.

## Task 3: Minimal Production Fix Only If Needed

**Files:**
- Modify only if needed: `preprocess/columns.py`
- Modify only if needed: `preprocess/line_stream.py`
- Modify only if needed: `parser/cobol_columns.py`

- [ ] **Step 1: If disabled/comment lines leak, inspect the failing assertion**

If `9000-DISABLED` or `9100-COMMENTED` appears in `CleanSource`, check that `preprocess.columns.is_deactivated(raw)` and `preprocess.columns.is_comment(raw)` are called from `CleanSource.strip_line`.

The intended implementation is:

```python
        if columns.is_deactivated(raw) or columns.is_comment(raw) or columns.is_debug(raw):
            return ""
```

- [ ] **Step 2: If `GO 1090-EXIT` is not normalized, inspect `CleanSource.strip_line`**

The intended implementation is:

```python
        return dialect.normalize(columns.clean_line(raw))
```

- [ ] **Step 3: If parser sections leak but CleanSource is correct, inspect `parser.cobol_parser` callers**

Do not change translator semantics. Limit any fix to ensuring parser-side section discovery ignores `parser.cobol_columns.is_comment(raw)` and `parser.cobol_columns.is_deactivated(raw)` for structure detection.

- [ ] **Step 4: Re-run focused tests after any fix**

Run:

```powershell
python -m unittest test_translation.TestDialectNormalize test_translation.TestProcStartCommentImmune -v
```

Expected: `OK`.

## Task 4: Document The Operation Record

**Files:**
- Create: `docs/操作记录/预处理回归样例操作记录.md`

- [ ] **Step 1: Create the operation record**

Add:

```markdown
# 预处理回归样例操作记录

## 本次修改

- 新增 `tests/fixtures/preprocess_regression.cob`，覆盖注释行、停用行、续行和方言 GO 归一样例。
- 修改 `test_translation.py`，扩展 `TestProcStartCommentImmune` 与 `TestDialectNormalize` 的 fixture-backed 回归用例。
- 未修改 translator/ASG 语义。

## 结果

预处理层继续跳过注释、停用和调试行；方言归一在 CleanSource 入口生效；注释或停用的 SECTION 形态不会进入 parser 的过程段集合。

## 验证命令

```powershell
python -m unittest test_translation.TestDialectNormalize test_translation.TestProcStartCommentImmune -v
python scripts/check.py --suite quick
```
```

## Task 5: Verify And Commit

**Files:**
- Verify: `test_translation.py`
- Verify: `tests/fixtures/preprocess_regression.cob`
- Verify: `docs/操作记录/预处理回归样例操作记录.md`

- [ ] **Step 1: Run focused verification**

Run:

```powershell
python -m unittest test_translation.TestDialectNormalize test_translation.TestProcStartCommentImmune -v
```

Expected: all tests pass.

- [ ] **Step 2: Run roadmap verification**

Run:

```powershell
python scripts/check.py --suite quick
```

Expected: quick suite passes.

- [ ] **Step 3: Check git status**

Run: `git status --short`

Expected changed files:

```text
 M test_translation.py
?? tests/fixtures/preprocess_regression.cob
?? docs/操作记录/预处理回归样例操作记录.md
```

If Task 3 required a production fix, include only the relevant upstream file from `preprocess/` or `parser/cobol_columns.py`.

- [ ] **Step 4: Commit implementation**

Run:

```powershell
git add test_translation.py tests/fixtures/preprocess_regression.cob docs/操作记录/预处理回归样例操作记录.md
git commit -m "test: add preprocess regression fixtures"
```

If a production fix was required, add that file to the same commit after confirming it is within the allowed scope.

## Self-Review

Spec coverage:

- Comment immunity is covered by `test_fixture_comments_and_disabled_lines_do_not_create_sections`.
- Disabled-line immunity is covered by both parser and CleanSource assertions.
- Continuation stability is covered by the cleaned continuation indicator line assertion.
- Dialect normalization is covered by `GO TO 1090-EXIT` from `CleanSource`.
- Verification commands match the approved spec.

Placeholder scan:

- No open-ended implementation placeholders or undefined helper names remain.

Type consistency:

- Helper methods use `Path`, already imported at the top of `test_translation.py`.
- Tests use existing `unittest` style and existing parser/preprocess APIs.
