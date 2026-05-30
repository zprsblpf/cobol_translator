# COBOL → Java 翻译器 · 设计与代码说明

本项目把 AS/400 LIFE/400 风格的 COBOL 程序自动翻译为 Spring 风格的 Java 代码。
本文说明**设计思想**、**整体架构**、**目录结构**与**各模块/类/关键函数的职责**，
便于后续扩展、梳理与对照。范围仅限本目录 `cobol_translator/`。

---

## 一、设计思想

### 1. 骨架优先，细节后填
最重要、必须确定性正确的，是先把 COBOL 程序"整理逻辑的骨架"搭起来，再往里填具体运算：

- **第 1 层 · 逻辑骨架（确定性，不依赖 LLM）**：类/模块结构、方法之间的调用、变量值的改变与传递、
  控制流（IF/循环/EVALUATE/GO TO）。这一层用确定性规则生成，单独即可审查、可编译。
- **第 2 层 · 细节运算填充（规则优先 + LLM 兜底）**：MOVE/算术/IO 等叶子语句填进骨架的槽位。
  规整语句由固化规则生成；规则识别不了的少数复杂叶子才交本地 LLM。叶子的局部错误不会破坏骨架结构。

### 2. 混合策略：固化规则 + LLM 兜底
重复规整的 COBOL 语句（MOVE/IF/PERFORM/EVALUATE/算术/GO TO）"固化"为固定 Java 写法，
确定性、可复现、零波动；只有罕见或切分不准的片段才调用 LLM。固化写法的事实源是
[`knowledge/*.md`](knowledge/)，既供人工对照，也作 RAG 提示喂给 LLM 兜底。

### 3. 大类拆分：每个 Java 类 < 2000 行
一个 COBOL 程序常有上百个 SECTION、上千个字段，直接翻成单类会到数千行。因此按 COBOL 段号
千位前缀把 SECTION 分到多个模块类，类名与 COBOL 结构对应（如 `Xxx1000Section`），便于 Java↔COBOL 对照。

### 4. 正确性靠三条不变量（而非追踪取值）
COBOL 变量贯穿整个流程、中途被多段修改、方法被反复嵌套调用。分块翻译**不破坏**这种长程逻辑，
因为守住了三条不变量：

1. **变量身份唯一**：所有段读写同一个 `XxxState` 实例（单例、按引用传递、不复制），
   A 段的修改对 B 段可见，与 COBOL 全局 WORKING-STORAGE 一致。
2. **段内语句顺序保真**：固化层按源序逐句生成。
3. **跨段调用顺序/嵌套保真**：PERFORM/嵌套/多处调用映射为同构的 Java 方法调用，门面 `perform()` 分发任意深度。

因此规则/LLM 只需保证**单条语句的局部正确**，无需追踪变量取值——运行时按相同顺序执行相同赋值，
变量演变自动复现。深度验证采用**静态分析 + 审查产物**（调用链图、变量数据流、风险清单）。

### 5. 两个关键确定性机制（近期补强）

- **段内 GO TO → 状态机循环**：COBOL 段内用 `GO TO <paragraph>` 回跳形成循环（如 BEGN+NEXTR 顺序读）。
  骨架层检测"回跳边"，把段还原为 `String __pc; FLOW: while(true){ switch(__pc){ case "<label>": … } }`，
  保住循环语义而非误塌缩为 `return`。详见 `rules.build_section`。
- **拷贝簿结构体命名范式（config 驱动）**：`COPY <名><后缀>`（SKM/REC/KEY）→ 结构体前缀 `<名>`，
  字段 `<名>-XXX` 渲染为 `对象.getXxx()`/`setXxx(v)`、整体 `new 类()`。规则由
  [`config/naming_conventions.yaml`](config/naming_conventions.yaml) 声明，Python 只读取、不写死。
  **不变量**：未加引号的 COBOL 连字符标识符**永不**翻成字符串字面量——要么是 `field_type_map` 字段，
  要么是拷贝簿结构体字段，要么是命名常量（如 `O-K`）。详见 `nodes.build_struct_registry` 与 `rules._operand`。

---

## 二、整体架构

### LangGraph 流水线（4 个节点）

```
parse_cobol            解析 .cob → 结构化数据 + 字段/类型映射 + COPY 引用
      ↓
build_context          跨段分析(调用链/数据流) + 分模块 + 生成 State/模块/门面骨架
                       + 一次性算好结构体命名注册表(struct_registry)
      ↓
[Send] translate_section × N   并行：每段先搭骨架(确定性)，再填叶子(规则优先 + LLM 兜底)
      ↓ (汇聚)
assemble               组装并写出多文件 + 审查清单 + 调用链
```

