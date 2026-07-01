# 步骤39 SEARCH叶子固化操作记录

日期：2026-07-01

## 本次改动

- `config/rules/leaf_search.yaml`
  - 登记 `LEAF.SEARCH.001`，状态为 implemented。
  - 明确支持 `SEARCH <array> VARYING <index> WHEN <condition>`。
- `translator/leaf/search.py`
  - 新增 `translate_search`。
  - 已知数组 + 显式 `VARYING` + 单个可翻译 `WHEN` 条件输出确定性 `for` 线性扫描。
  - `SEARCH ALL`、`AT END`、缺少 `VARYING`、未知数组、无法翻译条件等输出结构化 unsupported。
- `translator/leaf/__init__.py`
  - 在统一 leaf dispatcher 中接入 `SEARCH` 分支。
- `test_translation.py`
  - 新增 `TestLeafSearchExtract`，覆盖纯函数、统一入口、ASG Leaf 和复杂形态 unsupported。
- `docs/翻译标准/流程结构.md`
  - 补充 SEARCH 首版支持范围与 unsupported 边界。

## 验收

- `python -m unittest test_translation.TestLeafSearchExtract -v`
  - 5 tests OK。
- `python scripts/check.py --suite leaf`
  - 81 tests OK。
- `python scripts/check.py`
  - 240 tests OK，skipped=2。
  - minimal parse-only、skeleton 生成、`main.py --no-llm` 均完成。

## unsupported rule_id

- 新增 `LEAF.SEARCH.001`。

## 遗留风险

- 首版不处理 COBOL 表隐式索引名；缺少显式 `VARYING` 时保守 unsupported。
- `AT END` / `NOT AT END` 与带 action body 的多行 SEARCH 尚未固化。
