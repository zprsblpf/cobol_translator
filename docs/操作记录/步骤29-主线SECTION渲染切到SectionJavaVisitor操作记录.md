# 步骤29 主线 SECTION 渲染切到 SectionJavaVisitor 操作记录

日期：2026-06-29

## 本次改动

- `asg.builder` 新增 `build_paragraphs`，支持从 `[(label, body_lines)]` 构造 ASG Paragraph。
- `asg.__init__` 导出 `build_asg_paragraphs`。
- `translator.skeleton_gen.body_context`：
  - 旧 `rules.build_section` 路径封装为 `_translate_paragraphs_body_legacy`；
  - 新增 `_translate_paragraphs_body_asg`；
  - `translate_paragraphs_body` 默认走 ASG `SectionJavaVisitor`，异常时回退 legacy。
- 补充主线级测试，覆盖普通 SECTION、写 IO 结构吸收、pending range `force_sm=True` 和 fallback。

## 验收

- `python -m unittest test_translation.TestMainlineSectionViaAsg test_translation.TestMainlinePendingRangeViaAsg -v`
  - 5 tests OK。
- `python -m unittest test_translation`
  - 181 tests OK（skipped=2）。
- `python scripts\diff_asg_vs_legacy.py tests\fixtures\minimal.cob --verb SECTION`
  - 2 条 SECTION 两路逐字符一致。
- `python test_smoke.py`
  - 1 test OK。
- `python -m py_compile translator\skeleton_gen\body_context.py asg\builder.py asg\__init__.py asg\section_visitor.py asg\structure_rewrite.py asg\nodes.py`
  - OK。
