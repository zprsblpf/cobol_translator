# 并行开发提速设计

## 目标

把当前 COBOL 到 Java 翻译器的后续开发拆成可并行推进的固定泳道，减少等待、减少文件冲突，并让每条线都有独立验收入口。

本设计只解决开发组织和任务边界，不改变运行时翻译流程。

## 背景

项目当前已经形成清晰分层：

- `translator/leaf/`：叶子语句翻译公共底座，供 legacy rules 和 ASG visitor 共享。
- `translator/skel/`：骨架装配公共底座，承接 PERFORM、GOTO dispatch、IO 结构吸收等段级逻辑。
- `asg/`：轻量 ASG、结构改写和 visitor 渲染路径。
- `scripts/diff_asg_vs_legacy.py`：legacy 与 ASG 输出一致性对比闸口。
- `test_translation.py`：集中回归测试，已按功能族组织测试类。

最近的开发节奏是先设计、再计划、再实现，并逐步把旧 token 路径下沉到 `leaf/` 和 `skel/` 公共底座，再由 ASG visitor 共调。并行开发应保持这个方向。

## 推荐方案

采用固定泳道并行开发，而不是按单个大步骤串行推进。

每条泳道拥有明确的文件边界、测试边界和合并顺序。任务之间通过公共入口通信，不直接复制其他泳道逻辑。

### 泳道 A：Leaf 动词固化

职责：

- 新增或扩展 COBOL 叶子动词的确定性翻译。
- 继续使用 `translator.leaf.translate_leaf_stmt` 作为统一入口。
- 保持 legacy rules 和 ASG visitor 共用同一实现。

允许修改：

- `translator/leaf/*.py`
- `translator/leaf/__init__.py`
- `test_translation.py` 中对应的 `TestLeaf*`、`TestUnifiedLeafEntry`、`TestAsg*Visitor` 小范围测试
- 对应设计文档和操作记录

禁止修改：

- 不直接改 `translator/skel/*`
- 不直接改段级结构改写
- 不在 `translator/rules.py` 新增独立动词分支，除非只是兼容导入或委托

验收：

- 单动词直接测试类通过
- `TestUnifiedLeafEntry` 通过
- 相关 ASG visitor 测试通过

### 泳道 B：ASG/Visitor 迁移

职责：

- 补齐 ASG 节点、builder lift 和 visitor 渲染。
- 把已经公共化的 leaf/skel 能力接入 ASG。
- 推动主线从旧 rules 渲染转向 `SectionJavaVisitor`。

允许修改：

- `asg/nodes.py`
- `asg/builder.py`
- `asg/visitor.py`
- `asg/section_visitor.py`
- `asg/structure_rewrite.py`
- `scripts/diff_asg_vs_legacy.py` 中对应对比采集器
- `test_translation.py` 中对应 ASG 和 diff 测试

禁止修改：

- 不在 visitor 内复制 leaf/skel 的翻译规则
- 不绕过 `translator/leaf` 或 `translator/skel` 公共入口
- 不改变 parser 输出结构，除非单独开 parser 泳道设计

验收：

- 对应 `TestAsg*` 测试通过
- 对应 `TestDiffAsgVsLegacy*` 测试通过
- 主线相关 `TestMainline*` 不回退

### 泳道 C：Skel 结构吸收

职责：

- 处理段级结构：PERFORM 调用、GOTO dispatch、BEGN/READR/WRITE IO 结构吸收、pending range 方法。
- 维护 `translator/skel/` 作为 legacy rules 和 ASG visitor 的共享底座。

允许修改：

- `translator/skel/*.py`
- `asg/structure_rewrite.py`
- `asg/section_visitor.py`
- `translator/rules.py` 中委托到 skel 的薄适配层
- `test_translation.py` 中 skel、section visitor、diff 相关测试

禁止修改：

- 不把叶子动词翻译写进 skel
- 不在 `translator/rules.py` 继续扩大旧路径核心逻辑
- 不改变 `LeafCtx` 语义；段级上下文走 `SkelCtx`

验收：

- 对应 skel 单元测试通过
- 对应 ASG section visitor 测试通过
- 对应 legacy vs ASG diff 测试通过

### 泳道 D：验证与样例

职责：

