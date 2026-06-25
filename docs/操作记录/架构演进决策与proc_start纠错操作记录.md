# 操作记录　架构演进决策（三相分层）＋ proc_start 注释误判纠错

日期：2026-06-25
对应设计：
- `../详细设计/架构演进-三相分层(预处理-ASG-visitor)初步设计.md`（🔶待认可，路线图级）
- `../详细设计/步骤14-非过程段纠错与IF-CALL-STRING语句翻译设计.md` §1（🟢已实现）

---

## 1. 背景

用户对比 `proleap-cobol-parser`（ANTLR4 前端）后提出：本项目为何冗长复杂、能否借鉴 ANTLR4 思想。
经分析澄清「ProLeap 不译码、冗长在翻译不在解析、复杂度分本质/偶然两类」，决定：

- 产出**架构演进初步设计**（三相分层：预处理 → 自研轻量 ASG → visitor 翻译；增量绞杀式迁移；
  只偷 ANTLR4 思想、不引 ProLeap/不用全文法零容错，保留自研方言鲁棒前端）。
- **步骤14（IF/CALL/STRING 翻译）改期**到绞杀之后（那三类规则将迁入相3 visitor，老框架写＝白写）。
- **例外**：步骤14 §1 的 `proc_start` 注释误判 bug 立即单独修（旧管线整个绞杀期当回归基准，须输出可信）。

## 2. proc_start 纠错（落地内容）

| 项 | 内容 |
|---|---|
| 根因 | `parser/cobol_parser.py` 定位 proc_start 用裸大写行匹配 `\bPROCEDURE\s+DIVISION\b`，命中第10行注释 `*  The basic procedure division logic...` → proc_start=10（应=2498）→ 数据/环境段被当过程段 |
| 修法 | 定位 proc_start/ws_start/linkage_start 的循环里，先用 `cobol_columns.is_comment/is_deactivated` 跳注释/停用行再匹配（复用定列正本，单点根因修复） |
| 改动文件 | `parser/cobol_parser.py`（+4 行）、`test_translation.py`（新增 `TestProcStartCommentImmune`） |

## 3. 校验结果

| 项 | 命令 | 结果 |
|---|---|---|
| 单元测试 | `python -m unittest test_translation` | **44 通过**（skipped=2），含新增回归 |
| 真实程序 | `translate_skeleton --in cleaned_ZPOLDWNM.cob` | SECTION 数 **135→131**；TODO 总数 **1574→543**；层级号假叶子 **901→0** |
| 额外修对 | USING 入参 | `[]` → `['LETCMNT-PARAMS','PMSPNT-PARAMS']`（proc_start 错位时 USING 读的是注释行） |

旁注：`find_division`/`_clean_lines` 为改动前既存死代码，本次未触（范围纪律），留后续清理。

---

## Token 使用分析

- **主要消耗**：① ProLeap 评估文档 §7 与工程结构的只读复盘；② rules.py/body_context/render_skeleton/cobol_parser
  多文件 grep+精读定位（克制，单片段 ≤100 行）；③ 真实程序两次渲染冒烟（未打印 40 万字产物正文，只 grep 直方图/计数）；
  ④ 3 份文档写入（步骤14 设计、架构演进初步设计、本记录）＋ 1 代码 + 1 测试编辑。
- **量级**：中等偏上（本会话含一次架构级 brainstorming 多轮澄清 + 设计文档产出）。
- **context 提醒**：本会话已较长（含 ProLeap 复盘、步骤13 收尾核查、架构 brainstorming、proc_start 落地）。
  下一步若进入「相1 预处理抽取」等绞杀实操，建议**先 `/clear` 或新开会话**再叠加，避免早期大段探查内容被后续每轮复利重算。
