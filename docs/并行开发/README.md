# 并行开发 Agent 任务包

本目录把 `docs/详细设计/本地确定性翻译完善规划.md` 拆成可并行开发的 agent 任务包。

目标不是让多个 agent 随意改同一片代码，而是把后续工作固定成泳道、边界、依赖和验收命令，使多个 agent 可以并行推进、低冲突合并。

## 固定泳道

| 泳道 | 名称 | 职责 | 主要文件 |
|---|---|---|---|
| A | 产品主线 | deterministic CLI、多文件本地输出、入口控制流、LLM 禁用 | `main.py`, `graph/*`, `translator/assemble.py`, `translator/skeleton*.py` |
| B | Unsupported | 结构化 unsupported 注释、事件收集、报告输出 | `translator/unsupported.py`, `asg/visitor.py`, `graph/nodes.py` |
| C | Coverage | 规则覆盖扫描器、coverage JSON/Markdown、真实 COBOL 缺口统计 | `scripts/scan_rule_coverage.py`, `asg/*`, `translator/leaf/*` |
| D | Rules Asset | `config/rules` 规则资产、rule_id、规范与测试映射 | `config/rules/*`, `docs/翻译标准/*` |
| E | Leaf Rules | 叶子动词固化：UNSTRING/INSPECT/SEARCH/复杂 STRING | `translator/leaf/*`, `test_translation.py` |
| F | Flow/Data | 复杂控制流和数据语义：EVALUATE TRUE、88 条件、OF/IN、REDEFINES | `translator/leaf/*`, `asg/*`, `translator/wsaa/*` |
| G | Verification | check suite、fixtures、门禁、操作记录 | `scripts/check.py`, `tests/fixtures/*`, `docs/操作记录/*` |

## Agent 执行顺序

推荐先并行启动第一批：

- `第一批/任务01-产品入口与输出修正.md`
- `第一批/任务02-结构化unsupported基座.md`
- `第一批/任务03-覆盖扫描器雏形.md`
- `第一批/任务04-快速验证入口.md`

第一批合并后，再并行启动第二批叶子规则：

- `第二批/任务05-UNSTRING叶子固化.md`
- `第二批/任务06-INSPECT叶子固化.md`
- `第二批/任务07-SEARCH叶子固化.md`
- `第二批/任务08-复杂STRING补强.md`

后续控制流/数据语义任务见 `任务矩阵.md`。

## 合并原则

1. 公共基础任务先合并：unsupported、coverage、check suite。
2. 叶子规则任务只通过 `translate_leaf_stmt` 接入，不复制 visitor/rules 逻辑。
3. 每个 agent 只改任务包允许的文件。
4. 合并前必须运行任务包内的验收命令。
5. 最终本地闸口始终是：

```bash
python scripts/check.py
```

如果后续 `scripts/check.py --suite all` 落地，则改用：

```bash
python scripts/check.py --suite all
```

