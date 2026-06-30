# 步骤32 STRING叶子语句固化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 为 COBOL `STRING ... DELIMITED BY ... INTO ...` 的保守子集增加确定性叶子翻译。

**架构：** 新增 `translator.leaf.string.translate_string(tokens, ctx)`，并通过现有 `translator.leaf` 门面对外导出。`translate_leaf_stmt` 接入 `STRING` 后，`translator.rules`、`rules._dispatch_leaf` 兼容 wrapper 和 ASG `LeafJavaVisitor.visit_Leaf` 会自然共享同一行为。不支持的 `STRING` 形态继续返回 `([], False)`，保留现有 TODO 兜底。

**技术栈：** Python 3.12、`unittest`、现有 `translator.leaf` helper、现有 ASG visitor 路径。

---

## 文件分工

- 修改：`test_translation.py`
  - 新增 `TestLeafStringExtract`。
  - 扩展 `TestUnifiedLeafEntry`。
  - 把现有“未固化叶子”的 `STRING` 示例改成 `UNSTRING`，避免步骤32后测试含义混乱。
- 新建：`translator/leaf/string.py`
  - 负责窄范围 `STRING` 解析和渲染。
- 修改：`translator/leaf/__init__.py`
  - 导出 `translate_string`。
  - 在 `translate_leaf_stmt` 中接入 `STRING`。
- 新建：`docs/详细设计/步骤32-STRING叶子语句固化设计.md`
- 新建：`docs/操作记录/步骤32-STRING叶子语句固化操作记录.md`
- 修改：`docs/架构索引/项目总览.md`

---

### 任务1：先写失败测试锁定 STRING 行为

**文件：**
- 修改：`test_translation.py`
- 测试：`test_translation.py`

- [ ] **步骤1：新增 `TestLeafStringExtract`**

放在 `TestLeafArithExtract` 之后、`TestAsgLeafArithVisitor` 之前：

```python
class TestLeafStringExtract(unittest.TestCase):
    """步骤32：STRING ... DELIMITED BY ... INTO ... 叶子翻译。"""

    FTM = {
        "wsaaA": {"type": "String"},
        "wsaaB": {"type": "String"},
        "wsaaC": {"type": "String"},
        "wsaaOut": {"type": "String"},
    }

    def _ctx(self):
        return _leaf_ctx(field_type_map=self.FTM)

    def test_delimited_by_size_concatenates_full_sources(self):
        from translator.leaf import translate_string

        toks = "STRING WSAA-A DELIMITED BY SIZE WSAA-B DELIMITED BY SIZE INTO WSAA-OUT".split()

        self.assertEqual(translate_string(toks, self._ctx()),
                         (["wsaaOut = wsaaA + wsaaB;"], True))

    def test_delimited_by_space_uses_first_space_boundary(self):
        from translator.leaf import translate_string

        toks = "STRING WSAA-A DELIMITED BY SPACE INTO WSAA-OUT".split()

        self.assertEqual(translate_string(toks, self._ctx()),
                         (['wsaaOut = String.valueOf(wsaaA).split(java.util.regex.Pattern.quote(" "), 2)[0];'],
                          True))

    def test_literal_delimiter_uses_first_delimiter_boundary(self):
        from translator.leaf import translate_string

        toks = ["STRING", "WSAA-A", "DELIMITED", "BY", "'/'", "INTO", "WSAA-OUT"]

        self.assertEqual(translate_string(toks, self._ctx()),
                         (['wsaaOut = String.valueOf(wsaaA).split(java.util.regex.Pattern.quote("/"), 2)[0];'],
                          True))

    def test_mixed_delimiters_concatenate_rendered_parts(self):
        from translator.leaf import translate_string

        toks = ["STRING", "WSAA-A", "DELIMITED", "BY", "SIZE",
                "WSAA-B", "DELIMITED", "BY", "SPACE",
                "WSAA-C", "DELIMITED", "BY", "'/'",
                "INTO", "WSAA-OUT"]

        self.assertEqual(translate_string(toks, self._ctx()),
                         (['wsaaOut = wsaaA + String.valueOf(wsaaB).split(java.util.regex.Pattern.quote(" "), 2)[0] + String.valueOf(wsaaC).split(java.util.regex.Pattern.quote("/"), 2)[0];'],
                          True))

    def test_unsupported_clauses_fall_through(self):
        from translator.leaf import translate_string

        cases = [
            "STRING WSAA-A DELIMITED BY SIZE INTO WSAA-OUT WITH POINTER WSAA-B",
            "STRING WSAA-A DELIMITED BY SIZE INTO WSAA-OUT ON OVERFLOW MOVE 1 TO WSAA-C",
            "STRING WSAA-A INTO WSAA-OUT",
            "STRING WSAA-A DELIMITED BY SIZE",
        ]
        for line in cases:
            self.assertEqual(translate_string(line.split(), self._ctx()), ([], False))

    def test_non_string_verb_falls_through(self):
        from translator.leaf import translate_string

        self.assertEqual(translate_string("UNSTRING WSAA-A DELIMITED BY SPACE INTO WSAA-OUT".split(),
                                          self._ctx()),
                         ([], False))
```

