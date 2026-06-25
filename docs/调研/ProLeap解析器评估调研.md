# 调研 · ProLeap COBOL 解析器作为前端替换评估

状态：🟢 spike 已完成（2026-06-24，结论见 §6：**不建议接入 ProLeap，保留自研前端**）
日期：2026-06-09（创建）/ 2026-06-24（spike 实测回填）/ 2026-06-25（§7 可借鉴点沉淀）
触发：用户发现 GitHub `uwol/proleap-cobol-parser`，问能否用于翻译 COBOL；本地已克隆 `/home/zp/langgraph/proleap-cobol-parser`。
关联记忆：项目记忆 `proleap-parser-evaluation`；方向见 `../架构索引/项目总览.md`、本项目「config 规范是核心」定位。

---

## 0. 一句话结论

> **⚠️ spike 实测推翻了原始设想（2026-06-24）。原结论保留见下，实测结论见 §6。**

原始设想：ProLeap 是**工业级 COBOL 解析器（只解析、不生成 Java）**，可用作本项目**前端替换**——
换掉我们反复出 bug 的 Python 列模型 parser，**保留** config 规范驱动的 Java 生成内核。
它的 ASG **原生提供**步骤13 要手搓的控制流要素，故接入后步骤13 的 proc_order/控制流推断基本可省。

**实测结论**：在真实 ZPOLDWNM（CN 寿险方言、含中文、`!!!!!!` 停用行、`GO` 省略 `TO`）上，
ProLeap 即便加 4 道清理 + 113 个桩拷贝簿，仍只解析出 **~10% 的 section / ~4% 的 PERFORM** 即致命中断。
**它无法在本 shop 方言源上充当前端，更无法当神谕。建议保留自研 Python 前端，步骤13 照常手搓。**

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

## 5. 续接点（✅ 已于 2026-06-24 全部完成，结果见 §6）

~~用户「现保存、后续处理」。spike 已批准，但 dump 程序尚未写。下一步：~~
1. ✅ 写 `scripts/spike_proleap/` 解析-导出程序（已完成，见 §6.1）。
2. ✅ 导出 SECTION/paragraph 有序表、PERFORM/THRU 端点、WS 变量数（已完成）。
3. ✅ 对照现有 parser、定路线（已完成，A/B/C 均不成立，见 §6.4-6.5）。

**结论：不立「步骤14·接 ProLeap」。** 步骤13 按已认可设计手搓 proc_order/控制流。

本项目主线代码无改动；ProLeap jar 在其自身仓库、不入本项目。

---

## 6. spike 实测结果与结论（2026-06-24 回填）

### 6.1 产物与脚本（`scripts/spike_proleap/`，均参数化保留）
| 文件 | 职责 |
|---|---|
| `DumpAsg.java` | ProLeap 解析 + ASG 导出 JSON（sections/paragraphs/performs/ws_var_count），收 `CobolParserParams`（拷贝簿目录、只认 `.cob`、`ignoreSyntaxErrors`）|
| `clean_source.py` | 源清理：停用行(`!!!!!!`)清空、去行尾变更标记 `<XXXX>`、`GO 段名`→`GO TO 段名` |
| `gen_stub_copybooks.py` | 为缺失 COPY 生成最小合法 `.cob` 桩（同名 01 组 + FILLER）|
| `run_dump.sh` | 瘦入口：JBR javac/java + mvn 拼依赖 classpath，串起 清理→桩→编译→解析 |

环境补记：本机 `javac` 仅 IntelliJ JBR 有（`/opt/idea-IU-261.../jbr/bin`）；主 jar 非 fat，依赖经
`maven-dependency-plugin:3.7.0:build-classpath`（全坐标，绕过前缀解析）从 `~/.m2` 拼出。

### 6.2 三大阻塞（真实工程源 vs ProLeap 工业文法）
1. **拷贝簿缺口**：源引用 167（清理后 134）个 distinct COPY，仅 21~23 个有 `.cob` 文本；
   **113~144 个彻底缺失**（`*SKM`/`*REC`/`ITEMKEY` 等，主机数据字典编译期生成、不随源发布）。
   ProLeap 缺簿即硬抛、无忽略开关 → 必须造桩。
2. **中文/DBCS 列错位**：源含中文字面量（`'信诚'` 等 254 行）；变更标记按**双宽**排在 73 列+，
   ProLeap 按**字符数**截断到 72 列，中文算 1 字符使标记落进代码区 → 语法错误。必须预先去标记。
3. **`!!!!!!` 停用行 + 不一致停用**：2633~4172 行；ProLeap 把 1-6 列当序号区忽略 → 误激活停用行。
   且源里存在「IF 被停用、其 `GO TO`+`END-IF` 仍激活」的**悬空结构**，清理后 ProLeap 撞无主 `END-IF` **致命中断**。

