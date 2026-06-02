# 步骤06 · COBOL 解析器列对齐与停用行修复设计

状态：✅ 已认可（2026-06-03）
依据：步骤05 已知事项（`步骤05-cob到Java翻译引擎详细设计.md` §10.3）
概要索引：见 `../架构索引/项目总览.md`

> 三层职责：本文件属**代码实现层**。讲「修哪个函数、怎么修、为什么、影响谁、怎么回归」。

---

## 1. 背景与缺陷（量化）

步骤05 骨架引擎复用 `parser/cobol_parser.parse()`，暴露该解析器对 `ZPOLDWNM.cob` 的两个缺陷。
同一程序，离线拆解线 `decompose/` 解析正确，**两套列处理逻辑不一致**：

| # | 缺陷 | 现象 | 量化 |
|---|---|---|---|
| 1 | **col7 吞首字母** | 代码起于第 7 列的行，首字母被当指示符丢弃 | `  100-MAIN SECTION.` → 段名 `AIN`（应为 `MAIN`） |
| 2 | **`!!!!!!` 停用段误纳** | cols1–6 为 `!!!!!!` 的停用旧 SECTION 被当有效段 | 误纳 18 个（`8040-ACMV-INF`/`8040A-ACMV-INF`/重复 `B320-INCSUM-INF` 等） |

对照：`cobol_parser` 解析 **151** 段，`decompose` 口径 **133** 段；差集 18 个全为停用段 + 被吞名的 `AIN`。
本文件无 'D' 调试行（D=0）。

## 2. 根因分析

`parser/cobol_parser.py` 自带列处理，与 `decompose/lines.py`（成熟、正确）**重复且不一致**，违背「复用优先 / 单一正本」：

| 处理点 | `cobol_parser._strip_cobol_line` | `decompose/lines.py`（正确） |
|---|---|---|
| 代码区起点 | `raw[7:72]`（col8 起，**丢 col7**） | `clean_line`：`raw[6:72]`（**含 col7**，指示符并入 `\s*` 吸收） |
| 注释行 | col7 ∈ `* / D` → 返回 ""（按列丢） | `is_comment`：col7 ∈ `* /`（D 不算注释） |
| 停用行 | **无判定**（漏） | `is_deactivated`：cols1–6 == `!!!!!!` → 丢 |
| 行尾变更标记 | 靠 `[7:72]` 截断 | `_CHANGE_TAG_RE` 显式剥离 `<CSV001>` |

- 正常行（代码在 col8）下，`raw[6:]` 比 `raw[7:]` 多一个 col7 空格，被解析正则的 `^\s*` / `.strip()` 吸收，**无害**；
  仅当代码异常起于 col7 时，`raw[7:]` 才吞字母——故修复对标准行零影响。
- 停用段误纳源于 `cobol_parser` 既不识别 `!!!!!!`、`_parse_sections` 也不复用 `_effective`。

## 3. 修复方案（复用优先；两选项，待你拍板）

核心一致：**列处理收口为单一正本，`cobol_parser` 不再自带 `_strip_cobol_line`**。差异在正本落在哪：

### 选项 A（最小改动）：`cobol_parser` 直接复用 `decompose.lines`
- `parser/cobol_parser.py` 导入并复用 `decompose.lines` 的 `is_deactivated`/`is_comment`/`clean_line`/`_effective`。
- 依赖方向：`parser.cobol_parser → decompose.lines`（`decompose.lines` 仅依赖 `re`，无环）。
- 代价：通用解析器反向依赖业务「拆解包」，层次略别扭。

### 选项 B（推荐·依赖更顺）：列处理下沉到 `parser/` 基础模块
- 新建 `parser/cobol_columns.py`（或 `parser/lines.py`），承载列处理为**单一正本**。
- `decompose/lines.py` 与 `parser/cobol_parser.py` 都复用它（`decompose.lines` 可保留薄包装或直接改导入）。
- 依赖方向：`decompose → parser`（自然，拆解线本就建在解析层之上），无环。
- 代价：改动多一处（`decompose/lines.py` 改为复用），但架构最干净、正本归位。

> 两选项的解析行为**完全一致**，仅差「正本文件放哪 + 依赖方向」。推荐 **B**。

## 4. 各改动点（函数级；以选项 B 描述，A 同理仅导入来源不同）

### 4.1 新增 `parser/cobol_columns.py`（选项 B；A 则复用 decompose.lines，不新增）
迁移/收口列处理函数（语义同 `decompose/lines`，补 'D' 调试行处理以兼容 cobol_parser 既有语义）：
- `is_deactivated(raw)`：cols1–6 == `!!!!!!`。
- `is_comment(raw)`：col7 ∈ `* /`。
- `is_debug(raw)`：col7 == `D`（cobol_parser 既有：跳过调试行；decompose 无此概念，本文件 D=0 无差异）。
- `clean_line(raw)`：`raw[6:72]` + 剥离行尾 `<...>` 变更标记 + rstrip。
- `effective(raw)`：停用/注释/调试/空 → None，否则 `clean_line`。