- [ ] **步骤2：扩展 `TestUnifiedLeafEntry`**

把 `_ctx` 改成包含字符串字段：

```python
    def _ctx(self):
        ctx = _leaf_ctx(field_type_map={
            "wsaaCount": {"type": "int"},
            "wsaaA": {"type": "String"},
            "wsaaB": {"type": "String"},
            "wsaaOut": {"type": "String"},
        })
        ctx.system_programs = {"SYSERR": {"java_code": "throw new RuntimeException()"}}
        return ctx
```

在 supported cases 中加入：

```python
            "STRING WSAA-A DELIMITED BY SIZE WSAA-B DELIMITED BY SIZE INTO WSAA-OUT",
```

把未迁动词测试改为 `UNSTRING`：

```python
    def test_translate_leaf_stmt_falls_through_for_unmigrated_verbs(self):
        from translator.leaf import translate_leaf_stmt

        self.assertEqual(translate_leaf_stmt("UNSTRING WSAA-A DELIMITED BY SPACE INTO WSAA-B".split(),
                                             self._ctx()),
                         ([], False))
```

新增 ASG 共享输出测试：

```python
    def test_asg_leaf_uses_shared_string_output(self):
        from asg import Leaf, LeafJavaVisitor

        ctx = self._ctx()
        raw = "STRING WSAA-A DELIMITED BY SIZE WSAA-B DELIMITED BY SIZE INTO WSAA-OUT"
        node = Leaf(tokens=raw.split(), raw=raw)

        self.assertEqual(LeafJavaVisitor(ctx).visit(node), ["wsaaOut = wsaaA + wsaaB;"])

    def test_asg_leaf_keeps_unsupported_string_placeholder(self):
        from asg import Leaf, LeafJavaVisitor

        raw = "STRING WSAA-A DELIMITED BY SIZE INTO WSAA-OUT WITH POINTER WSAA-B"
        node = Leaf(tokens=raw.split(), raw=raw)

        self.assertEqual(LeafJavaVisitor(self._ctx()).visit(node), [f"// TODO-LEAF: {raw}"])
```

- [ ] **步骤3：更新既有“未固化叶子”示例**

`TestAsgIfVisitor.test_if_body_unmigrated_leaf_placeholder` 改用 `UNSTRING`：

```python
        # 步骤32：STRING 已固化，改用仍未固化的 UNSTRING 验诚实占位
        node = IfStmt(cond=["WSAA-COUNT", "=", "1"],
                      then=[Leaf(tokens=["UNSTRING", "WSAA-A", "DELIMITED", "BY", "SPACE", "INTO", "WSAA-B"],
                                 raw="UNSTRING WSAA-A DELIMITED BY SPACE INTO WSAA-B")])
        self.assertIn("    // TODO-LEAF: UNSTRING WSAA-A DELIMITED BY SPACE INTO WSAA-B",
                      LeafJavaVisitor(self._ctx()).visit(node))
```

`TestAsgLeafArithVisitor.test_unmigrated_leaf_placeholder` 改用 `UNSTRING`：

```python
        node = Leaf(tokens="UNSTRING WSAA-A DELIMITED BY SPACE INTO WSAA-B".split(),
                    raw="UNSTRING WSAA-A DELIMITED BY SPACE INTO WSAA-B")
        self.assertEqual(LeafJavaVisitor(self._ctx()).visit(node),
                         ["// TODO-LEAF: UNSTRING WSAA-A DELIMITED BY SPACE INTO WSAA-B"])
```

