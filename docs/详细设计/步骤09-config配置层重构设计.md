# 步骤09 — config 配置层重构设计

> 状态：🟢已实现（2026-06-04）
> 对应代码：`config/`（及其被 `translator/ parser/ graph/ main.py` 的引用点）
> 关联：[步骤05-翻译引擎](步骤05-cob到Java翻译引擎详细设计.md)、[步骤08-文法驱动骨架构建](步骤08-文法驱动骨架构建设计.md)
> 操作记录：[步骤09-config配置层重构操作记录](../操作记录/步骤09-config配置层重构操作记录.md)
>
> **实现要点（与设计的偏差）**：`yaml_cache.load` 最终采用「按裸文件名自动搜索 config 根 / specs / mappings」
> 方案（优于设计原稿的「调用方写子目录前缀」），使 yaml 物理归位对调用方透明、目录调整零代码改动。
> 回归：scripts/regress_config_snapshot.py 重构前后逐字节一致；test_translation 24 例全绿。

---

## 一、定位与目标

`config/` 是**全项目的规范基座**：一切翻译都由这里的"规范正本"驱动，后续会持续新增各层级规范
（已有：切分规范、骨架文法、WSAA 翻译规范；后续：过程语句翻译规范、其它块翻译规范……）。
因此本层必须**清晰、分层、零业务依赖、单一加载入口**。

本次重构目标（不改变任何翻译输出，纯结构整理 + 去冗余）：

1. **单一 YAML 加载入口**：消除散落 9+ 处的重复加载代码。
2. **访问层名副其实**：所有规范一律经访问层取，外部模块不再直读 yaml。
3. **清孤儿/死配置**：移走非运行时材料、删未引用配置。
4. **修正依赖方向**：config 成为最底层，不再反向依赖 `parser`。
5. **目录分层**：规范正本（specs）与配套映射（mappings）分目录，一眼看清层级。

---

## 二、现状诊断（重构动机）

### 冗余 A — YAML 加载逻辑重复 9+ 处
同一套 `CONFIG_DIR + open + yaml.safe_load(+lru_cache)` 被反复手写：
`config/spec_loader._load`、`config/grammar_loader._load`（与前者逐字相同）、
`translator/naming._load_yaml`、`graph/nodes._load_yaml`、
`translator/skeleton_gen/body_context`、`parser/variable_resolver._load_type_rules`、
`parser/ws/tree`、`translator/context`、`main.py`（后四者 inline open）。

### 冗余 B — 访问层形同虚设
`io_mappings.yaml` **没有任何访问函数**，被 5 处直接 `open`（context/main/nodes/body_context）；
`type_mappings.yaml` 一半经 `spec_loader`、一半被 `parser/ws/*` 直读。

### 冗余 C — PIC→Java 类型判定逻辑散 3 处
- `config/spec_loader.java_type_of` —— 查 `type_mappings.yaml` 的 `pic_rules`（**正本**）✓
- `parser/ws/pic.py` —— 也查 `pic_rules`（可接受，消费同一正本）
- `parser/variable_resolver._get_java_type` —— **硬编码 COMP/V9/X 分支、完全没读 yaml** ✗（逻辑重复且有漂移风险）

### 冗余 D — 死配置（仅删确无引用项）
- `type_mappings.yaml` 的 `cobol_constants` / `status_constants` 两块 —— **0 处引用**，死配置，删除。

> 注：`wsaa_type_catalog.yaml` 虽 0 运行时引用，但它是 **WSAA 翻译规范族**的"类型覆盖清单 + 样例"，
> 属规范配套、**必须留在 config 体现**（见 §七 决定 2）。不外迁 docs；若其格式不规整，在 config 内部归置。

### 冗余 E — 依赖方向倒置
`config/spec_loader.py` 反向 `import parser.variable_resolver._cobol_to_java_name` 与 `parser.ws.value.java_init`；
而 `parser/ws/*` 又直读 `config/type_mappings.yaml` ⇒ **config ↔ parser 双向耦合**。
（经核实：这两个被依赖的函数都是纯函数，仅用 `re`，无 parser 内部依赖，可安全下沉。）

### 缺陷 F — 无 `config/__init__.py`
现靠 Python 隐式 namespace package 偶然能 import，不稳健。

---

## 三、目标架构

### 3.1 目录结构