### 4.2 `parser/cobol_parser.py` 改动
- `_strip_cobol_line(raw)`：**删除自有实现**，改为：停用/注释/调试 → 返回 ""（保持「行被跳过」语义），其余 → `clean_line(raw)`。
  这样 WS/LINKAGE 变量解析、PIC 提取等下游**逻辑不变**，只是列基准对齐（col7 起，含原 col7 字符）。
- `_parse_sections(...)`：SECTION 头识别改用 `effective(raw)`（跳过停用/注释行）再匹配 `_SECTION_RE`，
  使 `!!!!!!` 停用段不再成为边界（修缺陷 2）。`_SECTION_RE` 与 decompose 同一份（可一并收口）。
- COPY 收集：现用 `not line.strip().startswith("!")` 近似判停用，改为 `not is_deactivated(raw)`（按 cols1–6 精确判），更准。

### 4.3 不改动
- `parser/ws/*`（WSAA 解析走独立路径，不经 `_strip_cobol_line`）——故 **WSAA 产物不受影响**。
- `decompose/` 的拆解行为（选项 B 仅把 `lines` 的实现来源换成复用 `parser` 正本，输出不变）。

## 5. 影响面（消费方）

`parser.cobol_parser.parse` 被这些直接消费：`graph/pipeline.py`（graph 线）、`parser/variable_resolver.py`、
`scripts/translate_skeleton.py`、`main.py`、`test_translation.py`。

**预期产出变化（属修正，非回退）**：
- 骨架 `Zpoldwnm.java`：SECTION 数 **151 → 133**；`AIN`→`main`；18 个停用段不再出现（步骤05 的方法去重兜底仍保留）。
- graph 线 SECTION 元数据同步修正（停用段不再计入、段名正确）。

## 6. 验证 / 回归计划（实现后执行，回填 §9）

1. **段名/段数**：`parse(ZPOLDWNM.cob)` 段数 = 133，含 `MAIN`，不含 `AIN` 及任何 `!!!!!!` 段；与 decompose 口径一致。
2. **骨架重生成**：`translate_skeleton` → 133 个方法、含 `main(...)`、花括号配平、无重复方法。
3. **WSAA 回归不变**：`translate_wsaa` 产物与现状 `diff` 仍为空（证明 4.3 不波及 WSAA）。
4. **标准行零影响**：抽样核对若干代码在 col8 的 WS 变量/PIC 解析结果与修复前一致。
5. **冒烟**：`graph/pipeline` 解析路径、`variable_resolver`、`test_translation.py` 导入/运行不报错。

## 7. 待确认的决定

1. **方案选 A 还是 B**（推荐 B：列处理下沉 `parser/`，依赖方向 `decompose→parser`）。
2. 'D' 调试行：保留 cobol_parser 既有「跳过」语义（推荐，零风险），还是统一为 decompose 的「不特殊处理」。

## 8. 已确认的决定（固化）

1. **方案 B**：新建 `parser/cobol_columns.py` 作列处理单一正本；`decompose/lines.py` 改为**薄重导出**
   （保留 `_effective` / `clean_block` 等公开名，行为不变），`cobol_parser` 复用该正本。依赖方向 `decompose → parser`。
2. **'D' 调试行保留跳过**：D-skip 仅在 `cobol_parser._strip_cobol_line` 内处理；共享的 `effective()`
   只跳过停用/注释（= decompose 现有行为），保证 decompose 输出不变。
3. **简化实现**：`!!!!!!` 停用段的过滤通过「`_strip_cobol_line` 对停用行返回 ''」级联到段/变量解析，
   无需在 `_parse_sections` 另引 `effective()`；COPY 收集改用 `is_deactivated(raw)` 精确判停用。

## 9. 实现结果（已回填）

状态：🟢 已实现（2026-06-03）。

### 9.1 落地文件
- `parser/cobol_columns.py`：**新增**·列处理单一正本（`is_deactivated`/`is_comment`/`is_debug`/`indicator`/`clean_line`/`effective`/`clean_block`）。
- `decompose/lines.py`：**改**·薄重导出 `parser.cobol_columns`（保留 `_effective`/`clean_block` 等公开名，行为不变）。
- `parser/cobol_parser.py`：**改**·`_strip_cobol_line` 复用 `cobol_columns`（停用/注释/调试→''，余 clean_line）；COPY 收集改用 `is_deactivated`。

### 9.2 验证结果（对应 §6）
1. ✅ 段数 `151 → 133`，含 `MAIN`、不含 `AIN`，无重复段，不含 `8040-ACMV-INF` 等停用段；与 decompose 口径一致。
2. ✅ 骨架重生成：134 个方法（execute + 133 段，全唯一）、含 `main`、花括号配平 136/136、无非法标识符。
3. ✅ WSAA 回归：`translate_wsaa` 产物与现状 `diff` 仍为空（证明不波及 WSAA 路径）。
4. ✅ 标准行零影响：col8 行经 `clean_line` 多带的 col7 空格被 `^\\s*`/`.strip()` 吸收；WS 抽样 888 变量名/PIC 正常无吞字符、无异常名。
5. ✅ 冒烟：`decompose.lines` 重导出 API 正常；`variable_resolver`/`pipeline`/`context`/`assemble`/`main` 导入无误。
