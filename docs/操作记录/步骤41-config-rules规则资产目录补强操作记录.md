# 步骤41 config/rules规则资产目录补强操作记录

日期：2026-07-02

## 本次改动

- `scripts/scan_rule_coverage.py`
  - 新增 `load_rule_assets()`，通过 PyYAML `safe_load` 读取 `config/rules/*.yaml` 的规则登记。
  - 覆盖报告新增 `rule_assets` 顶层字段。
  - 动词报告在命中规则资产时附带 `rules` 与 `rule_status`。
  - text/markdown 输出显示 implemented/planned/unsupported 规则资产数量。
- `test_smoke.py`
  - 增加规则资产加载 smoke 测试。

## 验收

- `python scripts/scan_rule_coverage.py tests/fixtures/minimal.cob`
  - exit 0；输出包含 `rule_assets`，并读取 INSPECT/SEARCH/STRING/UNSTRING 规则资产。
- `python -m unittest test_smoke -v`
  - 9 tests OK。
- `python scripts/check.py --suite quick`
  - exit 0。
- `python scripts/check.py`
  - exit 0；内部 unittest 242 tests OK，skipped=2，并完成 minimal.cob parse-only、skeleton、no-LLM 翻译检查。
## unsupported rule_id

- 本次未新增 unsupported rule_id。

## 遗留风险

- 已改用 PyYAML `safe_load`，支持标准 YAML；规则归一仍要求每条规则具备 `rule_id`/`id` 与 `verb`。
