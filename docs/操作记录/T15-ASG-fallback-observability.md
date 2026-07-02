# T15 ASG fallback observability

## Changed

- `translator/rules.py`: added `Ctx.asg_fallback_events`.
- `translator/skeleton_gen/body_context.py`: records structured ASG fallback events before invoking the legacy fallback renderer.
- `scripts/check.py`: includes `test_translation.TestMainlineSectionViaAsg` in `--suite asg`.
- `test_translation.py`: asserts forced ASG failure records fallback metadata and is covered by the ASG verification suite.

## Behavior

ASG rendering still falls back to the legacy renderer on exception. The fallback path now records:

- `exception_type`
- `message`
- `paragraph_labels`
- `force_sm`

Call `asg_fallback_summary(ctx)` to inspect the count and event list.

## Verification

```powershell
python -m unittest test_translation.TestMainlineSectionViaAsg -v
python scripts/check.py --suite asg
```
