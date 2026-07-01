# 任务03：ASG leaf fallback 对比补强

## 目标

补齐未固化 leaf 在 ASG visitor 下的占位输出对比，避免新增动词时误改 fallback 行为。

## 泳道

B：ASG/Visitor 迁移

## 允许修改

- `asg/visitor.py`
- `scripts/diff_asg_vs_legacy.py`
- `test_translation.py`
- `docs/操作记录/ASG-leaf-fallback对比补强操作记录.md`

## 禁止修改

- `translator/leaf/*.py`
- `translator/skel/*.py`
- `parser/*`

## 依赖

- `asg.Leaf`
- `asg.LeafJavaVisitor`
- `scripts/diff_asg_vs_legacy.py`

## 实施步骤

1. 新增或扩展 `TestDiffAsgVsLegacy*`，覆盖未固化动词的 fallback 输出。
2. 运行测试确认当前对比缺口。
3. 在 `scripts/diff_asg_vs_legacy.py` 增加必要的 leaf fallback 采集或报告。
4. 如 visitor fallback 文案不一致，只在 `asg/visitor.py` 做最小修正。
5. 更新操作记录。

## 验收命令

```powershell
python -m unittest test_translation.TestAsgLeafArithVisitor test_translation.TestUnifiedLeafEntry -v
python scripts/check.py --suite asg
python scripts/check.py --suite all
```

## 合并备注

该任务不改变任何已固化动词语义，应在 UNSTRING/INSPECT 主线接入前或同时合并。