- [ ] **步骤4：运行测试确认 RED**

```powershell
python -m unittest test_translation.TestLeafStringExtract test_translation.TestUnifiedLeafEntry -v
```

预期：`translate_string` import 失败，或 `STRING` 统一入口测试失败。

---

### 任务2：实现 `translator.leaf.string`

**文件：**
- 新建：`translator/leaf/string.py`
- 测试：`test_translation.py`

- [ ] **步骤1：新建 `translator/leaf/string.py`**

```python
from __future__ import annotations

from translator.leaf.context import LeafCtx
from translator.leaf.expr import _lvalue, _operand


_UNSUPPORTED = {"WITH", "ON", "NOT"}


def _before_delimiter(source: str, delimiter: str) -> str:
    return f"String.valueOf({source}).split(java.util.regex.Pattern.quote({delimiter}), 2)[0]"


def _delimiter_expr(tok: str, ctx: LeafCtx) -> str:
    if tok.upper() == "SPACE":
        return '" "'
    return _operand(tok, ctx)


def translate_string(tokens: list[str], ctx: LeafCtx) -> tuple[list[str], bool]:
    """Translate supported COBOL STRING leaf statements."""
    if not tokens or tokens[0].upper() != "STRING":
        return [], False
    u = [t.upper() for t in tokens]
    if any(t in _UNSUPPORTED for t in u):
        return [], False
    if "INTO" not in u:
        return [], False
    into_i = u.index("INTO")
    if into_i <= 1 or into_i + 2 != len(tokens):
        return [], False

    target = tokens[into_i + 1]
    parts: list[str] = []
    i = 1
    while i < into_i:
        if i + 3 >= into_i:
            return [], False
        source = tokens[i]
        if u[i + 1] != "DELIMITED" or u[i + 2] != "BY":
            return [], False
        delimiter = tokens[i + 3]
        source_expr = _operand(source, ctx)
        if delimiter.upper() == "SIZE":
            parts.append(source_expr)
        else:
            parts.append(_before_delimiter(source_expr, _delimiter_expr(delimiter, ctx)))
        i += 4

    if not parts:
        return [], False
    return [f"{_lvalue(target, ctx)} = {' + '.join(parts)};"], True
```

- [ ] **步骤2：运行直接 STRING 测试**

```powershell
python -m unittest test_translation.TestLeafStringExtract -v
```

预期：`TestLeafStringExtract` 全部通过。

---

### 任务3：接入共享叶子入口

**文件：**
- 修改：`translator/leaf/__init__.py`
- 测试：`test_translation.py`

- [ ] **步骤1：导入、导出并分派 `translate_string`**

在 `translator/leaf/__init__.py` 加：

```python
from translator.leaf.string import translate_string
```

在 `translate_leaf_stmt` 的 `CALL` 后、`translate_control` 前加：

```python
        if verb == "CALL":
            return translate_call(tokens, ctx)
        if verb == "STRING":
            return translate_string(tokens, ctx)
        return translate_control(tokens, ctx)
```

把 `"translate_string"` 加入 `__all__`。

- [ ] **步骤2：运行统一入口测试**

```powershell
python -m unittest test_translation.TestLeafStringExtract test_translation.TestUnifiedLeafEntry -v
```

预期：通过。

- [ ] **步骤3：运行附近 ASG 叶子测试**

```powershell
python -m unittest test_translation.TestAsgIfVisitor test_translation.TestAsgLeafArithVisitor test_translation.TestAsgControlVisitor -v
```

预期：通过。

---

### 任务4：补项目文档

**文件：**
- 新建：`docs/详细设计/步骤32-STRING叶子语句固化设计.md`
- 新建：`docs/操作记录/步骤32-STRING叶子语句固化操作记录.md`
- 修改：`docs/架构索引/项目总览.md`

- [ ] **步骤1：新增详细设计**

`docs/详细设计/步骤32-STRING叶子语句固化设计.md` 内容：

