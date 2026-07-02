# Agent 执行协议

每个并行开发 agent 必须遵守本协议。

## 领取任务

1. 只领取一个任务包。
2. 先读任务包的“允许修改”和“禁止修改”。
3. 如需改禁止文件，必须先暂停并更新任务包，不直接越界。

## 开发流程

每个 agent 按固定步骤执行：

1. 读任务包。
2. 写或更新最小失败测试。
3. 实现最小代码。
4. 运行任务包验收命令。
5. 更新对应操作记录。
6. 运行最终本地闸口。

## 输出要求

每个 agent 完成后必须给出：

- 修改文件列表。
- 新增/修改测试列表。
- 验收命令和结果。
- 是否引入新的 unsupported rule_id。
- 是否有遗留风险。

## 冲突处理

高冲突文件：

- `test_translation.py`
- `translator/leaf/__init__.py`
- `asg/visitor.py`
- `graph/nodes.py`
- `scripts/check.py`

处理方式：

- 测试类按功能追加，不改其它测试类语义。
- `translator/leaf/__init__.py` 只增加 dispatcher 分支。
- `asg/visitor.py` 只接公共入口，不写业务翻译规则。
- `graph/nodes.py` 的 deterministic/LLM 行为只能由泳道 A 或 B 修改。

## 禁止事项

- 不在 `translator/rules.py` 扩大旧路径核心逻辑。
- 不新增匿名 TODO。
- 不让 deterministic 路径调用 LLM。
- 不把文档规范当作“已实现”标记，除非有代码和测试。
- 不静默 fallback；fallback 必须可观测。