状态以 `TranslationState`（`graph/state.py`）在节点间流动；`translated_sections` 用 reducer 合并并行结果。

### 输出形态（以程序 ZPOLDWNM、类基名 Zpoldwnm 为例）

| 文件 | 角色 |
|------|------|
| `ZpoldwnmState.java` | `@Component` 共享状态 POJO，持有全部 WORKING-STORAGE/LINKAGE 字段（按 01 组分块）|
| `ZpoldwnmService.java` | 门面 `@Service`：持有 State 单例 + 注入各模块，`execute()` 入口、`perform(section)` 跨模块分发 |
| `Zpoldwnm1000Section.java` … | 模块 `@Service`：段号桶（1000/2000/…/Misc）的 SECTION 方法；持 `st` 与 `facade` 引用 |
| `review_checklist.md` | 审查清单：高风险点、模块拆分汇总、文件行数、统计 |
| `call_graph.md` | 嵌套调用树 + 入口序列 |

---

## 三、目录结构

```
cobol_translator/
├── main.py                  命令行入口（全量/单段/仅骨架/仅解析）
├── run.sh                   用项目专用 Python 环境启动 main.py
├── ARCHITECTURE.md          本文档
│
├── parser/                  ① 解析层（COBOL → 结构化数据，纯确定性）
│   ├── cobol_parser.py        固定列格式解析 → CobolProgram
│   └── variable_resolver.py   COBOL 变量 → Java 字段 / 类型映射
│
├── analyzer/                ② 跨段静态分析层（确定性，无 LLM）
│   ├── callgraph.py           PERFORM 调用链 / 入口序列 / 调用环
│   └── dataflow.py            变量读写生命周期 / 风险标注
│
├── translator/              ③ 固化语法层（单段 COBOL → Java，确定性）
│   ├── segmenter.py           代码行 → paragraph / 语句块树
│   └── rules.py               骨架(控制流+GO TO状态机) + 叶子(MOVE/算术/结构体)
│
├── graph/                   ④ 流水线编排层（LangGraph）
│   ├── state.py               TranslationState 状态结构
│   ├── nodes.py               4 个节点 + 骨架构建/后处理/组装/RAG/LLM
│   └── graph.py               节点装配 + Send 并行派发
│
├── validator/               ⑤ 产物校验
│   └── java_validator.py      javac 编译校验 + 风险扫描
│
├── config/                  规则配置（py 读取，不写死）
│   ├── type_mappings.yaml     PIC/COMP → Java 类型
│   ├── io_mappings.yaml       CALL 'xxxIO' → Repository/Service
│   ├── copy_mappings.yaml     COPY 名 → Java 类名（显式覆盖）
│   └── naming_conventions.yaml 拷贝簿结构体命名范式（后缀/访问器）
│
├── knowledge/               翻译规范知识库（事实源 + RAG 语料）
│   ├── cobol_java_patterns.md  通用语句模式
│   ├── data_types.md           数据类型
│   ├── io_call_patterns.md     IO 调用（READR/BEGN+NEXTR/UPDAT）
│   └── insurance_domain.md     保险领域术语
│
└── test_translation.py      回归测试
```

---

## 四、各模块与类的职责

### 入口 · `main.py`
命令行入口。`python main.py X.cob` 全量翻译；`--sections N` 仅前 N 段（测试）；
`--skeleton-only` 仅生成第 1 层骨架（叶子留占位，不调 LLM）；`--parse-only` 只解析；
`--section NAME` 单段试译；`--output DIR` 输出目录。单段/截断路径直接调用节点函数，全量走 LangGraph 图。

### ① 解析层 `parser/`

**`cobol_parser.py`** — 解析 AS/400 固定列格式 COBOL，产出 `CobolProgram`，纯解析无 LLM。

| 符号 | 职责 |
|------|------|
| `Variable` (dataclass) | 一条数据项：层级、名称、PIC、COMP、VALUE |
| `CobolSection` (dataclass) | 一个 SECTION：名称、行区间、源码行、PERFORM/CALL/GO TO 目标 |
| `CobolProgram` (dataclass) | 整程序：PROGRAM-ID、WORKING-STORAGE/LINKAGE 变量、`linkage_using`、sections、`copy_refs` |
| `parse()` | 顶层入口：定位各 DIVISION，解析变量/段/COPY |
| `_parse_variables` / `_parse_variable_line` | WORKING-STORAGE/LINKAGE 逐行解析 |
| `_parse_sections` | 按 SECTION 切分并抽取 PERFORM/CALL/GO TO |
| `_strip_cobol_line` / `_clean_lines` | 去序号列/注释/续行规整 |

