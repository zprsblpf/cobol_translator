# 任务01：UNSTRING 叶子固化

## 目标

为保守子集的 `UNSTRING ... DELIMITED BY ... INTO ...` 增加确定性翻译，并接入统一 leaf 入口。

## 泳道

A：Leaf 动词固化

## 允许修改

- `translator/leaf/unstring.py`
- `translator/leaf/__init__.py`
- `test_translation.py`
- `docs/详细设计/步骤33-UNSTRING叶子语句固化设计.md`
- `docs/操作记录/步骤33-UNSTRING叶子语句固化操作记录.md`

## 禁止修改

- `translator/skel/*`
- `asg/structure_rewrite.py`
- `translator/rules.py` 中非委托逻辑

## 依赖

- `translator.leaf.translate_leaf_stmt`
- `translator.leaf.expr._operand`
- `translator.leaf.expr._lvalue`

## 实施步骤

1. 新增 `TestLeafUnstringExtract`，覆盖支持子集和不支持形态。
2. 扩展 `TestUnifiedLeafEntry`，验证 `translate_leaf_stmt` 统一入口命中。
3. 扩展 ASG leaf visitor 测试，验证 visitor 共享输出。
4. 新建 `translator/leaf/unstring.py`。
5. 在 `translator/leaf/__init__.py` 接入 `translate_unstring`。
6. 更新设计文档和操作记录。

## 验收命令

```powershell
python -m unittest test_translation.TestLeafUnstringExtract test_translation.TestUnifiedLeafEntry -v
python scripts/check.py --suite leaf
python scripts/check.py --suite all
```

## 合并备注

该任务只依赖 leaf 公共入口，可与 INSPECT 并行开发，但合并时需要协调 `translator/leaf/__init__.py` 和 `test_translation.py` 的插入位置。
