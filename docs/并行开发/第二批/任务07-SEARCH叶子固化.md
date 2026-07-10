# 任务07：SEARCH 叶子固化

## 目标

为保守子集的 COBOL `SEARCH` 增加确定性翻译，优先覆盖简单线性搜索。

## 泳道

E：Leaf Rules

## 允许修改

- `config/rules/leaf_search.yaml`
- `translator/leaf/search.py`
- `translator/leaf/__init__.py`
- `test_translation.py`
- `docs/翻译标准/流程结构.md`
- `docs/操作记录/步骤39-SEARCH叶子固化操作记录.md`

## 禁止修改

- `translator/skel/*`
- `asg/structure_rewrite.py`
- `translator/rules.py` 中非委托逻辑

## 依赖

- 建议等待任务02结构化 unsupported 基座。
- 可能依赖条件翻译能力 `translate_condition`。

## 实施步骤

1. 登记 `config/rules/leaf_search.yaml`。
2. 明确首版支持范围：简单数组、`WHEN cond`、无复杂 `VARYING`。
3. 新增 `TestLeafSearchExtract`。
4. 实现 `translator/leaf/search.py`。
5. 接入统一 leaf 入口。
6. 更新操作记录。

## 验收命令

```bash
python -m unittest test_translation.TestLeafSearchExtract -v
python scripts/check.py --suite leaf
python scripts/check.py
```

## 完成标准

- 简单 SEARCH 能确定性输出循环。
- 复杂 SEARCH 明确 unsupported。