**`variable_resolver.py`** — COBOL 变量按 PIC/COMP 规则转 Java 字段。

| 符号 | 职责 |
|------|------|
| `JavaField` (dataclass) | 解析后的 Java 字段：名称、类型、是否数组、大小 |
| `resolve()` | 变量列表 → `JavaField` 列表 |
| `_get_java_type` | PIC/COMP → Java 类型（查 `type_mappings.yaml`） |
| `_cobol_to_java_name` | `WSAA-POLICY-NO` → `wsaaPolicyNo` |
| `generate_field_declarations` / `generate_grouped_field_declarations` | 字段声明块 / 按 01 组分块（State 类用） |
| `build_field_type_map` | `{java名: {type,is_array,array_size}}`，供固化规则判型 |
| `generate_variable_context` | 变量映射摘要（注入 LLM 提示） |

### ② 跨段分析层 `analyzer/`（确定性，无 LLM）

**`callgraph.py`** — `build_call_graph`：从入口段 DFS 跟踪 `PERFORM` 目标，产出邻接表/调用者表、
入口序列（供 `execute()` 接线）、调用环检测、`call_graph.md` 嵌套调用树。

**`dataflow.py`** — `analyze_dataflow`：逐段抽取变量的写（MOVE…TO / COMPUTE / ADD…GIVING）与读，
得 `var_lifecycle`（每变量在哪些段被写/读）并标注"读先写后/多段共享写/仅读仅写"风险；
`writers_context`：为某段生成"本段所读变量在别处被写"的提示，注入 LLM。

### ③ 固化语法层 `translator/`

**`segmenter.py`** — 把 SECTION 代码切成结构化树。

| 符号 | 职责 |
|------|------|
| `Stmt` (dataclass) | 语句节点：kind(simple/if/evaluate/perform)、tokens、children、whens、raw |
| `split_paragraphs()` | 按 paragraph 标签（Area A 行首无缩进 + 句点）切成 `[(label, body_lines)]`，供 GO TO 状态机 |
| `segment()` | 把代码行递归解析为顶层语句列表 |
| `_Parser` | 递归下降：IF/ELSE/END-IF、EVALUATE/WHEN、PERFORM…END-PERFORM、叶子 |

**`rules.py`** — 固化规则引擎。字段一律输出"裸名"，由 `nodes` 后处理统一加 `st.` 前缀与跨模块路由。

| 符号 | 职责 |
|------|------|
| `Ctx` (dataclass) | 翻译上下文：`field_type_map`、已知段集、leaves 收集器、状态机标签/paragraph 集、**结构体命名注册表**（前缀/对象/类/getter/setter/默认后缀） |
| **骨架层** | |
| `build_section()` | 段级入口：检测 GO TO 回跳边 → 平铺骨架 或 `while+switch` 状态机；无回跳则退回 `build_skeleton` |
| `build_skeleton()` / `_skeleton_one` | 递归生成控制流骨架，叶子位置插 `/*__LEAF_n__*/` 占位 |
| `_sk_if` / `_sk_evaluate` / `_sk_perform` / `_sk_control` | IF/EVALUATE/PERFORM/GO·EXIT·CONTINUE 的骨架翻译（`_sk_control` 内含状态机回跳/退出） |
| `_collect_gotos` / `_ends_with_transfer` | 回跳边检测辅助 |
| **叶子层** | |
| `translate_leaf()` | 叶子分发：命中规则返回 Java，否则 `matched=False` 交 LLM |
| `_t_move`/`_t_set`/`_t_add`/`_t_subtract`/`_t_multiply`/`_t_divide`/`_t_compute` | 各动词的确定性翻译（BigDecimal 链式 vs 整型；figurative 常量） |
| `_try_condition` / `_try_comparison` | IF/UNTIL/WHEN 条件 → Java 布尔表达式（数值/字符串/取反） |
| **操作数与命名** | |
| `_operand()` | 单操作数 → Java：字面量 / 字段裸名 / 下标 / **引用修改 substring** / **结构体 getter** |
| `_assign()` | 赋值语句：结构体字段→setter、结构体整体→`new`、普通字段→`=` |
| `_struct_prefix`/`_struct_obj`/`_struct_cls` | 结构体前缀识别与对象/类名解析（查 `Ctx` 注册表） |
| `_refmod_lo`/`_refmod_hi` | COBOL 1-based 子串 → Java 0-based `substring`（常量折算） |
| `_java`/`_pascal`/`_field_base`/`_is_field`/`_is_numeric_field`/`_is_bigdecimal` | 命名与判型工具 |

