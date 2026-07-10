# 操作记录 · parser-section-boundary-audit

## 目标

加固解析器段边界检测的测试覆盖，不新增翻译功能。

## 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `tests/fixtures/section_boundary.cob` | 新建 | 覆盖连续段/入口代码/同名变量/COPY 边界的 COBOL 夹具 |
| `test_translation.py` | 修改 | 新增 `TestSectionBoundary` (7 用例) + `TestParagraphExtraction` (3 用例) |
| `docs/操作记录/parser-section-boundary-audit操作记录.md` | 新建 | 本文件 |

## 测试覆盖

### TestSectionBoundary（7 用例）

| 测试 | 验证点 |
|------|--------|
| `test_consecutive_sections` | 连续 SECTION（中间无段落）全部识别，不丢失 |
| `test_section_name_with_special_chars` | 段名含连字符和数字，正确解析 |
| `test_entry_code_before_first_section` | PROCEDURE DIVISION 与首 SECTION 间代码 → `__ENTRY` 段 |
| `test_no_entry_code_with_immediate_section` | 首 SECTION 紧跟 PROCEDURE DIVISION → 无 `__ENTRY` |
| `test_section_after_empty_line` | SECTION 前有空行仍正常识别 |
| `test_fixture_section_boundary_integrity` | section_boundary.cob 段数/入口/同名变量正确 |
| `test_fixture_entry_code_content` | `__ENTRY` 段含入口代码 |
| `test_comment_lines_do_not_affect_section_count` | 注释内 SECTION 字样不影响段计数 |

### TestParagraphExtraction（3 用例）

| 测试 | 验证点 |
|------|--------|
| `test_paragraph_name_with_hyphen` | 段落名含连字符正确提取 |
| `test_consecutive_paragraphs_preserved` | 连续空段落不被丢弃 |
| `test_exit_only_paragraph` | EXIT-only 段落正确提取 |

## 验证结果

- 新增 11 测试：**全通过**
- 现有相关测试（`TestProcStartCommentImmune`/`TestAsgBuild`）：**全通过**
- `scripts/check.py --suite all`：**259 tests OK (skipped=2)**
- 未修改生产代码（`parser/cobol_parser.py` 不动）

## Token 使用分析

- `tests/fixtures/section_boundary.cob`：22 行
- `test_translation.py` 新增：~160 行（2 个测试类，11 个用例）
- 操作记录：~50 行

## 未覆盖项（留后续）

1. **50%-disabled line**：列7 'D' 的停用 SECTION 头（当前无生产代码支持，需等列模型扩展）
2. **COPY 展开后的段边界**：需 COPY 展开设施就绪后才能测试
3. **嵌套 COPY 段落**：同上
4. **REDEFINES + SECTION 同名**：当前测试了 01 级同名，未测嵌套级
