# 步骤07 · 主线 SECTION 方法体确定性翻译 操作记录

执行日期：2026-06-03
对应设计：`../详细设计/步骤07-主线SECTION方法体确定性翻译设计.md`（🟢 已实现）

## 1. 落地产物

| 文件 | 性质 | 职责 |
|---|---|---|
| `translator/skeleton_gen/body_context.py` | 新增 | 备料 `build_body_ctx`(同 pipeline 配方) + 段级 `reset_section` + `translate_section_body` + 瘦后处理（决策A方案B/B1） |
| `translator/skeleton_gen/program_model.py` | 改 | `SectionModel` 加 `body_lines`；`build_model` 回填 `s.lines` |
| `translator/skeleton_gen/render_skeleton.py` | 改 | 建 ctx 一次；`_section_method` 接 rules 填体；去空体 TODO/PERFORM 尾注释；删无用导入 |
| `translator/postprocess.py` | 微改 | 抽模块级 `fix_array_subscripts`；`_prefix_fields_outside_strings` 加 `prefix` 参（默认 `st.`，graph 不变） |

> 决策固化（设计 §0）：复用方式=主线直接调 rules；决策A=方案B（瘦后处理仅数组下标+`wsaa.`前缀）；
> 决策B=B1（后处理把 `this.X()` 补 `this.X(wsaa, using…)`）。

## 2. 执行命令

```bash
# 全量渲染（含确定性方法体）
python scripts/translate_skeleton.py \
    --in /home/zp/Documents/cob/ZPOLDWNM.cob --out /tmp/Zpoldwnm.step07.java
# 回归测试
python test_translation.py
```

产物：`/tmp/Zpoldwnm.step07.java`（7268 行；步骤05 空体版为 1309 行）。

## 3. 验证结果（对应设计 §5）

| 项 | 期望 | 实测 |
|---|---|---|
| 方法数 | 不变（步骤06 基线 134=133段+execute） | ✅ 134 |
| `// TODO 方法体待译` | 归零 | ✅ 0 |
| `// TODO 叶子待译` | 量化规则覆盖率 | 712 条（无 LLM，符合预期） |
| LEAF 占位残留 | 0 | ✅ 0 |
| 花括号配平 | 配平 | ✅ 1019 / 1019 |
| 非法标识符 | 无数字开头 | ✅ 无 |
| 决策A wsaa. 前缀 | 生效 | ✅ 2309 处 |
| 决策B1 this.X(wsaa,…) | 生效 | ✅ 214 处 |
| 结构体访问器 | obj.getXxx/setXxx | ✅ 2933 处 |
| graph 回归 | postprocess 仍 `st.` | ✅ 测试通过，输出 `st.` |
| 测试套件 | 全通过 | ✅ 24 通过 / 2 skip |
| WSAA 回归 | 不受影响 | ✅ 未触 translator/wsaa（结构性保证） |

## 4. 已知事项（既有 rules 规则盲区，非本步引入）

少数未进 `field_type_map` 的名被规则当字面量渲染到赋值左侧（如 `"WSAA-A65086" = "";`、
`"DTC1-FUNCTION" = "TDAY";`），不可编译。该行为 graph 路径同样存在，按设计 §6 划出本步范围，
规则增强留后续独立步骤。

## 5. Token 使用分析

- **主要消耗**：① 探查阶段（精读 rules/segmenter/context/nodes/postprocess/pipeline 的接口契约，
  确定备料配方与两处架构接缝）轮数较多；② 写 1 新文件 + 改 3 文件；③ 1 轮渲染 + 1 轮校验脚本聚合输出
  （回显克制，统计用脚本汇总而非全文打印 7268 行产物）。
- **量级**：本步以「探查接口 + 接线」为主，新增逻辑集中（body_context ~70 逻辑行）。
- **Context 提醒**：本会话从 `/clear` 起，叠加探查多文件后已偏中等；如继续新步骤建议先 `/clear`。
