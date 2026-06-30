# Step 30 Legacy SECTION Demotion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `rules.build_section` explicitly legacy-only after the mainline SECTION renderer moved to `SectionJavaVisitor`.

**Architecture:** Keep the ASG visitor as the default mainline path in `translator.skeleton_gen.body_context`. Preserve the legacy SECTION renderer for fallback and diff tooling only, guarded by a narrow helper and tests that fail if normal mainline rendering silently uses legacy.

**Tech Stack:** Python 3.12, `unittest`, existing COBOL parser/translator modules, ASG visitor path.

---

### Task 1: Lock Legacy Routing With Failing Tests

**Files:**
- Modify: `test_translation.py`
- Test: `test_translation.py`

- [ ] **Step 1: Write the failing test**

Add a test in `TestMainlineSectionViaAsg` that monkeypatches `_translate_paragraphs_body_legacy` to raise and asserts normal `translate_section_body` still renders through ASG:

```python
def test_mainline_does_not_call_legacy_when_asg_succeeds(self):
    from translator.skeleton_gen import body_context as bc

    prog, sec = self._program("MOVE 1 TO A.")
    ctx, ws = bc.build_body_ctx(prog)
    original = bc._translate_paragraphs_body_legacy

    def _boom(*_args, **_kwargs):
        raise AssertionError("legacy path should not be called")

    bc._translate_paragraphs_body_legacy = _boom
    try:
        out = bc.translate_section_body(sec.lines, ctx, ws, "", self._known_methods(prog, ctx))
    finally:
        bc._translate_paragraphs_body_legacy = original

    self.assertIn("a = 1;", out)
```

Add a second test that monkeypatches ASG to fail and verifies the explicit legacy fallback is still available:

```python
def test_mainline_uses_legacy_only_as_fallback(self):
    from translator.skeleton_gen import body_context as bc

    prog, sec = self._program("MOVE 1 TO A.")
    ctx, ws = bc.build_body_ctx(prog)
    original = bc._translate_paragraphs_body_asg

    def _boom(*_args, **_kwargs):
        raise RuntimeError("forced ASG failure")

    bc._translate_paragraphs_body_asg = _boom
    try:
        out = bc.translate_section_body(sec.lines, ctx, ws, "", self._known_methods(prog, ctx))
    finally:
        bc._translate_paragraphs_body_asg = original

    self.assertIn("a = 1;", out)
```

- [ ] **Step 2: Run tests to verify they fail before implementation**

Run:

```powershell
python -m unittest test_translation.TestMainlineSectionViaAsg -v
```

Expected before implementation: the first test fails because the existing output is prefixed as `wsaa.a = 1;`, or because the helper API needs the new explicit fallback semantics.

### Task 2: Make Legacy Boundary Explicit

**Files:**
- Modify: `translator/skeleton_gen/body_context.py`
- Test: `test_translation.py`

- [ ] **Step 1: Add explicit helper names and comments**

Rename or wrap the fallback helper so the public internal name makes the intended boundary clear:

```python
def _translate_paragraphs_body_legacy_fallback(...):
    """Legacy SECTION renderer retained only for ASG failure fallback and diff tooling."""
    return _translate_paragraphs_body_legacy(...)
```

Update `translate_paragraphs_body` to call `_translate_paragraphs_body_legacy_fallback` only inside the `except Exception` block.

- [ ] **Step 2: Keep old helper available for existing tests and diff tooling**

Do not remove `_translate_paragraphs_body_legacy`; tests and compare tooling may still call it directly as a known legacy reference.

- [ ] **Step 3: Run targeted tests**

Run:

```powershell
python -m unittest test_translation.TestMainlineSectionViaAsg test_translation.TestMainlinePendingRangeViaAsg -v
```

Expected: all tests in both classes pass.

### Task 3: Update Diff Tool Wording

**Files:**
- Modify: `scripts/diff_asg_vs_legacy.py`

- [ ] **Step 1: Update SECTION docstrings**

Change `_legacy_sections` docstring to say `rules.build_section` is a legacy reference renderer, not a mainline path.

- [ ] **Step 2: Run SECTION diff**

Run:

```powershell
python scripts\diff_asg_vs_legacy.py tests\fixtures\minimal.cob --verb SECTION
```

Expected: `[OK] ... [SECTION]`.

### Task 4: Write Project Step Docs

**Files:**
- Create: `docs/详细设计/步骤30-rules.build_section旧路降级设计.md`
- Create: `docs/操作记录/步骤30-rules.build_section旧路降级操作记录.md`
- Modify: `docs/架构索引/项目总览.md`

- [ ] **Step 1: Add design doc**

Document that step 30 keeps legacy code for fallback and diff reference only, and explicitly does not delete old structure absorption code.

- [ ] **Step 2: Add operation record**

Record changed files and verification commands.

- [ ] **Step 3: Update architecture index**

Add one line after step 29 stating step 30 demotes `rules.build_section` to fallback/reference status.

### Task 5: Full Verification

**Files:**
- No production edits.

- [ ] **Step 1: Run targeted tests**

```powershell
python -m unittest test_translation.TestMainlineSectionViaAsg test_translation.TestMainlinePendingRangeViaAsg -v
```

Expected: OK.

- [ ] **Step 2: Run full test module**

```powershell
python -m unittest test_translation
```

Expected: OK, with local vLLM tests skipped if the model service is unavailable.

- [ ] **Step 3: Run smoke/check script**

```powershell
python scripts/check.py
```

Expected: command exits 0.

- [ ] **Step 4: Check git diff**

```powershell
git diff -- translator/skeleton_gen/body_context.py scripts/diff_asg_vs_legacy.py test_translation.py docs
```

Expected: diff only contains step 30 scoped changes.
