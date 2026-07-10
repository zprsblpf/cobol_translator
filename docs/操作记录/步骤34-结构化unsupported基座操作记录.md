# 步骤34 结构化unsupported基座操作记录

日期：2026-07-01

## 本次改动

- `translator/unsupported.py`
  - 新增 `UnsupportedEvent`。
  - 新增 `unsupported_comment(rule_id, kind, raw, reason)`，统一输出 `UNSUPPORTED[...]` Java 注释。
- `asg/visitor.py`
  - `LeafJavaVisitor.visit_Leaf` 未命中分支接入 `UNSUPPORTED[LEAF.UNKNOWN.001]`。
  - 已支持 leaf 仍沿用 `translate_leaf_stmt` 输出，不改变确定性翻译结果。
- `test_translation.py`
  - 更新 ASG leaf 未支持动词期望。
  - 新增未知 leaf 动词结构化 unsupported 标记测试。

## 验收

- `python -m unittest test_translation.TestUnifiedLeafEntry -v`
  - 7 tests OK。
- `python -m unittest test_translation.TestAsgLeafArithVisitor -v`
  - 3 tests OK。
- `python -m unittest test_translation.TestAsgIfVisitor -v`
  - 5 tests OK。
- `python scripts/check.py`
  - exit 0；内部 unittest 215 tests OK，skipped=2，并完成 minimal.cob parse-only、skeleton、no-LLM 翻译检查。