### ④ 流水线层 `graph/`

**`state.py`** — `TranslationState`（TypedDict）：贯穿流水线的状态（解析产物、模块划分、骨架、
调用链/数据流、`copy_refs`/`struct_registry`、翻译结果）。`translated_sections`/`review_items` 带 reducer 合并并行写入。

**`nodes.py`** — 4 个节点 + 全部骨架构建/后处理/组装/RAG/LLM 工具。

| 符号 | 职责 |
|------|------|
| **节点** | |
| `parse_cobol_node` | 解析并产出字段/类型映射、`copy_refs` |
| `build_context_and_skeleton_node` | 跑调用链/数据流、分模块、生成 State/模块/门面骨架、算 `struct_registry` |
| `translate_section_node` | 两遍翻译：骨架(确定性) → 填叶子(规则优先 + 一次 LLM 兜底) |
| `assemble_node` / `_fill_stubs` | 多文件组装、写出、审查清单与调用链 |
| **骨架构建** | |
| `_assign_sections_to_modules` | 按段号千位前缀分模块（控制类大小 < 2000 行） |
| `_build_state_class` / `_build_module_skeleton` / `_build_facade_skeleton` | 生成 State / 模块 / 门面 Java 骨架 |
| `_calls_to_repos` / `_build_io_call_template` | IO 调用 → Repository 注入 / 生成 CALL 翻译模板 |
| `_class_base`/`_module_class_name`/`_section_to_method`/`_facade_field` | 命名工具 |
| **命名范式** | |
| `build_struct_registry` | 从 `copy_refs` 按 `naming_conventions.yaml` 派生结构体注册表（前缀/对象/类） |
| `_load_yaml` | config 读取 |
| **后处理** | |
| `_postprocess_java_body` | 三遍：下标 `(i)`→`[i-1]`、`this.m()` 跨模块改 `facade.perform`、`st.` 前缀 |
| `_prefix_fields_outside_strings` | 仅对字符串字面量外的字段名加 `st.` |
| **LLM / RAG** | |
| `_get_llm`/`_call_llm_no_think`/`_get_current_model` | 本地 vLLM（OpenAI 兼容）调用，剥离 `<think>` |
| `_get_vs`/`_rag_retrieve` | 知识库向量检索（Chroma + 多语 MiniLM 嵌入），注入 LLM 提示 |
| `_translate_leaves_llm` | 把规则未命中的叶子批量交 LLM（带 RAG + IO 模板上下文） |

**`graph.py`** — 用 LangGraph 装配节点；`_route_after_parse` 错误分流；`_send_sections` 用 `Send` API
并行派发各段翻译（受本地 vLLM 并发限制）。

### ⑤ 校验 `validator/`
**`java_validator.py`** — `validate_with_javac` 调 `javac` 编译校验；`scan_risks` 扫描高风险残留。

### 配置 `config/` 与知识库 `knowledge/`

| 文件 | 作用 | 被谁读取 |
|------|------|----------|
| `config/type_mappings.yaml` | PIC/COMP → Java 类型 | `variable_resolver._load_type_rules` |
| `config/io_mappings.yaml` | `CALL 'xxxIO'` → Repository/Service | `nodes`（IO 上下文/模板） |
| `config/copy_mappings.yaml` | COPY 名 → Java 类名（显式覆盖） | `nodes.build_struct_registry` |
| `config/naming_conventions.yaml` | 拷贝簿后缀范式 + 访问器前缀 + 默认类后缀 | `nodes.build_struct_registry` |
| `knowledge/*.md` | 翻译规范（模式/类型/IO/领域术语） | 人工对照 + `nodes._rag_retrieve` |

### 测试 `test_translation.py`
回归测试：后处理/变量解析等纯逻辑始终跑；LLM 相关在 vLLM 不可用时自动 skip。

---

## 五、扩展指引（常见任务从哪下手）

