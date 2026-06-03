# 步骤09 — config 配置层重构 操作记录

> 日期：2026-06-04　|　设计：[步骤09-config配置层重构设计](../详细设计/步骤09-config配置层重构设计.md)
> 性质：纯结构重构（不改翻译输出，以回归逐字节比对为准）

## 一、目标回顾
把 `config/` 整理为**清晰、分层、零业务依赖、单一加载入口**的规范基座：消除 9+ 处重复 YAML 加载、
让访问层名副其实、清死配置、修正 config→parser 反向依赖、规范正本与映射分目录。

## 二、改动清单

### 新增（config 基础设施）
- `config/__init__.py` —— 显式包 + 分层说明。
- `config/yaml_cache.py` —— 唯一 YAML 加载入口 `load(name)`；**按裸文件名自动搜索 `config/` 根 / `specs/` / `mappings/`**，子目录对调用方透明。
- `config/conversions.py` —— 纯转换函数 `cobol_to_java_name` / `java_init`（由 parser 下沉）。

### 目录分层（yaml 物理归位，零代码改动）
- `config/specs/`：segmentation_spec、skeleton_spec、wsaa_translation_spec、wsaa_type_catalog。
- `config/mappings/`：type_mappings、naming_conventions、copy_mappings、io_mappings。

### 访问层
- `spec_loader.py`：删自带 `_load` → 收口 `yaml_cache`；新增 IO 访问 `io_programs/date_programs/system_programs/io_default_pattern`；命名/初值改引 `config.conversions`（不再 import parser）。
- `grammar_loader.py`：删自带 `_load` → 收口 `yaml_cache`。

### 收编外部直读（消除所有 `open(*.yaml)` 与自定义 `_load_yaml`）
- `translator/context.py`：IO 走 spec_loader；删**死加载** `copy_cfg`。
- `translator/naming.py`、`parser/ws/tree.py`：自定义加载器 → `yaml_cache.load`。
- `graph/nodes.py`、`main.py`、`translator/skeleton_gen/body_context.py`：IO 走 spec_loader；删 `import yaml`/`CONFIG_DIR`。

### 消冗余 / 修依赖 / 清死配置
- `parser/variable_resolver.py`：硬编码 `_get_java_type` + 死 `_TYPE_RULES`/`_load_type_rules` → 统一调 `spec_loader.java_type_of`（与 WSAA 渲染线同一正本）；`_cobol_to_java_name` 改为 `config.conversions` 别名。
- `parser/ws/value.py`：`java_init` 改 re-export 自 `config.conversions`（保留 extract_value_raw/literals）。
- `config/mappings/type_mappings.yaml`：删 0 引用的 `cobol_constants` / `status_constants`。
- **依赖方向**：config 已不再 import parser（`grep -rn "import parser" config/` 为空）。

### 工具与文档
- `scripts/regress_config_snapshot.py`：回归快照脚本（确定性 config 函数输出序列化）。
- 回填 `docs/架构索引/项目总览.md`（文件表 + config 包描述）；设计文档转 🟢已实现。

## 三、校验结果（逐项）
| 项 | 命令 | 结果 |
|---|---|---|
| config 无 parser 依赖 | `grep -rn "import parser" config/` | ✅ 空 |
| 全量 import | 导入 config/parser/translator/graph/main | ✅ OK |
| 回归快照逐字节 | `diff snap_before snap_final` | ✅ 无差异 |
| 单元测试 | `python -m unittest test_translation` | ✅ Ran 24, OK (skipped=2 为 LLM 用例) |
| 无残留直读 | `grep open(*.yaml)` 业务代码 | ✅ 仅经 yaml_cache |

回归基线：`/tmp/snap_before.json`（重构前 348 行）↔ `/tmp/snap_final.json`（重构后）完全一致。

## 四、注意事项
- 消冗余C（`_get_java_type` 收口）对所有代表性 PIC 输出与原硬编码一致；理论上仅「多个 `9(n)` 组的非小数整数」这类病态 PIC 可能因 `java_type_of` 累加全部数字位而判定更准——此为与 WSAA 渲染线**对齐**（修正潜在漂移），非回归劣化。

## 五、Token 使用分析
- **主要消耗**：① 阶段前的耦合面探查（多文件精读：spec_loader/grammar_loader/llm_config/context/naming/nodes/value/variable_resolver/pic/tree + 6 个 yaml），约占本任务读取量大头；② 多轮小步编辑 + 每阶段回归自检的工具往返。
- **控制手段**：探查用 grep 定位 + 精读片段（offset/limit），未全文读大文件；回归用脚本一次性输出快照并 `diff`，避免在对话回显大段产物；`wsaa_translation_spec.yaml`(381行) 仅读头部 18 行。
- **量级**：中等。读取集中在确定性 config/parser/translator 链路；大 yaml 基本未全文读入对话。
- **Context 提示**：本会话已含较完整的 config 重构上下文，量偏中上。若后续要叠加**新的独立任务**，建议先 `/clear` 或新开会话，仅带本操作记录 + 设计文档继续，避免多轮复利重算。
