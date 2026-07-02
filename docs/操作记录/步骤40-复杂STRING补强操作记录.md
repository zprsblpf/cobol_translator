# 步骤40 复杂STRING补强操作记录

日期：2026-07-02

## 本次改动

- `config/rules/leaf_string.yaml`
  - 登记简单 STRING 支持规则与复杂 STRING unsupported rule_id。
- `translator/leaf/string.py`
  - `WITH POINTER` 输出 `UNSUPPORTED[LEAF.STRING.POINTER.001]`。
  - `ON OVERFLOW` / `NOT ON OVERFLOW` 输出 `UNSUPPORTED[LEAF.STRING.OVERFLOW.001]`。
  - 保持既有简单 `STRING ... DELIMITED BY ... INTO ...` 输出不变。
- `test_translation.py`
  - 扩展 `TestLeafStringExtract`，覆盖复杂 STRING 结构化 unsupported。

## 验收

- `python -m unittest test_translation.TestLeafStringExtract -v`
  - 7 tests OK。
- `python scripts/check.py --suite leaf`
  - 82 tests OK。
- `python scripts/check.py`
  - exit 0；内部 unittest 241 tests OK，skipped=2，并完成 minimal.cob parse-only、skeleton、no-LLM 翻译检查。

## unsupported rule_id

- 新增 `LEAF.STRING.POINTER.001`。
- 新增 `LEAF.STRING.OVERFLOW.001`。

## 遗留风险

- 本步未实现 POINTER 递增、目标容量和 OVERFLOW 分支语义，仅将复杂形态结构化可观测。
