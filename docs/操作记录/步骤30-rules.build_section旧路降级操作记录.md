# 步骤30 rules.build_section 旧路降级操作记录

日期：2026-06-30

## 本次改动

- `translator.skeleton_gen.body_context`
  - 新增 `_translate_paragraphs_body_legacy_fallback`，显式标识 legacy 只作为 ASG 失败回退入口。
  - `translate_paragraphs_body` 的异常路径改为调用该 fallback wrapper。
  - 保留 `_translate_paragraphs_body_legacy`，供 fallback wrapper、历史测试和 diff reference 使用。
- `test_translation.py`
  - 新增测试确认 fallback wrapper 与 legacy reference 输出一致。
  - 既有测试继续覆盖 ASG 成功不调用 legacy、ASG 失败才 fallback。
- `scripts/diff_asg_vs_legacy.py`
  - 更新 `SECTION` legacy 路径注释，明确 `rules.build_section` 是 reference renderer，不是主线入口。
- `docs/架构索引/项目总览.md`
  - 登记步骤30，并修正 `SectionJavaVisitor`/`structure_rewrite` 已进入主线的状态描述。
- `docs/superpowers/plans/2026-06-30-step30-legacy-section-demotion.md`
  - 记录本步执行计划。

## 验收

- `python -m unittest test_translation.TestMainlineSectionViaAsg -v`
  - 5 tests OK。
- `python -m unittest test_translation.TestMainlineSectionViaAsg test_translation.TestMainlinePendingRangeViaAsg -v`
  - 6 tests OK。
- `python scripts\diff_asg_vs_legacy.py tests\fixtures\minimal.cob --verb SECTION`
  - 2 条 SECTION 两路逐字符一致。
- `python -m py_compile translator\skeleton_gen\body_context.py scripts\diff_asg_vs_legacy.py test_translation.py`
  - OK。
- `python -m unittest test_translation`
  - 183 tests OK（skipped=2）。
- `python scripts\check.py`
  - OK。
