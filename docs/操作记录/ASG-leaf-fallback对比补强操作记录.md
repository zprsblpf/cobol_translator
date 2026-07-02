# ASG leaf fallback对比补强操作记录

## 本次修改

- 修改 `scripts/diff_asg_vs_legacy.py`，新增 `FALLBACK` 采样器。
- 修改 `test_translation.py`，新增 `TestDiffAsgVsLegacyLeafFallback`。
- 将既有“未固化 leaf”测试样例从已固化的 `UNSTRING` 调整为仍未固化的 `DISPLAY`。

## 设计说明

`FALLBACK` 采样器只采集 `rules.translate_leaf` 未命中的 simple leaf，并与 ASG `LeafJavaVisitor` 的 `// TODO-LEAF: ...` 输出逐字符对齐。它不改变任何已固化动词语义，只锁住 fallback 文案。

## 验证命令

```powershell
python -m unittest test_translation.TestDiffAsgVsLegacyLeafFallback -v
python scripts/check.py --suite asg
python scripts/check.py --suite all
```
