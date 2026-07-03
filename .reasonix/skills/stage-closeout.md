---
name: stage-closeout
description: 阶段收口检查 — 收尾一个开发批次：验证测试、检查文档一致性、产出收口报告
---
# stage-closeout — 阶段收口检查

收尾一个开发批次（如 T10-T17、T18 等），确保进入可提交、可复现的状态。

## 步骤 1：明确收口范围
- 读对应批次的 plan 文件（`docs/superpowers/plans/`）
- 读该批次的 spec 文件（`docs/superpowers/specs/`）
- 列出该批次包含的所有任务

## 步骤 2：验证测试全绿
- 运行 `python scripts/check.py quick`
- 运行 `python scripts/check.py leaf`
- 运行 `python scripts/check.py asg`
- 运行 `python scripts/check.py all`
- 运行 `python -m pytest tests/ -v`
- 记录每个命令的 exit code 和关键输出

## 步骤 3：文档一致性检查
- 检查 `docs/操作记录/` 下该批次每项任务是否有操作记录
- 检查 `docs/详细设计/` 下每项任务的设计文档与实现是否一致
- 检查 `docs/翻译标准/` 是否反映了该批次的翻译规则变化
- 检查 `knowledge/*.md` 是否更新了新的翻译模式
- 搜索 TODO/FIXME/HACK 等标记，确认是否有遗留未决项

## 步骤 4：生成差异报告
- 用 `git diff --stat` 查看改动的文件范围
- 用 `git diff`（或通过脚本）查看关键改动
- 记录该批次新增/修改/删除的文件清单

## 步骤 5：产出收口报告
产出 markdown 文档，包含：
- 批次范围与目标
- 测试结果（每项命令的 pass/fail）
- 文档一致性检查结果
- 未决事项列表
- 是否达到 mainline gate 准入标准

用 `submit_plan` 提交收口报告给用户审阅。
