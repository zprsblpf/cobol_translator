# T16 deterministic multi-file report output

## Changed

- `scripts/deterministic_report.py`: added a deterministic JSON report API and CLI.
- `translator/skeleton_gen/render_skeleton.py`: added `render_skeleton_with_context(program)` while keeping `render_skeleton(program)` compatible.
- `test_t16_deterministic_report.py`: added coverage for stable multi-input report output.
- `scripts/check.py`: includes T16 in `--suite quick` through py_compile and the focused unittest.

## Report Shape

The JSON report has stable key ordering and includes:

- `schema_version`
- `command.inputs`
- `command.output_dir`
- `command.report_path`
- `files[]`: input, output, program id, class name, line count, TODO count, risk count, risks, ASG fallback summary
- `totals`: file count, TODO count, risk count, ASG fallback count

## Verification

```powershell
python -m unittest test_t16_deterministic_report -v
python scripts/deterministic_report.py --in tests/fixtures/minimal.cob --out-dir output/t16-report --report output/t16-report/report.json
python scripts/check.py --suite quick
```
