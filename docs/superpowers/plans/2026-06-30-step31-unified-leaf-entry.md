# Step 31 Unified Leaf Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make rules and ASG visitor leaf rendering share one `translator.leaf` dispatch entry without migrating new COBOL verbs.

**Architecture:** Add `translate_leaf_stmt(tokens, ctx)` to the `translator.leaf` facade and delegate both `rules.translate_leaf` and `LeafJavaVisitor.visit_Leaf` to it. Keep `rules._dispatch_leaf` as a compatibility wrapper so old tests/tools keep working while its implementation becomes a thin delegate.

**Tech Stack:** Python 3.12, `unittest`, existing translator/rules/asg modules.

---

### Task 1: Lock Shared Leaf Dispatch With Failing Tests

**Files:**
- Modify: `test_translation.py`
- Test: `test_translation.py`

- [ ] **Step 1: Add `TestUnifiedLeafEntry`**

Add a focused test class near the existing leaf tests:

```python
class TestUnifiedLeafEntry(unittest.TestCase):
    def _ctx(self):
        return _leaf_ctx(field_type_map={"wsaaCount": {"type": "int"}},
                         system_programs={"SYSERR": {"java_code": "throw new RuntimeException()"}})

    def test_translate_leaf_stmt_matches_rules_dispatch_for_supported_verbs(self):
        from translator.leaf import translate_leaf_stmt
        import translator.rules as rules

        ctx = self._ctx()
        cases = [
            "MOVE 1 TO WSAA-COUNT",
            "ADD 1 TO WSAA-COUNT",
            "CALL 'SYSERR'",
        ]
        for line in cases:
            toks = line.split()
            self.assertEqual(translate_leaf_stmt(toks, ctx), rules._dispatch_leaf(toks, ctx))

    def test_translate_leaf_stmt_handles_control_leaf_words(self):
        from translator.leaf import translate_leaf_stmt

        self.assertEqual(translate_leaf_stmt(["CONTINUE"], self._ctx()), ([";  // CONTINUE"], True))

    def test_translate_leaf_stmt_falls_through_for_unmigrated_verbs(self):
        from translator.leaf import translate_leaf_stmt

        self.assertEqual(translate_leaf_stmt("STRING WSAA-A INTO WSAA-B".split(), self._ctx()),
                         ([], False))

    def test_rules_and_asg_leaf_share_supported_output(self):
        from asg import Leaf, LeafJavaVisitor
        from translator.segmenter import Stmt
        import translator.rules as rules

        ctx = self._ctx()
        stmt = Stmt(kind="simple", tokens="ADD 1 TO WSAA-COUNT".split(), raw="ADD 1 TO WSAA-COUNT")
        node = Leaf(tokens=list(stmt.tokens), raw=stmt.raw)

        lines, matched = rules.translate_leaf(stmt, ctx)
        self.assertTrue(matched)
        self.assertEqual(LeafJavaVisitor(ctx).visit(node), lines)
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```powershell
python -m unittest test_translation.TestUnifiedLeafEntry -v
```

Expected before implementation: import failure for `translate_leaf_stmt`.

### Task 2: Add Unified Leaf Entry

**Files:**
- Modify: `translator/leaf/__init__.py`
- Test: `test_translation.py`

- [ ] **Step 1: Implement `translate_leaf_stmt`**

Add imports for `translate_call` and existing helpers are already present. Add:

```python
def translate_leaf_stmt(tokens: list[str], ctx: LeafCtx) -> tuple[list[str], bool]:
    if not tokens:
        return [], False
    verb = tokens[0].upper()
    try:
        if verb == "MOVE":
            return translate_move(tokens, ctx)
        lines, ok = translate_arith_assign(tokens, ctx)
        if ok:
            return lines, ok
        if verb == "CALL":
            return translate_call(tokens, ctx)
        return translate_control(tokens, ctx)
    except (ValueError, IndexError):
        return [], False
```

Add `"translate_leaf_stmt"` to `__all__`.

- [ ] **Step 2: Run the new tests**

Run:

```powershell
python -m unittest test_translation.TestUnifiedLeafEntry -v
```

Expected: tests still fail because callers have not been delegated yet or pass only the direct-entry tests.

### Task 3: Delegate Existing Callers

**Files:**
- Modify: `translator/rules.py`
- Modify: `asg/visitor.py`
- Test: `test_translation.py`

- [ ] **Step 1: Delegate rules dispatch**

In `translator/rules.py`, import `translate_leaf_stmt` from `translator.leaf`. Replace `_dispatch_leaf` body with:

```python
def _dispatch_leaf(toks: list[str], ctx: Ctx) -> tuple[list[str], bool]:
    return translate_leaf_stmt(toks, ctx)
```

Keep the function name for compatibility.

- [ ] **Step 2: Delegate ASG leaf visitor**

In `asg/visitor.py`, import `translate_leaf_stmt` and replace `visit_Leaf` render body with:

```python
def _render():
    lines, ok = translate_leaf_stmt(node.tokens, self.ctx)
    return lines if ok else [f"// TODO-LEAF: {node.raw}"]
```

- [ ] **Step 3: Run targeted tests**

Run:

```powershell
python -m unittest test_translation.TestUnifiedLeafEntry test_translation.TestAsgLeafArithVisitor test_translation.TestAsgControlVisitor -v
```

Expected: OK.

### Task 4: Step Docs

**Files:**
- Create: `docs/详细设计/步骤31-叶子翻译统一入口设计.md`
- Create: `docs/操作记录/步骤31-叶子翻译统一入口操作记录.md`
- Modify: `docs/架构索引/项目总览.md`

- [ ] **Step 1: Add design doc**

Document the narrow scope, non-goals, dispatch order, and test strategy from the approved design.

- [ ] **Step 2: Add operation record**

Record changed files and verification commands.

- [ ] **Step 3: Update architecture index**

Add one step 31 line after step 30 stating that rules and ASG leaf rendering now share `translate_leaf_stmt`.

### Task 5: Full Verification

**Files:**
- No production edits.

- [ ] **Step 1: Run targeted ASG/mainline tests**

```powershell
python -m unittest test_translation.TestAsgLeafArithVisitor test_translation.TestAsgControlVisitor test_translation.TestMainlineSectionViaAsg test_translation.TestMainlinePendingRangeViaAsg -v
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

- [ ] **Step 4: Check scoped diff**

```powershell
git diff -- translator/leaf/__init__.py translator/rules.py asg/visitor.py test_translation.py docs
```

Expected: diff only contains step 31 scoped changes.

