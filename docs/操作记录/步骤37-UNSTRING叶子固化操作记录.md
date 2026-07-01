# 步骤37 UNSTRING叶子固化操作记录

日期：2026-07-01

## 本次改动

- `config/rules/leaf_unstring.yaml`
  - 记录 `UNSTRING ... DELIMITED BY ... INTO ...` 的保守支持子集与不支持形态。
- `translator/leaf/unstring.py`
  - 新增 `translate_unstring(tokens, ctx)`。
  - 支持单源、单分隔符、顺序写入一个或多个目标字段。
  - 生成局部代码块包住 `__unstringParts`，避免重复临时变量声明。
  - 对 `WITH POINTER`、`TALLYING/COUNT IN`、`DELIMITER IN`、`ON OVERFLOW`、`ALL/OR` 分隔符输出结构化 unsupported。
- `translator/leaf/__init__.py`
  - 导出 `translate_unstring`。
  - `translate_leaf_stmt` 增加 `UNSTRING` 分支，legacy rules 与 ASG visitor 共享同一 leaf 实现。
- `test_translation.py`
  - 新增 `TestLeafUnstringExtract`。
  - 扩展 `TestUnifiedLeafEntry` 的分派与 ASG 输出一致性测试。
  - 将原先用 `UNSTRING` 表示未固化叶子的占位测试改为 `DISPLAY`。
- `docs/翻译标准/流程结构.md`
  - 追加 UNSTRING 叶子语句支持边界和 unsupported rule_id。

## 新增 unsupported rule_id

- `LEAF.UNSTRING.POINTER.001`
- `LEAF.UNSTRING.COUNT.001`
- `LEAF.UNSTRING.DELIMITER.001`
- `LEAF.UNSTRING.OVERFLOW.001`
- `LEAF.UNSTRING.DELIMITER.002`

## 验收

- `python -m unittest test_translation.TestLeafUnstringExtract -v`
  - 6 tests OK。
- `python -m unittest test_translation.TestUnifiedLeafEntry -v`
  - 9 tests OK。
- `python scripts/scan_rule_coverage.py /tmp/unstring_coverage.cob --format text`
  - `UNSTRING supported=1 unsupported=0`。
- `python scripts/scan_rule_coverage.py scripts/spike_proleap/cleaned_ZPOLDWNM.cob --format text`
  - exit 0；真实样本当前未出现 `UNSTRING` verb。
- `python scripts/check.py --suite leaf`
  - 82 tests OK。
- `python scripts/check.py`
  - exit 0；241 tests OK，skipped=2，并完成 minimal.cob parse-only、skeleton、no-LLM 翻译检查。

## 遗留风险

- 当前子集不覆盖 `WITH POINTER`、`TALLYING/COUNT IN`、`DELIMITER IN`、`ON OVERFLOW`、多分隔符等完整 COBOL UNSTRING 语义。
- 多目标翻译采用 Java `split(..., limit)`，最后一个目标保留剩余文本；更复杂的 COBOL pointer/count/delimiter 语义需后续单独固化。
