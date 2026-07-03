---
name: step-translate
description: 单步翻译开发 — 实现一个新COBOL→Java翻译步骤（动词固化/visitor迁移等），含设计→实现→验证→回填
---
# step-translate — 单步翻译开发

实现一个 COBOL→Java 翻译新步骤（例如新动词固化、visitor 迁移、结构吸收等）。

## 步骤 1：阅读设计
- 读 `docs/superpowers/specs/` 下对应步骤的详细设计
- 读 `docs/详细设计/` 下对应步骤的设计文档
- 读 `docs/翻译标准/` 下相关标准定义
- 读 `knowledge/*.md` 中相关的翻译模式知识

## 步骤 2：理解现有代码
- 搜索 `translator/leaf/` 下已有的类似动词实现（如要加 SEARCH 就看 `search.py`）
- 搜索 `asg/` 下相关 ASG 节点定义
- 搜索 `translator/rules.py` 中是否有旧的实现路径需要了解
- 运行 `python scripts/check.py` 了解当前测试基线

## 步骤 3：产出详细设计（如果还没有）
如果设计文档还不够详细，用 `submit_plan` 提交详细设计给用户审批。

## 步骤 4：实现
- 按设计实现代码
- 每完成一个子功能就跑 `python -m pytest tests/ -x -v` 验证
- 用 `todo_write` 跟踪多文件实现进度

## 步骤 5：验证
- 运行 `python scripts/check.py quick` 快速验证
- 运行 `python scripts/check.py leaf` 验证叶子翻译
- 运行 `python scripts/check.py asg` 验证 ASG 路径
- 运行 `python scripts/check.py all` 全量验证
- 确认 output/ 下的生成结果符合预期

## 步骤 6：回填文档
- 更新 `docs/操作记录/` 下对应的操作记录
- 如有接口或架构变化，更新 `ARCHITECTURE.md`
- 如有新的翻译模式，更新 `knowledge/*.md`