### 6.3 实测覆盖率（清理 + 113 桩后，仍远不可用）
| 指标 | 真实(grep PROCEDURE) | ProLeap 抓到 | 覆盖率 |
|---|---|---|---|
| SECTION | 125 | 12 | ~10% |
| paragraph | 322 | 42 | ~13% |
| PERFORM | 616 | 22 | **~4%** |

ProLeap 只在源 ~3666–4467 这一段建出 ASG，遇 §6.2-3 悬空 `END-IF` 即不可恢复，丢弃其后约 110 个 section。
另有 `GO 段名`（241 处）、复合条件表达式等方言点。

### 6.4 路线判定
- **路线 A（旁路 parser）**：前提是「最小代价换工业级 parser」，实测被推翻——ProLeap 要先垫一整套
  与我们现有前端等价的方言清理层，且清理后仍致命中断、覆盖 ~10%。**不成立**。
- **路线 B（整体迁 Java）**：同样依赖 ProLeap 能解析，阻塞更前置、代价更大。**不成立**。
- **路线 C（仅当神谕）**：ProLeap 连本 shop 源都解析不全，无法做对照基准。**不成立**（除非未来只在已
  完全规范化的子程序上用，优先级低）。

### 6.5 最终建议
**保留自研 Python 前端（它对本 shop 方言鲁棒），不接入 ProLeap，步骤13 控制流照常手搓。**
spike 脚本保留备查；如未来引入「先规范化再喂工业 parser」的预处理管线，可在此基础上复用。

---

## 7. 可借鉴点（不接入 ProLeap，但吸收其架构思想）

ProLeap 目录印证它是**教科书式编译器前端分层**：`preprocessor/`（670 行独立预处理文法）→ ANTLR 解析
（`Cobol.g4` 3269 行全 COBOL85 文法）→ `asg/visitor`（建语义图）→ `asg/resolver`（符号/引用解析）
→ `asg/metamodel/registry/ASGElementRegistry`（全局可查注册表）。下面区分「可借鉴」与「不可借鉴」。

### 7.1 ProLeap 的真正优势（相对我们手搓前端）
| 维度 | ProLeap | 我们现状 |
|---|---|---|
| 文法完备性 | ANTLR4 形式化全 COBOL85 文法，语句/子句穷尽覆盖 | 按需手搓 segmenter，只覆盖遇到的构造 |
| 预处理独立成相 | `preprocessor/` 单独一相：COPY/REPLACE、定宽/自由格式、续行、注释/序号区剥离，有独立文法 | 散在 cleaner/segmenter，无清晰边界 |
| 语义图 ASG | 节点带类型、引用已解析（PERFORM 目标→真实过程、数据名→DDE） | 扁平 section/paragraph + 规则引擎 |
| 全局注册表 | `ASGElementRegistry` 一把查全程序所有语义元素 | 无；步骤12/13 才临时建 `section_order`/`proc_order` |
| 解析/生成解耦 | parse→ASG→消费三段清晰 | 解析与翻译规则有耦合 |

### 7.2 值得借鉴的（落进 Python 前端，不引入 ProLeap）
1. **ASGElementRegistry 思想 = 步骤13 `proc_order` 正在做的事**：ProLeap 解析 `PERFORM A THRU B` 靠的就是
   注册表里「全程序过程单元有序索引 + 引用解析」。步骤13 的 `proc_order`（四元有序表 + `_perform_range`
   两级查找）本质就是**手搓一个 scoped 版过程单元注册表**——只建真正要用的那部分。反向印证步骤13 设计方向正确：
   「按需自建迷你 ASG」。
2. **预处理独立成相**：把 COPY 展开/格式归一/续行/停用行(`!!!!!!`)清理从 segmenter 抽成清晰「预处理相」
   （spike 的 `clean_source.py`/`gen_stub_copybooks.py` 已是雏形），方言处理集中可测。
3. **「先解析成中性模型、再翻译」的解耦**：长远规则引擎吃稳定中间模型（哪怕轻量自研 ASG）比直接吃 segmenter
   输出更抗变化。**大重构，不在步骤13 范围**，仅记为方向。

### 7.3 不可借鉴的（正是它在本 shop 崩的根因）
- **严格无容错**：缺拷贝簿硬抛、无 ignore 开关、悬空 `END-IF` 致命中断、按字符数截 72 列（中文 DBCS 错位）。
  「工业严格」恰是覆盖率仅 ~10% 的原因（详见 §6.2-6.3）。
- **我们的反向优势 = 方言鲁棒**：`GO 段名`、不一致停用、中文字面量本前端都兜得住，是必保的核心资产。

### 7.4 落到步骤13 的启示（不改变已认可设计）
`proc_order` = mini procedure registry 的定位已被 ProLeap 架构印证，**设计无需改**。可借鉴的小点：ProLeap 的
registry 是**程序级算一次、全程序可查**——与步骤13 回填决策「`proc_order` 程序级建一次、`pending_range_methods`
程序级累积、`reset_section` 不清」方向吻合。详见 `../详细设计/步骤13-paragraph级THRU区间解析设计.md` §2.1/§2.3。
