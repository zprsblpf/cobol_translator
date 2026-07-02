# 任务05：UNSTRING 叶子固化

## 目标

为保守子集的 `UNSTRING ... DELIMITED BY ... INTO ...` 增加确定性翻译，并接入统一 leaf 入口。

## 泳道

E：Leaf Rules

## 允许修改

- `config/rules/leaf_unstring.yaml`
- `translator/leaf/unstring.py`
- `translator/leaf/__init__.py`
- `test_translation.py`
- `docs/翻译标准/流程结构.md`
- `docs/操作记录/步骤37-UNSTRING叶子固化操作记录.md`

## 禁止修改

- `translator/skel/*`
- `asg/structure_rewrite.py`
- `translator/rules.py` 中非委托逻辑

## 依赖

- 建议等待任务02结构化 unsupported 基座。
- 建议等待任务04快速验证入口。

## 实施步骤

1. 新增 `config/rules/leaf_unstring.yaml`。
2. 新增 `TestLeafUnstringExtract`。
3. 实现 `translator/leaf/unstring.py`。
4. 在 `translate_leaf_stmt` 接入 `UNSTRING`。
5. 扩展 `TestUnifiedLeafEntry`。
6. 使用覆盖扫描器确认 `UNSTRING` unsupported 数下降。
7. 更新文档和操作记录。

## 验收命令

```bash
python -m unittest test_translation.TestLeafUnstringExtract -v
python -m unittest test_translation.TestUnifiedLeafEntry -v
python scripts/check.py --suite leaf
python scripts/check.py
```

## 完成标准

- 支持子集被确定性翻译。
- 不支持形态结构化 unsupported。
- legacy rules 与 ASG visitor 共用同一 leaf 实现。