| 想做的事 | 改哪里 |
|----------|--------|
| 新增/调整 PIC→Java 类型 | `config/type_mappings.yaml` |
| 新增 IO 子程序映射 | `config/io_mappings.yaml`（+ 必要时 `_build_io_call_template`） |
| 新增拷贝簿结构体命名/类名 | `config/copy_mappings.yaml`（显式）或 `naming_conventions.yaml`（范式后缀） |
| 固化一类新语句（少调 LLM） | `translator/rules.py` 加 `_t_xxx` 并在 `translate_leaf` 分发；样例补 `knowledge/*.md` |
| 调整控制流/状态机生成 | `translator/rules.py` 的 `build_section` / `_sk_*` |
| 改模块拆分粒度/命名 | `graph/nodes.py` 的 `_assign_sections_to_modules` / `_module_class_name` |
| 改 State/门面/模块骨架样式 | `graph/nodes.py` 的 `_build_*_skeleton` |
| 改后处理（前缀/路由/下标） | `graph/nodes.py` 的 `_postprocess_java_body` |

**改动原则**：能进 config 的规则就不要写死在 py 里（命名范式、类型、IO、COPY 映射均已 config 化）；
新增确定性能力时优先固化到规则层，把 LLM 兜底面积持续缩小。

---

## 六、端到端时序（一次翻译读写了哪些 state 字段）

下图标出每个节点**读取**与**写入**的关键 `TranslationState` 字段，便于排查"某字段从哪来、到哪用"。

```
 .cob 文件
   │
   ▼ ┌─────────────────────────────────────────────────────────────┐
     │ parse_cobol_node                                            ① │
     │  读: cobol_file                                                │
     │  写: program_id, sections_meta(含每段源码行), variable_context, │
     │      field_type_map, java_field_names, java_field_declarations,│
     │      linkage_using, copy_refs                                  │
     └─────────────────────────────────────────────────────────────┘
   │
   ▼ ┌─────────────────────────────────────────────────────────────┐
     │ build_context_and_skeleton_node                            ② │
     │  读: sections_meta, field_type_map, linkage_using, copy_refs   │
     │  写: call_graph, entry_sequence(← callgraph)                   │
     │      var_lifecycle, review_items(← dataflow)                   │
     │      module_assignment, modules, module_skeletons,            │
     │      state_class_source, facade_skeleton(← 骨架构建)           │
     │      struct_registry(← build_struct_registry, 程序级算一次)    │
     └─────────────────────────────────────────────────────────────┘
   │
   ▼ ┌─────────────────────────────────────────────────────────────┐
[Send]│ translate_section_node  × N 段（并行）                      ③ │
  并行 │  读: current_section, field_type_map, java_field_names,       │
     │      struct_registry, module_assignment, io_context           │
     │  内部两遍:                                                      │
     │   1) segment+split_paragraphs → rules.build_section → 骨架     │
     │      (确定性: 控制流/GO TO 状态机/结构体 getter·setter)         │
     │   2) 叶子: translate_leaf 命中即固化; 未命中 → _translate_     │
     │      leaves_llm(带 RAG + IO 模板)                              │
     │   3) _postprocess_java_body: 下标/跨模块路由/st. 前缀          │
     │  写: translated_sections[method] (reducer 合并各并行结果)       │
     └─────────────────────────────────────────────────────────────┘
   │ (汇聚)
   ▼ ┌─────────────────────────────────────────────────────────────┐
     │ assemble_node                                              ④ │
     │  读: translated_sections, modules, module_skeletons,          │
     │      state_class_source, facade_skeleton, sections_meta,      │
     │      call_graph, review_items                                 │
     │  写出文件: <Base>State.java, <Base>Service.java,              │
     │           <Base>NNNNSection.java × N,                         │
     │           review_checklist.md, call_graph.md                 │
     └─────────────────────────────────────────────────────────────┘
   │
   ▼ output/ 多文件 Java + 审查产物
```

要点：
- **③ 是唯一可能调 LLM 的节点**，且只在"叶子规则未命中"时；①②④ 全确定性。
- `struct_registry` 在 ② 算一次、③ 各段复用；单段调试路径（`main.py --section`）则在 ③ 内按需 `build_struct_registry`。
- 字段裸名在 ③ 第 3 遍后处理统一加 `st.` 前缀，结构体局部对象（`xxxParams`）不加——靠 `java_field_names` 白名单区分。

---

## 七、快速上手

```bash
# 仅看骨架（确定性，不需要本地模型）
python main.py YOURPROG.cob --skeleton-only --output ./out

# 全量翻译（叶子规则优先；少数复杂叶子需本地 vLLM 在 http://localhost:8000）
python main.py YOURPROG.cob --output ./out

# 单段试译（调试规则/范式最快的回路）
python main.py YOURPROG.cob --section 2070-CHECK-REPRINT --output ./out

# 产物：./out/<Base>State.java、<Base>Service.java、<Base>NNNNSection.java、
#       review_checklist.md、call_graph.md
```
