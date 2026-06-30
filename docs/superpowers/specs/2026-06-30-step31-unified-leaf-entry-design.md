# Step 31 Unified Leaf Entry Design

## Goal

Consolidate leaf statement dispatch behind one shared `translator.leaf` entry point, without adding support for new COBOL verbs.

## Scope

Step 31 only changes routing:

- Add a shared `translate_leaf_stmt(tokens, ctx)` entry in `translator.leaf`.
- Make `translator.rules.translate_leaf` delegate to that entry after applying its existing `struct_rebind` wrapper.
- Make `asg.visitor.LeafJavaVisitor.visit_Leaf` delegate to the same entry.
- Keep `rules._dispatch_leaf` available as a compatibility wrapper if existing tests or tools import it.
- Keep fallback behavior unchanged: unsupported verbs return `([], False)` and callers render their existing TODO placeholders.

Non-goals:

- Do not migrate STRING, UNSTRING, INSPECT, or other new verbs.
- Do not remove `rules._dispatch_leaf` in this step.
- Do not change SectionJavaVisitor behavior or legacy SECTION fallback behavior.

## Architecture

The current code has two leaf dispatch surfaces. `rules.translate_leaf` routes through `rules._dispatch_leaf`, while `LeafJavaVisitor.visit_Leaf` manually tries `translate_arith_assign` and `translate_control`. Step 31 moves that dispatch order into `translator.leaf.translate_leaf_stmt` so both mainline rules fallback and ASG visitor use the same function.

The shared entry point should preserve the existing rules dispatch order:

1. `MOVE`
2. `translate_arith_assign` for INITIALIZE, SET, ADD, SUBTRACT, MULTIPLY, DIVIDE, COMPUTE
3. `CALL`
4. `translate_control` for GO, GOBACK, STOP, EXIT, CONTINUE, NEXT

This slightly broadens the rules leaf path by allowing control leaf words through the unified entry, but `_skeleton_one` already handles control statements before leaf placeholder creation, so normal rules output should remain unchanged.

## Testing

Add focused tests in `test_translation.py`:

- `translate_leaf_stmt` matches the legacy rules dispatch for MOVE, arithmetic/assignment, CALL, and unsupported verbs.
- ASG `LeafJavaVisitor.visit_Leaf` uses the shared entry point for arithmetic/control leaves and still renders `// TODO-LEAF` for unsupported verbs.
- `rules.translate_leaf` and ASG `visit_Leaf` agree on the same shared-entry output for supported leaf cases.

Verification commands:

```powershell
python -m unittest test_translation.TestUnifiedLeafEntry -v
python -m unittest test_translation.TestAsgLeafArithVisitor test_translation.TestAsgControlVisitor -v
python -m unittest test_translation.TestMainlineSectionViaAsg test_translation.TestMainlinePendingRangeViaAsg -v
python -m unittest test_translation
python scripts/check.py
```