```markdown
# 步骤32 STRING叶子语句固化设计

日期：2026-06-30

## 目标

在步骤31统一叶子入口之后，为 `STRING ... DELIMITED BY ... INTO ...` 增加确定性翻译。实现只覆盖可保守建模的简单分隔符形态，不支持的 `STRING` 继续返回 `([], False)`，由调用方保持原有 TODO 兜底。

## 范围

- 新增 `translator.leaf.string.translate_string(tokens, ctx)`。
- `translator.leaf.translate_leaf_stmt` 增加 `STRING` 分支。
- `rules._dispatch_leaf` 继续只是兼容 wrapper，不新增独立分支。
- ASG `LeafJavaVisitor.visit_Leaf` 通过统一入口自动获得同一输出。

## 首版支持

- `DELIMITED BY SIZE`：完整拼接源项。
- `DELIMITED BY SPACE`：截取第一个空格之前的内容。
- `DELIMITED BY <literal-or-token>`：截取第一个 delimiter 之前的内容。
- 单个 `INTO <target>`。

## 明确不做

- 不做 `UNSTRING`、`INSPECT`、`SEARCH`。
- 不做 `WITH POINTER`、`ON OVERFLOW`、`NOT ON OVERFLOW`。
- 不新增 ASG 节点。
- 不改 SECTION 路由和 legacy fallback。
```

- [ ] **步骤2：新增操作记录**

`docs/操作记录/步骤32-STRING叶子语句固化操作记录.md` 内容：

```markdown
# 步骤32 STRING叶子语句固化操作记录

日期：2026-06-30

## 本次改动

- `translator/leaf/string.py`
  - 新增 `translate_string(tokens, ctx)`。
  - 支持简单 `STRING ... DELIMITED BY ... INTO ...`。
  - 对 `WITH POINTER`、`ON OVERFLOW`、缺失 `INTO` 等不支持形态返回 `([], False)`。
- `translator/leaf/__init__.py`
  - 导出 `translate_string`。
  - `translate_leaf_stmt` 增加 `STRING` 分支。
- `test_translation.py`
  - 新增 `TestLeafStringExtract`。
  - 扩展 `TestUnifiedLeafEntry`。
  - 将“未固化叶子”示例从 `STRING` 调整为 `UNSTRING`。

## 验收

- `python -m unittest test_translation.TestLeafStringExtract test_translation.TestUnifiedLeafEntry -v`
- `python -m unittest test_translation.TestAsgIfVisitor test_translation.TestAsgLeafArithVisitor test_translation.TestAsgControlVisitor -v`
- `python -m unittest test_translation`
- `python scripts/check.py`
```

- [ ] **步骤3：更新架构索引**

在步骤31附近增加：

```markdown
- **STRING叶子语句固化（步骤32）**：`translator.leaf.string.translate_string` 支持简单 `STRING ... DELIMITED BY ... INTO ...`，并通过 `translate_leaf_stmt` 同时供 rules 与 ASG `LeafJavaVisitor` 使用；不支持的 overflow/pointer/复杂形态继续保守 TODO。
```

在叶子翻译公共底座表加入：

```markdown
| `translator/leaf/string.py` | translator.leaf | `translate_string(toks, ctx)`：固化简单 `STRING ... DELIMITED BY ... INTO ...`，支持 SIZE/SPACE/字面量 delimiter；复杂 overflow/pointer 形态返回 `([], False)` |
```

---

### 任务5：完整验收

**文件：**
- 无生产改动。

- [ ] **步骤1：运行目标测试**

```powershell
python -m unittest test_translation.TestLeafStringExtract test_translation.TestUnifiedLeafEntry -v
python -m unittest test_translation.TestAsgIfVisitor test_translation.TestAsgLeafArithVisitor test_translation.TestAsgControlVisitor -v
```

预期：两个命令都 exit 0。

- [ ] **步骤2：运行完整翻译测试**

```powershell
python -m unittest test_translation
```

预期：OK，本地 vLLM 不可用时相关测试 skip。

- [ ] **步骤3：运行项目检查脚本**

```powershell
python scripts/check.py
```

预期：exit 0。

- [ ] **步骤4：检查范围 diff**

```powershell
git diff -- translator/leaf/string.py translator/leaf/__init__.py test_translation.py docs
```

预期：只包含步骤32范围内改动。
