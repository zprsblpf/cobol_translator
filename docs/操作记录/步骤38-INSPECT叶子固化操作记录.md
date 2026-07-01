# 步骤38 INSPECT叶子固化操作记录

日期：2026-07-01

## 本次改动

- `config/rules/leaf_inspect.yaml`
  - 登记 `LEAF.INSPECT.001`，声明 INSPECT 确定性支持范围与 fallback 策略。
- `translator/leaf/inspect.py`
  - 新增 `translate_inspect(tokens, ctx)`。
  - 支持 `INSPECT ... TALLYING ... FOR CHARACTERS`。
  - 支持 `INSPECT ... TALLYING ... FOR ALL ...`。
  - 支持 `INSPECT ... REPLACING ALL/FIRST/LEADING ... BY ...`。
  - 对 `BEFORE`、`AFTER`、`CONVERTING`、多子句等不支持形态返回 `([], False)`。
- `translator/leaf/__init__.py`
  - 导出 `translate_inspect`。
  - `translate_leaf_stmt` 增加 `INSPECT` 分支，并保留并行任务已有分支顺序。
- `test_translation.py`
  - 新增 `TestLeafInspectExtract`。
  - 扩展 `TestUnifiedLeafEntry`，覆盖 rules/leaf 统一入口与 ASG leaf 输出一致性。
- `docs/翻译标准/流程结构.md`
  - 追加 INSPECT 叶子语句的确定性支持范围和暂不支持范围。

## 验收

- `python -m unittest test_translation.TestLeafInspectExtract -v`
  - 6 tests OK。
- `python scripts/check.py --suite leaf`
  - 81 tests OK。
- `python scripts/check.py`
  - 240 tests OK，skipped=2（本地 vLLM 不可用的既有模型测试）。
  - 完成 `minimal.cob` parse-only、skeleton 生成、no-LLM 翻译检查。

## unsupported rule_id

- 本任务未新增 unsupported rule_id。
- 不支持的 INSPECT 形态返回 `([], False)`，由上层既有 `LEAF.UNKNOWN.001` 结构化占位承接。

## 遗留风险

- `INSPECT ... TALLYING ... FOR ALL ...` 使用 Java `replace` 差分计算非重叠出现次数；复杂 COBOL 作用域、重叠语义、多子句仍保守未支持。
- `BEFORE` / `AFTER` / `CONVERTING` 未固化。
