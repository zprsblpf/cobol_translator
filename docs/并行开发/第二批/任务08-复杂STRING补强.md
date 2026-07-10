# 任务08：复杂 STRING 补强

## 目标

在现有简单 `STRING ... DELIMITED BY ... INTO ...` 基础上，补强 `WITH POINTER`、`ON OVERFLOW` 等复杂形态的保守支持或结构化 unsupported。

## 泳道

E：Leaf Rules

## 允许修改

- `config/rules/leaf_string.yaml`
- `translator/leaf/string.py`
- `test_translation.py`
- `docs/操作记录/步骤40-复杂STRING补强操作记录.md`

## 禁止修改

- `translator/skel/*`
- `asg/structure_rewrite.py`
- `translator/rules.py` 中非委托逻辑

## 依赖

- 建议等待任务02结构化 unsupported 基座。

## 实施步骤

1. 登记复杂 STRING rule_id。
2. 为 `WITH POINTER`、`ON OVERFLOW` 增加测试。
3. 对可安全翻译的形态实现确定性翻译。
4. 对暂不支持形态输出 structured unsupported。
5. 更新操作记录。

## 验收命令

```bash
python -m unittest test_translation.TestLeafStringExtract -v
python scripts/check.py --suite leaf
python scripts/check.py
```

## 完成标准

- 现有 STRING 测试不回退。
- 复杂形态不再匿名落 TODO。

