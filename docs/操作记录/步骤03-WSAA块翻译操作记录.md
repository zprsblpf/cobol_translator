# 步骤03 · WSAA 块翻译 操作记录

日期：2026-05-31
对应设计：`../详细设计/步骤03-WSAA块翻译设计.md`

## 1. 新增/修改文件

新增包 `parser/ws/`：`__init__.py / model.py / lines.py / entry.py / conditions.py /
value.py / pic.py / tree.py`
新增包 `translator/wsaa/`：`__init__.py / render_field.py / render_condition.py /
render_view.py / render_class.py`
新增入口 `scripts/translate_wsaa.py`
修改 `config/type_mappings.yaml`：重写 `pic_rules`（V9→BigDecimal、COMP→long、裸 9 整数、
编辑 PIC→String、`max_digits` 由 9 的总位数判定）。

## 2. 执行命令

```bash
python scripts/translate_wsaa.py --program ZPOLDWNM \
  --in  /home/zp/Documents/cob/ZPOLDWNM/拆解/ZPOLDWNMWSAA.cob \
  --out /home/zp/Documents/cob/ZPOLDWNM/拆解/ZpoldwnmWsaa.java
```

## 3. 产物

`/home/zp/Documents/cob/ZPOLDWNM/拆解/ZpoldwnmWsaa.java`（1278 行）

## 4. 自检结果（逐项）

- 解析统计：01 级根 383、节点 891、组 95、叶子 796、88 条件 12、REDEFINES 22、OCCURS 27、编辑 PIC 18。
- 结构 lint（脚本 + 临时 python 检查）：
  - 字段 772，全部唯一（无重名 → 无 Java 重复声明）✔
  - public 方法 68，全部唯一 ✔
  - 花括号 `{`70 / `}`70 平衡 ✔
  - 无 `long/int = ""` 等 类型/初值 不匹配 ✔
  - 88 取值无关键字泄漏（修复前曾出现 `"VALUE"`/`"-NOTPRINT"`）✔
- 抽样核对（对照用户规范）：
  - `WSAA-PROG` → `String wsaaProg = "ZPOLDWN"` ✔
  - `WSAA-LETOKEYS`(30) → getter 拼接 + setter 切分（含 FILLER 占位）✔
  - `WSAA-A65086` → 4 个 `is6pwb/isWpdh/is2dwe/isDeej` 布尔方法 ✔
  - `WSAA-CP-AMOUNT-D` → `BigDecimal[27][4]`（二维）✔
  - `WSAA-CTRL-FLGS` REDEFINES → 3 个定宽切片 get/set 视图 ✔
  - 各 PIC 类型（999→int、9(15)V99→BigDecimal、Z(14)9.99→String、X'0F'→`""`）✔

## 5. 修复记录（开发期发现并修正）

1. WS 段头 `WORKING-STORAGE SECTION.` 误触发停止 → 加 `_SKIP_HEADER` 跳过。
2. `9(03)/99/999` 等被判 `long`/`String` → 重写 `pic_rules`，`_digits` 统计裸 9 位数。
3. `9(15)V99` 漏判小数 → 新增 `V9→BigDecimal` 规则。
4. `WSAA-SKIP-COMP` 因名字含 COMP 被判 `long` → COMP 正则加「前置空白」锚。
5. `CASH-VALUE-NOTPRINT` 因名字含 VALUE，88 取值混入 `"VALUE"/"-NOTPRINT"` → VALUE 正则加「前置空白」锚。
6. OCCURS 数组上下文内 REDEFINES 生成对数组的标量视图（非法）→ 加 `arrayed` 集合判定，退化 TODO。
7. 畸形叶子（带 PIC 又带子项）其子项未回填类型（默认 String）→ `backfill` 在叶子分支也递归子项。

## 6. 遗留（见设计文档 §5 已知限制）

数值/编辑型 REDEFINES、数组内 REDEFINES、外部 REDEFINES、畸形层级、INDICATOR 88
均以 `// TODO` 在产物内标注，待人工核对或后续步骤处理。

## 7. Token 使用分析

本任务 token 消耗偏高（估计达数十万级别，本会话 context 已偏大）。主要来源：

1. **大文件全文读取（最大头）**：`ZPOLDWNMWSAA.cob` 1177 行≈30k tokens（分页读两次）；
   `translator/rules.py` 1248 行整文件读取（实际仅复用两三个函数，偏重）；
   另加 nodes/skeleton/cobol_parser/variable_resolver 等。
2. **智能体多轮复利（结构性）**：约 30 个工具调用回合，每轮把全量对话+工具输出重新计费，
   早期读入的大文件在后续每轮反复重算，总量接近平方增长。
3. **调试迭代**：修 7 个 bug，多次「改→重新生成→grep 核对」回显生成的 Java 片段
   （`IS-AGE105-PRD` 几十个值的 88 条件被完整回显多次）。
4. **文本回显**：规范全文在 AskUserQuestion 答复中被重新粘回一次。

**下次可精简**：大文件用 grep 定位关键函数而非全文读；调试一次性批量 grep、少回显；
大 cob 只在脚本内处理、避免在对话里反复打印。

> ⚠️ 提醒：本会话 context 已偏多，若继续在同一会话叠加新任务，建议先 `/clear` 或
> 新开会话，避免 context 膨胀拖慢/增本。

