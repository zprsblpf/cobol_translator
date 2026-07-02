# 任务02：INSPECT 叶子固化

## 目标

为保守子集的 `INSPECT ... REPLACING` 或 `INSPECT ... TALLYING` 增加确定性翻译。

## 泳道

A：Leaf 动词固化

## 允许修改

- `translator/leaf/inspect.py`
- `translator/leaf/__init__.py`
- `test_translation.py`
- `docs/详细设计/步骤34-INSPECT叶子语句固化设计.md`
- `docs/操作记录/步骤34-INSPECT叶子语句固化操作记录.md`

## 禁止修改

- `translator/skel/*`
- `asg/structure_rewrite.py`
- `translator/rules.py` 中非委托逻辑

## 依赖

- `translator.leaf.translate_leaf_stmt`
- `translator.leaf.expr._operand`
- `translator.leaf.expr._lvalue`

## 实施步骤

1. 新增 `TestLeafInspectExtract`，覆盖 `REPLACING`、`TALLYING` 和不支持形态。
2. 扩展 `TestUnifiedLeafEntry`，验证 `translate_leaf_stmt` 统一入口命中。
3. 扩展 ASG leaf visitor 测试，验证 visitor 共享输出。
4. 新建 `translator/leaf/inspect.py`。
5. 在 `translator/leaf/__init__.py` 接入 `translate_inspect`。
6. 更新设计文档和操作记录。

## 验收命令

```powershell
python -m unittest test_translation.TestLeafInspectExtract test_translation.TestUnifiedLeafEntry -v
python scripts/check.py --suite leaf
python scripts/check.py --suite all
```

## 合并备注

该任务与 UNSTRING 同属 leaf 泳道，默认可以并行开发。合并顺序以先完成、先通过 `--suite leaf` 为准。
