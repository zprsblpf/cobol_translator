# 调研 · ProLeap COBOL 解析器作为前端替换评估

状态：🔶调研中（spike 已批准、jar 已构建，dump 程序待写）
日期：2026-06-09
触发：用户发现 GitHub `uwol/proleap-cobol-parser`，问能否用于翻译 COBOL；本地已克隆 `/home/zp/langgraph/proleap-cobol-parser`。
关联记忆：项目记忆 `proleap-parser-evaluation`；方向见 `../架构索引/项目总览.md`、本项目「config 规范是核心」定位。

---

## 0. 一句话结论

ProLeap 是**工业级 COBOL 解析器（只解析、不生成 Java）**，可用作本项目**前端替换**——
换掉我们反复出 bug 的 Python 列模型 parser，**保留** config 规范驱动的 Java 生成内核。
它的 ASG **原生提供**步骤13 要手搓的控制流要素，故接入后步骤13 的 proc_order/控制流推断基本可省。

---

## 1. ProLeap 是什么

- GitHub `uwol/proleap-cobol-parser`，v4.0.0，**Java 17 + ANTLR 4.7.2 + Maven**，1119 个 Java 文件。
- 产出 **AST + ASG（Abstract Semantic Graph）**：含数据流、控制流、变量访问解析；EXEC SQL/CICS 作文本抽取。
- **过 NIST 测试套件**，在银行/保险真实 COBOL 上实战；支持多方言、copybook 预处理、定宽/自由格式。
- **不译码**：源码全是 parser/ASG/preprocessor，无任何 codegen/transform/emit。姊妹库 `proleap-cobol`
  （analyzer/interpreter/**transformer**）含更多变换能力，值得后续顺带评估。

---

## 2. 为什么对症本项目

我们近几步的麻烦**全在解析层**：步骤06 列对齐、步骤08 paragraph 切分、步骤13（proc_order/PERFORM THRU/GO TO 回跳）。
ProLeap ASG **原生**给出这些（已读源码确认接口）：

| 我们的需求 | ProLeap ASG 接口 |
|---|---|
| 全程序 SECTION/paragraph **有序**表（步骤13 proc_order） | `ProcedureDivision.getSections()` / `getParagraphs()`（有序 List）、`Section.getParagraphs()` |
| `PERFORM A THRU B` 端点（步骤13 命门） | `PerformProcedureStatement.getCalls()`（端点 Call）+ `getPerformType()`（UNTIL/VARYING/TIMES） |
| 变量定义/类型/层级 | `ProgramUnit.getDataDivision()` 元模型 |
| 控制流/变量访问 | ASG 语义层（数据/控制流） |

**含义**：接 ProLeap 后，步骤13 手搓的 proc_order 与控制流推断**基本不必做**。

---

## 3. 接入三路线（待用户拍板）

| 路线 | 做法 | 代价 | 收益 |
|---|---|---|---|
| **A·旁路进程**（倾向） | ProLeap 编个 Java CLI，把 ASG 导成 JSON，Python 端消费 | 加 Java/Maven 构建依赖；要写 ASG→JSON 序列化层；JVM 启动开销 | 保留 config 驱动生成内核，解析换工业级，解耦 |
| **B·整体迁 Java** | 翻译器搬到 Java，直接吃 ASG API | 最大重写，config/rules 全迁 | 单运行时、ASG 访问最丰富 |
| **C·仅当神谕** | 只拿它校验/对照现有 Python 解析器 | 最小投入 | 不改架构，只兜底验证 |

倾向 **A**：契合「config 规范是核心、解析只是手段」定位，最小代价换掉脆弱 parser。

---

## 4. 已确认环境事实（spike 就绪）

- **Java 21** 在（兼容 ProLeap 的 17）；**无 `mvn`**，用 IntelliJ 自带：
  `/opt/idea-IU-261.23567.138/plugins/maven/lib/maven3/bin/mvn`；`~/.m2` 缓存可用。
- **已构建成功**：`/home/zp/langgraph/proleap-cobol-parser/target/proleap-cobol-parser-4.0.0.jar`（exit 0）。
- **源码**：`/home/zp/Documents/cob/ZPOLDWNM.cob`（1.28 MB / 15862 行，定宽 → `CobolSourceFormatEnum.FIXED`）。
- **API 链路**：`new CobolParserRunnerImpl().analyzeFile(file, FIXED)` → `Program`
  → `getCompilationUnit("ZPOLDWNM").getProgramUnit()` → `getProcedureDivision()/getDataDivision()`；
  取所有 PERFORM 可用 `program.getASGElementRegistry()`。

---

## 5. 续接点（下次直接做）

用户「现保存、后续处理」。spike **已批准**，但 **dump 程序尚未写**。下一步：
1. 写 `scripts/spike_proleap/` 下的解析-导出程序（rule11 保留脚本），用 §4 的 jar + API 解析 ZPOLDWNM。
2. 导出：SECTION/paragraph 有序表、PERFORM/THRU 端点、WS 变量数。
3. 用实测产物对照我们现有 parser，定接入路线 A/B/C，再决定是否立「步骤14·接 ProLeap」。

本项目主线代码无改动；ProLeap jar 在其自身仓库、不入本项目。
