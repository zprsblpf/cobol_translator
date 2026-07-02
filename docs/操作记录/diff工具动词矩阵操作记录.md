# diff 工具动词矩阵操作记录

## 本次修改

- 修改 `scripts/diff_asg_vs_legacy.py`，新增 `VERB_MATRIX`，集中声明 diff 工具支持的动词族、所属泳道、比对范围和迁移状态。
- 修改 `test_translation.py`，新增 `TestDiffAsgVsLegacyVerbMatrix`，锁定矩阵顺序、字段形态以及矩阵与 `_SAMPLERS` 的一一对应关系。
- 新增 `docs/superpowers/plans/2026-07-01-diff-verb-matrix.md`，记录本次小步实现计划。

## 结果

`VERB_MATRIX` 只提供稳定元数据，不改变 `--verb` 参数、`_SAMPLERS` 调度或 legacy/ASG 比对输出。后续并行 worker 可直接读取矩阵选择精确 parity 闸。

## 验证命令

```powershell
python -m unittest test_translation.TestDiffAsgVsLegacyVerbMatrix -v
python -m unittest test_translation.TestDiffAsgVsLegacy test_translation.TestDiffAsgVsLegacyIf test_translation.TestDiffAsgVsLegacyArith -v
python scripts/check.py --suite asg
python scripts/check.py --suite all
```
