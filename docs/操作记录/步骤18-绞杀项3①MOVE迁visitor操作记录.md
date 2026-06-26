# 步骤18　绞杀项3① MOVE 迁 visitor 操作记录

日期：2026-06-26
对应设计：`../详细设计/步骤18-绞杀项3①MOVE迁visitor设计.md`（🟢已实现）
上位路线图：`../详细设计/架构演进-三相分层(预处理-ASG-visitor)初步设计.md` §5-项3。

---

## 1. 决策脉络（Why）

- 入口：用户「按路线图 §5-项3」。§5-项3 = rules 逐类迁 visitor，动词顺序 MOVE→IF→PERFORM/THRU→CALL→STRING，本步只迁 **MOVE**。
- 探查发现关键点（留痕，详见设计 §3.1）：`rules._t_move` 非纯 token 活，闭包牵出整条表达式底座
  （operand/assign/struct/判型/figurative），且该底座被条件翻译与其它动词共用 → 这是该抽公用的部分。
- 利好：旧 `Ctx` 由 `body_context.build_body_ctx(program)` 装配；ASG 侧 leaf-ctx 直接复用它 →
  两路同一 ctx、同一 `translate_move` → 产物逐字符必然一致，零 diff 风险。
- 用户经 AskUserQuestion 定两决策：① **抽公用模块两路共调**（否决 visitor 重写 / 反向 import rules）；
  ② **建常驻 `scripts/diff_asg_vs_legacy.py` 比对闸**。

## 2. 执行步骤与产物（How）

| 步 | 动作 | 产物 |
|---|---|---|
| 1 | 建公用包 | `translator/leaf/{context,expr,move,__init__}.py`（expr/move 原样迁自 rules，逻辑零改） |
| 2 | rules 委托 | `rules.py` 删 18 符号 + `_t_move`、加 import、`_dispatch_leaf` MOVE 委托 `translate_move` |
| 3 | ASG 提升 | `asg/nodes.py` +`MoveStmt`；`asg/builder._lift` +MOVE 分支 |
| 4 | 相3 visit | `asg/visitor.py` +`LeafJavaVisitor.visit_MoveStmt`；`asg/__init__` 导出 |
| 5 | 比对闸 | `scripts/diff_asg_vs_legacy.py`（legacy=segmenter 枚举 / asg=MoveStmt 遍历，逐字符 diff） |
| 6 | 单测 | `test_translation.py` +4 类 11 测（`TestLeafMoveExtract/TestAsgMoveLift/TestAsgMoveVisitor/TestDiffAsgVsLegacy`） |
| 7 | 回填 | 设计 §10、本记录、`架构索引/项目总览.md` |

## 3. 校验结果（逐项）

- 步骤2 硬闸（旧路径零影响）：`python -m unittest test_translation` → 75 通过/2 skip/0 失败（迁址+委托前）。
- 步骤3 ASG 旧测：`TestAsgBuild/TestAsgRegistryThru/TestAsgGotoVisitor` 11 测全绿。
- 步骤5 比对闸：`PYTHONIOENCODING=utf-8 python scripts/diff_asg_vs_legacy.py <sample.cob>` →
  `[OK] …：7 条 MOVE 两路逐字符一致`，exit 0。
- 步骤6 新测：4 类 11 测全绿。
- 收尾全量：`python -m unittest test_translation` → **86 通过 / 2 skip / 0 失败**（旧 75 + 新 11）。
- 配置快照：`PYTHONIOENCODING=utf-8 python scripts/regress_config_snapshot.py > snap.json` → exit 0、23KB。
  （注：GBK 控制台直接 stdout 会因 `∉`(U+2209) 报 UnicodeEncodeError，是终端编码问题非回归，UTF-8 重定向即过。）

## 4. 关键命令回显（择要）

- `python -m unittest test_translation` → `Ran 86 tests … OK (skipped=2)`。
- `diff_asg_vs_legacy.py sample.cob` → `[OK] …7 条 MOVE 两路逐字符一致 exit=0`。

## 5. 环境备注

- 本机 PowerShell/Git-Bash 异常：`cat` 不可用（仓库根遗留 `bash.exe.stackdump`）；样例 .cob 改用 Write 工具落盘。
- unittest 走 stderr，PowerShell 报 `NativeCommandError` 是正常噪声（退出码以 `Ran … OK` 为准）。

---

## Token 使用分析

- **主要消耗**：
  1. 设计期探查 —— 读 `rules.py`（叶子层 + 表达式底座 ~330 行 + `_t_move`/`_dispatch_leaf`）、`body_context.py`、
     `asg/{builder,visitor,nodes}.py`、两份上位设计文档，定位 `_t_move` 依赖闭包。占比最高（一次性精读，未无脑全文）。
  2. rules 大块删除 —— 为保逐字节精确匹配，删 143 行 helper 块前重读该区间一次（offset 精读，非全文）。
  3. 落盘产物 —— 4 公用文件 + 比对脚本 + 4 测试类 + 3 份文档回填（设计 §10 / 本记录 / 项目总览）。
- **量级**：工具轮次中读取集中在 rules.py 局部精读与 ASG 三文件；无调试反复迭代（单测一次全绿、比对闸一次 exit 0）。
- **节流**：grep 定位符号行号后再 offset 精读；大块删除用 `_ind` 锚点保证唯一匹配，避免多次试错；
  快照编码问题用 UTF-8 重定向一次解决，未反复重试。
