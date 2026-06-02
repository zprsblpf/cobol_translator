# 步骤04 · WSAA 遗留补全（REDEFINES / INDICATOR 88 确定性补全）操作记录

执行日期：2026-06-03
对应设计：`../详细设计/步骤04-WSAA遗留补全设计.md`（🟢 已实现）
决策依据：`../../knowledge/wsaa_translation_decisions.md`（D8–D15 + 假设 A1/A2）

---

## 1. 改动文件

| 文件 | 动作 | 说明 |
|---|---|---|
| `translator/wsaa/storage.py` | 新增 | 定宽存储串构造：`scale_of` / `num_to_digits` / `num_from_digits` / `storage_accessor` / `NUM_HELPER`（`_toDigits`、`_fromDigits`） |
| `translator/wsaa/render_view.py` | 改 | 删 `_string_accessor`；`render_redefines` 基于 `storage_accessor`；新增 `_slice_view`/`_array_view`/`_scalar_view`/`render_primary` |
| `translator/wsaa/render_condition.py` | 改 | `render_conditions(holder, indexed)`；INDICATOR 88 数组上下文 → `indOn(int i)/indOff(int i)` |
| `translator/wsaa/render_class.py` | 改 | `_handle` 传 `indexed`；目标缺失 REDEFINES 走 `render_primary` 并入 fields；视图含数值串时追加 `NUM_HELPER` |
| `docs/详细设计/步骤04-…md` | 回填 | §8 实现结果 + 顶部状态 🟢 |
| `docs/详细设计/步骤03-…md` | 更新 | §5 已知限制标注已补全/保留项 |
| `docs/架构索引/项目总览.md` | 更新 | 登记 `storage.py` + 调用关系 |

## 2. 执行命令

```bash
python scripts/translate_wsaa.py --program ZPOLDWNM \
  --in  /home/zp/Documents/cob/ZPOLDWNM/拆解/ZPOLDWNMWSAA.cob \
  --out /home/zp/Documents/cob/ZPOLDWNM/拆解/ZpoldwnmWsaa.java
```

## 3. 校验结果（逐项）

- ✅ **TODO 由 27 → 10**（`grep -c TODO`）。剩余 10 处全部为已决定保留类：
  - 畸形层级 ×6（D14，源 295–327 区）；
  - 数组上下文 REDEFINES ×4（D13：WSXX-PCESTRM-X、WSXX-RCESTRM-X、WS01-PCESTRM-X、WS02-PCESTRM-X）。
- ✅ **A 字符/数值子项 over 数值**：`WSAA-AMOUNT1/2/3/5/6-CHAR`、`WSAA-AGE/TERM/PREMTRM-CHAR`、
  `WSAA-INVCAMT-CHAR`、`WSAA-RES-CRRCD` 的 `RCDYEAR/MONTH/DAY` — `_toDigits/_fromDigits` 双向同步正确。
- ✅ **B 数值 over 组**：`WSAA-STRING-R`/`-R-2`（`int` over SEX+ISSUE-AGE）切片回写正确。
- ✅ **C 字符数组 over 字符**：`WSAA-P`（X(2) OCCURS 5 over X(10)）→ `getWsaaP(int i)/setWsaaP(int i,String)`。
- ✅ **D INDICATOR 88**：`IND-ON/IND-OFF` → `indOn(int i)/indOff(int i)`（B'1'/B'0'）。
- ✅ **目标停用（D12）**：`WSAA-CVCP-AMOUNT-D` → 普通 `BigDecimal` 字段 + 注释，不再报 copybook TODO。
- ✅ **括号配平**：花括号 108/108；去注释与字符串后代码区圆括号净差 0。
  （唯一不配平的 `(` 来自被 `_short` 截断的 COBOL 原文注释 `S9(15)V9(2…`，无害。）
- ⚠️ `javac` 在本环境不可用，未做编译校验；以括号配平 + 逐例肉眼核对替代。

---

## Token 使用分析

- **主要消耗来源**：
  1. 续接探查：读设计 §0、决策库、3 个待改源文件 + 模型/pic/render_field（精读定位，单次批量并发读，约 6 个文件）；
  2. 真实数据核对：分段 grep/sed 读 `ZPOLDWNMWSAA.cob` 的 REDEFINES/INDICATOR 段（未全文读，省 token）；
  3. 校验回显：TODO 列表、抽样 get/set 片段、括号配平脚本（均小段输出）。
- **量级**：本任务为续接实现，无大文件全文读；工具调用约 15 轮，回显以小片段为主，属中等偏低消耗。
- **Context 提示**：本会话叠加了 CLAUDE.md（三份）+ 续接探查，context 处于中等水平；若继续叠加
  新步骤，建议 `/clear` 后凭 memory 续接，避免早期读入内容多轮复利重算。
