# 步骤28 写 IO 结构吸收迁 visitor 操作记录

日期：2026-06-29

## 本次改动

- 新增 `IoWriteSingleStmt`，用于承载 UPDAT/WRITR/DELET 单条写 IO 结构吸收结果。
- `asg.structure_rewrite` 新增 `rewrite_write_single`，识别 setup + CALL + 可选 STATUZ error IF。
- `SectionJavaVisitor` 新增写 IO 渲染：
  - WRITR/init params -> `new Record` + setters + `repo.save(entity)`；
  - UPDAT/reuse -> setters + `repo.save(entity)`；
  - DELET -> `repo.delete(entity)`；
  - STATUZ `NOT = O-K` -> `try/catch`。
- 补充 ASG rewrite/visitor 测试 7 条，并与旧路线逐字符串比对。

## 验收

- `python -m unittest test_translation.TestAsgWriteSingleRewrite test_translation.TestAsgWriteSingleVisitor -v`
  - 7 tests OK。
- `python -m unittest test_translation`
  - 176 tests OK（skipped=2）。
- `python scripts\diff_asg_vs_legacy.py tests\fixtures\minimal.cob --verb SECTION`
  - 2 条 SECTION 两路逐字符一致。
- `python test_smoke.py`
  - 1 test OK。
- `python -m py_compile asg\structure_rewrite.py asg\section_visitor.py asg\visitor.py asg\nodes.py`
  - OK。