- 提供更快、更细的验证入口，让其它泳道不必每次跑全量。
- 维护 diff 工具、fixture、check 脚本和验收文档。

允许修改：

- `scripts/check.py`
- `scripts/diff_asg_vs_legacy.py`
- `tests/fixtures/*`
- `test_smoke.py`
- `test_translation.py` 中验证工具自身测试
- `docs/操作记录/*`

禁止修改：

- 不改变翻译语义
- 不把业务规则写入测试工具

验收：

- 工具自身测试通过
- 至少提供一个单命令快速验证入口
- `python scripts/check.py` 保持作为最终本地闸口

## 任务包格式

每个并行任务必须先写清边界，再实施。

任务包必须包含：

- 目标：一句话说明本任务完成后新增什么能力。
- 允许修改文件：列出精确路径。
- 禁止修改文件：列出高风险路径。
- 依赖：说明依赖哪个公共入口或前置任务。
- 测试：列出单测类或脚本命令。
- 合并备注：说明是否必须先于其它任务合并。

## 合并顺序

推荐合并顺序：

1. 公共底座任务先合并：`translator/leaf` 或 `translator/skel` 的纯能力扩展。
2. ASG 接入任务后合并：visitor 只调用已存在公共入口。
3. diff 和主线切换最后合并：确保 legacy 与 ASG 输出一致后再改主线默认路径。
4. 文档和操作记录随任务一起合并，不单独滞后。

如果两个任务同时修改 `test_translation.py`，先按测试类位置分区提交；合并时只处理测试类插入顺序，不改测试语义。

## 第一批并行任务

### 任务 1：UNSTRING 叶子固化

泳道：A

目标：为保守子集的 `UNSTRING ... DELIMITED BY ... INTO ...` 增加确定性翻译，并接入统一 leaf 入口。

允许修改：

- `translator/leaf/unstring.py`
- `translator/leaf/__init__.py`
- `test_translation.py`
- 对应设计文档和操作记录

验收：

- 新增 `TestLeafUnstringExtract`
- 扩展 `TestUnifiedLeafEntry`
- 扩展 ASG leaf visitor 共享输出测试

### 任务 2：INSPECT 叶子固化

泳道：A

目标：为保守子集的 `INSPECT ... REPLACING` 或 `INSPECT ... TALLYING` 增加确定性翻译。

允许修改：

- `translator/leaf/inspect.py`
- `translator/leaf/__init__.py`
- `test_translation.py`
- 对应设计文档和操作记录

验收：

- 新增 `TestLeafInspectExtract`
- 扩展 `TestUnifiedLeafEntry`
- 不支持形态继续返回 `([], False)`

### 任务 3：ASG leaf fallback 对比补强

泳道：B

目标：补齐未固化 leaf 在 ASG visitor 下的占位输出对比，避免新增动词时误改 fallback 行为。

允许修改：

- `asg/visitor.py`
- `scripts/diff_asg_vs_legacy.py`
- `test_translation.py`

验收：

- 新增或扩展 `TestDiffAsgVsLegacy*`
- 已固化动词输出不变
- 未固化动词仍输出 `// TODO-LEAF`

### 任务 4：快速验证入口

泳道：D

目标：为单个动词族提供快速验证命令，降低并行开发时的等待成本。

允许修改：

- `scripts/check.py`
- `scripts/diff_asg_vs_legacy.py`
- `test_translation.py`
- `docs/操作记录/*`

验收：

- 能用一个命令跑指定动词族测试
- `python scripts/check.py` 仍保持全量本地闸口

## 风险控制

- `translator/rules.py` 当前仍是高风险文件。新增能力优先下沉到 `leaf/` 或 `skel/`，`rules.py` 只做委托。
- `test_translation.py` 是冲突热点。任务计划必须指定插入测试类的位置。
- ASG visitor 不拥有业务翻译规则。它只负责节点调度、缩进、段级上下文和公共入口调用。
- 任何主线切换必须先有 diff 闸口证明输出一致。

## 成功标准

并行开发机制落地后，应满足：

- 至少 3 个任务可以同时开发，且默认不修改同一核心文件。
- 每个任务有独立单测入口。
- 合并后 `python scripts/check.py` 通过。
- 新增翻译能力优先进入公共底座，legacy 与 ASG 不分叉。
