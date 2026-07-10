# 任务06：INSPECT 叶子固化

## 目标

为保守子集的 `INSPECT ... REPLACING` / `INSPECT ... TALLYING` 增加确定性翻译。

## 泳道

E：Leaf Rules

## 允许修改

- `config/rules/leaf_inspect.yaml`
- `translator/leaf/inspect.py`
- `translator/leaf/__init__.py`
- `test_translation.py`
- `docs/翻译标准/流程结构.md`
- `docs/操作记录/步骤38-INSPECT叶子固化操作记录.md`

## 禁止修改

- `translator/skel/*`
- `asg/structure_rewrite.py`
- `translator/rules.py` 中非委托逻辑

## 依赖

- 建议等待任务02结构化 unsupported 基座。

## 实施步骤

1. 登记 `config/rules/leaf_inspect.yaml`。
2. 新增 `TestLeafInspectExtract`。
3. 实现 `translator/leaf/inspect.py`。
4. 接入统一 leaf 入口。
5. 扩展 unified entry 测试。
6. 更新操作记录。

## 验收命令

```bash
python -m unittest test_translation.TestLeafInspectExtract -v
python scripts/check.py --suite leaf
python scripts/check.py
```

## 完成标准

- 支持形态确定性翻译。
- 不支持形态返回 structured unsupported 或 `([], False)` 由上层结构化。