```
config/
├── __init__.py            # 显式包（新增）
├── yaml_cache.py          # 【基础设施】唯一 YAML 缓存加载器（新增）
├── conversions.py         # 【基础设施】纯转换函数（新增；接收从 parser 下沉的两函数）
├── llm_config.py          # 【基础设施】LLM 运行时配置（保持不动；非"规范"，是 infra）
│
├── specs/                 # 【规范正本】各层级翻译/文法规范（会持续增加）
│   ├── segmentation_spec.yaml      # 物理切分：列模型/词法/paragraph
│   ├── skeleton_spec.yaml          # 骨架文法：block_grammar/control_flow
│   ├── wsaa_translation_spec.yaml  # WSAA(数据)翻译规范正本
│   └── wsaa_type_catalog.yaml      # WSAA 规范族：类型覆盖清单 + 样例（规范配套，留在 config）
│
├── mappings/              # 【配套映射】规范引用的查表
│   ├── type_mappings.yaml          # PIC→Java 类型 pic_rules（删两块死常量）
│   ├── naming_conventions.yaml     # 命名范式（类/字段/COPY 角色）
│   ├── copy_mappings.yaml          # COPY 记录名→Java 类名
│   └── io_mappings.yaml            # CALL 'xxxIO'→Repository 范式+覆盖
│
├── grammar_loader.py      # 【访问层】切分+骨架文法访问（消费 specs/seg + specs/skeleton）
└── spec_loader.py         # 【访问层】翻译规范访问（消费 specs/wsaa + mappings/*）
```

### 3.2 分层与调用关系

```
   ┌─────────────────────── 业务层 ───────────────────────┐
   │ translator/  parser/  graph/  main.py                 │
   └───────────────┬───────────────────┬───────────────────┘
                   │ 只调访问层函数      │ 只调访问层函数
                   ▼                   ▼
        ┌──────────────────┐  ┌──────────────────┐   ← 访问层（config）
        │  spec_loader     │  │  grammar_loader   │
        │ (翻译规范+映射)   │  │ (切分+骨架文法)    │
        └────────┬─────────┘  └─────────┬─────────┘
                 │  conversions.py（纯函数）│
                 ▼                        ▼
        ┌────────────────────────────────────────┐
        │            yaml_cache.load()             │  ← 唯一加载入口
        └───────────────────┬──────────────────────┘
                            ▼
              config/specs/*.yaml + config/mappings/*.yaml   ← 规范正本（数据）
```

**关键不变量**：依赖方向单向向下（业务 → 访问层 → yaml_cache → 数据）；
config 包内部不依赖任何业务模块；外部不再出现 `open(... .yaml)`。

---

## 四、各文件/类/函数职责（详细设计）

### 4.1 `config/yaml_cache.py`（新增，基础设施）
- **做什么**：项目唯一的 YAML 读取+缓存入口。
- **函数** `load(name: str) -> dict`：`name` 为相对 `config/` 的路径（如 `"specs/skeleton_spec.yaml"`）。
  `@lru_cache` 缓存，文件缺失返回 `{}`（沿用 naming.py 现有容错语义）。
- **设计思路**：把 `spec_loader._load`/`grammar_loader._load`/各处 `_load_yaml` 收口到此。其余模块一律不再自定义加载器、不再持有 `CONFIG_DIR`。

### 4.2 `config/conversions.py`（新增，基础设施）
- **做什么**：承接从 parser 下沉的两个纯转换函数，斩断 config→parser 反向依赖。
- `cobol_to_java_name(cobol: str) -> str`：`WSAA-POLICY-NO → wsaaPolicyNo`（原 `parser/variable_resolver._cobol_to_java_name` 原样搬入）。
- `java_init(value_raw: str, java_type: str) -> str`：单值 VALUE→Java 初值（原 `parser/ws/value.java_init` 搬入；`extract_value_raw`/`literals` 是解析阶段逻辑，**仍留在** `parser/ws/value.py`，其 `java_init` 改为从本模块 re-export 以不破坏现有 import）。
- **设计思路**：命名范式与 VALUE→初值是"规范层概念"，理应位于 config；让 parser 反过来依赖 config（方向正确）。

