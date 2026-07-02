# Preprocess Regression Fixtures Design

## Goal

Add a narrow regression gate for COBOL preprocessing and fixed-column parsing stability before more translator behavior changes land.

This task is Batch 5.1 from the parallel development roadmap. It protects upstream input normalization so downstream ASG, visitor, and leaf work is not invalidated by changes in comments, disabled lines, continuations, or dialect normalization.

## Scope

In scope:

- Add representative fixtures under `tests/fixtures/`.
- Add focused regression tests in `test_translation.py`.
- Touch `preprocess/*.py` or `parser/cobol_columns.py` only if a fixture exposes an obvious current-behavior bug.
- Add an operation record under `docs/操作记录/`.

Out of scope:

- Translator semantic changes in `translator/*`.
- ASG visitor behavior changes.
- Full parser section-boundary audit from Batch 5.2.
- LLM, MongoDB, Chroma, or full translation path changes.

## Test Coverage

The regression tests will cover four upstream stability classes:

1. Comment immunity: COBOL comment lines must not become executable statements, sections, or paragraphs.
2. Disabled-line immunity: disabled section or paragraph-looking lines must not create process units.
3. Continuation stability: fixed-column continuation samples must normalize consistently under the existing parser/preprocess contract.
4. Dialect normalization: known dialect spellings must normalize before downstream parse-only and ASG build paths consume them.

The tests should reuse existing public helpers where available instead of asserting against private internals. If existing tests already cover part of a class, extend them with fixture-backed cases rather than duplicating ad hoc strings.

## Data Flow

Fixtures feed the existing preprocessing and parser entry points. The resulting cleaned lines or parsed program are then checked for stable observable behavior:

- no unexpected sections or paragraphs from comments/disabled lines;
- expected normalized tokens or lines for dialect/continuation cases;
- `main.py --parse-only` and ASG build remain compatible for representative samples.

## Error Handling

The tests should lock current intended behavior. If a fixture fails because behavior is ambiguous, prefer documenting the current conservative contract in the test name and operation record before changing implementation.

Implementation fixes, if needed, must be minimal and limited to the upstream files named in the roadmap.

## Verification

Primary verification:

```powershell
python -m unittest test_translation.TestDialectNormalize test_translation.TestProcStartCommentImmune -v
python scripts/check.py --suite quick
```

If implementation files change, also run:

```powershell
python scripts/check.py --suite all
```

## File Boundaries

Allowed files:

- `preprocess/*.py`
- `parser/cobol_columns.py`
- `test_translation.py`
- `tests/fixtures/*`
- `docs/操作记录/预处理回归样例操作记录.md`

Avoid changing:

- `translator/*`
- `asg/*`
- `scripts/diff_asg_vs_legacy.py`
