# 步骤06 · COBOL 解析器列对齐与停用行修复 操作记录

执行日期：2026-06-03
对应设计：`../详细设计/步骤06-COBOL解析器列对齐与停用行修复设计.md`（🟢 已实现）

## 1. 落地产物

| 文件 | 性质 | 职责 |
|---|---|---|
| `parser/cobol_columns.py` | 新增 | 列处理单一正本：`is_deactivated`/`is_comment`/`is_debug`/`indicator`/`clean_line`/`effective`/`clean_block` |
| `decompose/lines.py` | 改 | 薄重导出 `parser.cobol_columns`（保留 `_effective`/`clean_block` 等公开名，行为不变） |
| `parser/cobol_parser.py` | 改 | `_strip_cobol_line` 复用 cobol_columns（停用/注释/调试→''，余 clean_line）；COPY 收集改用 `is_deactivated` |

> 方案 B（列处理下沉 parser/，依赖方向 decompose→parser）+ 'D' 调试行保留跳过（设计 §8 固化）。

## 2. 修复的两个缺陷

1. **col7 吞首字母**：`raw[7:]`→`clean_line`（`raw[6:]`，含指示列）。代码异常起于第7列的行首字母不再丢。
2. **`!!!!!!` 停用段误纳**：`_strip_cobol_line` 对停用行返回 ''，级联到段/变量解析；COPY 用 `is_deactivated` 精确判。

## 3. 验证结果（对应设计 §6）

| 项 | 期望 | 实测 |
|---|---|---|
| 段数 | 151→133，含 MAIN、无 AIN、无停用段、无重复 | ✅ 133 / MAIN✓ / AIN✗ / 8040-ACMV-INF✗ / 重复段=[] |
| 骨架重生成 | 134 方法(含 main)、配平、无非法标识符 | ✅ 134 唯一 / main✓ / 136-136 / 无数字开头 |
| WSAA 回归 | 与现状 diff 为空 | ✅ 逐字节一致 |
| 标准行零影响 | col8 行 col7 空格被 strip 吸收 | ✅ WS 888 变量名/PIC 正常，无吞字符/异常名 |
| 冒烟 | decompose+各消费方导入运行 | ✅ decompose.lines API 正常；variable_resolver/pipeline/context/assemble/main 导入无误 |

## 4. Token 使用分析

- **主要消耗**：① 根因探查（精读 decompose/lines、blocks，列布局逐字节核对，差集量化）；
  ② 工具调用轮数较少（探查 → 写 3 文件 → 1 轮验证，含 2 次测试断言自纠）；③ 回显克制，均用脚本聚合输出。
- **量级**：本步骤增量小（3 文件、改动集中）。叠加步骤05 后本会话 context 已偏中等，
  如继续新任务建议先 `/clear` 或新开会话。
