# T15 ASG Fallback Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record ASG-to-legacy fallback events and include that behavior in the ASG verification suite.

**Architecture:** Keep the legacy fallback behavior unchanged, but attach structured fallback events to the existing rules context. The verification entry point will include the mainline ASG fallback tests in the `asg` suite so regressions are counted by the normal command.

**Tech Stack:** Python dataclasses, `unittest`, existing `scripts/check.py` verification runner.

---

### Task 1: Count Mainline ASG Fallbacks

**Files:**
- Modify: `translator/rules.py`
- Modify: `translator/skeleton_gen/body_context.py`
- Modify: `scripts/check.py`
- Modify: `test_translation.py`
- Create: `docs/操作记录/T15-ASG-fallback-observability.md`

- [x] **Step 1: Write failing tests**

Add tests in `TestMainlineSectionViaAsg` that assert `body_context.asg_fallback_summary(ctx)` reports one event after forced ASG failure, including `RuntimeError`, message text, paragraph labels, and `force_sm`. Add a test asserting `scripts.check.SUITES["asg"]` includes `test_translation.TestMainlineSectionViaAsg`.

- [x] **Step 2: Run tests to verify RED**

Run: `python -m unittest test_translation.TestMainlineSectionViaAsg -v`
Expected: FAIL/ERROR because the fallback summary API is not implemented yet and the asg suite does not include the class.

- [x] **Step 3: Implement minimal tracking**

Add `asg_fallback_events: list` to `translator.rules.Ctx`. In `translator.skeleton_gen.body_context`, add helpers `record_asg_fallback(ctx, exc, paras_raw, force_sm)` and `asg_fallback_summary(ctx)`. Call the recorder in the `translate_paragraphs_body` exception path before invoking `_translate_paragraphs_body_legacy_fallback`.

- [x] **Step 4: Include the tests in ASG verification**

Add `test_translation.TestMainlineSectionViaAsg` to `scripts.check.SUITES["asg"]`.

- [x] **Step 5: Run targeted verification**

Run: `python -m unittest test_translation.TestMainlineSectionViaAsg -v`
Expected: PASS.

Run: `python scripts/check.py --suite asg`
Expected: PASS.

- [x] **Step 6: Document the operation**

Create `docs/操作记录/T15-ASG-fallback-observability.md` with the changed files, behavior, and verification commands.
