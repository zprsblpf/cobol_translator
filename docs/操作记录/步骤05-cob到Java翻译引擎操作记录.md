# 步骤05 · cob → Java 翻译引擎 操作记录

执行日期：2026-06-03
对应设计：`../详细设计/步骤05-cob到Java翻译引擎详细设计.md`（🟢 已实现）

## 1. 落地产物

| 文件 | 性质 | 职责 |
|---|---|---|
| `config/spec_loader.py` | 新增 | 规范访问层：`java_type_of`/`init_of`/`field_name`/`class_name`/`copy_role`/`entity_class`/`service_class`/`service_field` + `FIELD_DECL` |
| `config/naming_conventions.yaml` | 改 | 新增 `service_copybooks: [VARCOM]` |
| `translator/skeleton_gen/__init__.py` | 新增 | 暴露 `render_skeleton` |
| `translator/skeleton_gen/program_model.py` | 新增 | CobolProgram → SkeletonModel |
| `translator/skeleton_gen/copy_resolver.py` | 新增 | COPY 角色分流（服务/实体/常量） |
| `translator/skeleton_gen/render_skeleton.py` | 新增 | 装配主类骨架（含方法去重） |
| `translator/wsaa/render_field.py` | 改 | 类型/初值/命名/样式串改经 spec_loader |
| `translator/wsaa/render_class.py` | 改 | `_class_base` → `spec_loader.class_name` |
| `scripts/translate_skeleton.py` | 新增 | 瘦入口 `--in/--out` |

> 命名决定（固化于设计 §2）：骨架包名 `translator/skeleton_gen/`（旧 `skeleton.py` 温存，避免同名冲突）；
> SECTION 方法名复用 `_section_to_method`（保留数字后缀防碰撞）；服务类 `PascalCase(名)+Service`。

## 2. 执行命令与产物

```bash
# WSAA 回归（必须逐字节一致）
cp 拆解/ZpoldwnmWsaa.java /tmp/ZpoldwnmWsaa.before.java
python scripts/translate_wsaa.py --program ZPOLDWNM \
    --in 拆解/ZPOLDWNMWSAA.cob --out /tmp/ZpoldwnmWsaa.after.java
diff before after        # → 空（一致）

# 骨架生成
python scripts/translate_skeleton.py \
    --in /home/zp/Documents/cob/ZPOLDWNM.cob --out /tmp/Zpoldwnm.java
```

产物：`/tmp/ZpoldwnmWsaa.after.java`（1414 行）、`/tmp/Zpoldwnm.java`（1309 行）。

## 3. 自检结果（对应设计 §9）

1. ✅ 规范加载：spec_loader 三件套查询正确（char/decimal/comp3、VARCOM→service、LETCMNTSKM→LetcmntParams）。
2. ✅ 骨架 `Zpoldwnm.java`：主类名 `Zpoldwnm`；151 个 SECTION 方法（名唯一、无数字开头非法标识符）；
   `USING LETCMNT-PARAMS`→入参；入口 `new ZpoldwnmWsaa()`；299 条 `PERFORM`→调用注释；
   花括号配平 153/153；停用重复段 `B320-INCSUM-INF` 去重为注释。
3. ✅ WSAA `ZpoldwnmWsaa.java`：与改造前 `diff` 为空（逐字节回归一致）；`// TODO` 仍为 10。
4. ✅ 结构 lint：括号配平、方法去重、类型-初值匹配通过（无 javac 环境）。

## 4. 已知事项（上游 parser，非本步骤缺陷）

`parser/cobol_parser._strip_cobol_line` 取 `raw[7:]`（标准固定格式列8起为代码）。本源文件个别行首列
偏移，如 `  100-MAIN SECTION.` 段名 `MAIN` 起于第 7 列（指示符列）→ 首字母被吞为 `AIN`，约 11 个段受影响。
该 parser 被 `graph.pipeline` / `variable_resolver` 共用，修复超出步骤05 范围，列为独立后续。
骨架引擎对解析器给定的段名忠实渲染，自身逻辑无误。

## 5. Token 使用分析

- **主要消耗**：① 前期只读探查（精读 spec/parser 模型/既有 wsaa 渲染 5+ 文件）约占多数；
  ② 工具调用轮数中等（探查 → 写 9 个文件 → 2 轮验证 + 1 轮调试方法去重 → 文档回填）；
  ③ 大文件回显克制：拆解目录列举一次、源文件仅 grep/精读定位关键行，未全文读入。
- **量级**：本会话 context 偏中等。建议如继续叠加「步骤06/方法体翻译」等新任务，先 `/clear` 或新开会话，
  避免多轮复利把前期读入的渲染代码反复重算。
