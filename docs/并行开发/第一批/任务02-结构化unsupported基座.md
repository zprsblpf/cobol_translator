# 任务02：结构化 unsupported 基座

## 目标

建立统一的 `UNSUPPORTED[...]` 注释和事件结构，替代后续新增匿名 TODO。

## 泳道

B：Unsupported

## 允许修改

- `translator/unsupported.py`
- `asg/visitor.py`
- `test_translation.py`
- `docs/操作记录/步骤34-结构化unsupported基座操作记录.md`

## 禁止修改

- `translator/leaf/*` 中具体动词实现
- `translator/skel/*`
- `graph/nodes.py` 的 LLM 调用流程

## 依赖

- 规划：`docs/详细设计/本地确定性翻译完善规划.md`

## 实施步骤

1. 新增 `translator/unsupported.py`。
2. 提供 `unsupported_comment(rule_id, kind, raw, reason)`。
3. 先接入 `LeafJavaVisitor.visit_Leaf` 的未命中分支。
4. 新增测试：未支持动词输出 `UNSUPPORTED[LEAF.UNKNOWN.001]` 或等价规则编号。
5. 保持已支持动词输出不变。
6. 更新操作记录。

## 验收命令

```bash
python -m unittest test_translation.TestUnifiedLeafEntry -v
python -m unittest test_translation.TestAsgLeafArithVisitor -v
python scripts/check.py
```

## 完成标准

- 新增 unsupported 基座。
- 至少 ASG leaf fallback 接入结构化输出。
- 不破坏已支持 leaf 输出。

## 合并备注

建议在第二批 leaf 规则任务前合并。

