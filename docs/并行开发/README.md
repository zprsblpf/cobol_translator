# 并行开发

本目录固化 COBOL 到 Java 翻译器的并行开发任务包。

源设计：

- `docs/superpowers/specs/2026-06-30-parallel-development-design.md`

固定泳道：

- A：Leaf 动词固化
- B：ASG/Visitor 迁移
- C：Skel 结构吸收
- D：验证与样例

执行原则：

- 每个任务先写清允许修改文件和禁止修改文件。
- 公共底座任务先合并，ASG 接入任务后合并，主线切换最后合并。
- 每个任务必须有独立验收命令。
- 最终合并前必须通过 `python scripts/check.py --suite all`。

第一批任务：

- `第一批/任务01-UNSTRING叶子固化.md`
- `第一批/任务02-INSPECT叶子固化.md`
- `第一批/任务03-ASG-leaf-fallback对比补强.md`
- `第一批/任务04-快速验证入口.md`