### 4.3 `config/spec_loader.py`（重构）
保留全部现有公开函数（`java_type_of`/`init_of`/`field_name`/`class_name`/`copy_role`/`entity_class`/`service_class`/`service_field`）。改动：
- `_load` → 删除，改用 `yaml_cache.load`。
- `import parser.*` → 改为 `from config.conversions import cobol_to_java_name, java_init`。
- **新增 IO 访问函数**（收编 io_mappings 直读，合并逻辑从 context.py 上提）：
  - `io_default_pattern() -> dict`
  - `io_programs() -> dict`（已合并 `io_programs` + 旧缩进兼容键 `io_programs2`）
  - `date_programs() -> dict`
  - `system_programs() -> dict`

### 4.4 `config/grammar_loader.py`（小改）
公开函数不变；仅 `_load` 改用 `yaml_cache.load`，读取路径改 `specs/` 前缀。

### 4.5 `config/__init__.py`（新增）
显式包声明（可空 + 简短 docstring 说明本包定位）。

### 4.6 `config/llm_config.py`
**保持不动**（运行时基础设施配置，非规范，无重复加载问题）。

---

## 五、外部收编点（消除直读 / 重复加载）

| 文件 | 现状 | 改为 |
|---|---|---|
| `translator/context.py` | open io_mappings + copy_mappings | `spec_loader.io_programs()/date_programs()/...` + copy 访问 |
| `translator/naming.py` | 自定义 `_load_yaml` 读 naming/copy | 经 `spec_loader`（命名范式/copy 已有访问函数） |
| `graph/nodes.py` | 自定义 `_load_yaml` + open io_mappings | `spec_loader` IO 函数 |
| `main.py` | open io_mappings | `spec_loader` IO 函数 |
| `translator/skeleton_gen/body_context.py` | open io_mappings | `spec_loader` IO 函数 |
| `parser/variable_resolver.py` | `_load_type_rules` + 硬编码 `_get_java_type` | 统一调 `spec_loader.java_type_of`（消冗余 C）；`_cobol_to_java_name` 搬到 conversions |
| `parser/ws/tree.py` | open type_mappings | `yaml_cache.load` 或 `spec_loader` |
| `parser/ws/pic.py` | 读 type_mappings | 经 `yaml_cache.load`（保留其 pic 判定，仅换加载入口） |
| `parser/ws/value.py` | 定义 `java_init` | re-export 自 `config.conversions` |

---

## 六、迁移步骤（分阶段，每步可独立验证）

1. **建基础设施**：新增 `__init__.py`、`yaml_cache.py`、`conversions.py`（搬入两函数；`value.py`/`variable_resolver.py` 改为引用，保证 import 不破）。
2. **目录分层**：yaml 移入 `specs/`、`mappings/`；改 `spec_loader`/`grammar_loader` 内部 `load()` 路径。
3. **访问层补全**：`spec_loader` 加 IO 函数；两 loader 的 `_load` 收口到 `yaml_cache`。
4. **收编外部直读**：按第五节逐文件改造，消除所有 `open(...yaml)` 与自定义 `_load_yaml`。
5. **消冗余 C**：`variable_resolver._get_java_type` 改调 `spec_loader.java_type_of`。
6. **清死配置**：删 type_mappings 两块死常量（`cobol_constants`/`status_constants`）。`wsaa_type_catalog.yaml` 随 §六-2 移入 `specs/`，保留在 config。
7. **回归校验**：跑现有翻译流水线，比对 Java 产物逐字节不变（纯结构重构，输出必须一致）。
8. **回填**：更新 `docs/架构索引/项目总览.md` 的 config 条目；本文档状态 → 🟢已实现 + 操作记录。

---

## 七、已确认的决定

- 重构范围 = **最彻底档**（含修正 config→parser 依赖方向）。配置规范是代码基础，需清晰明了、可扩展。
- **先写本设计文档 → 用户认可 → 再编码 → 回填**。
- 纯结构重构：**不得改变任何 Java 翻译输出**，以回归比对为准。
- 决定 1：采用 `specs/` + `mappings/` 两子目录分层（用户认可）。
- 决定 2：**WSAA 翻译规范（含 `wsaa_type_catalog.yaml`）必须留在 config 体现**，不外迁 docs；放 `specs/`。格式若不规整，仅在 config 内部归置。
- 决定 3：访问层模块名**保持** `spec_loader` / `grammar_loader`，不改名（避免 import 大面积变动）。
