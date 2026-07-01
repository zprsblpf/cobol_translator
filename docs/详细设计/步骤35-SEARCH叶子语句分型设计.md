# 步骤35-SEARCH叶子语句分型设计

## 状态

已实现。

## 目标

对 `SEARCH` 叶子语句做显式分型，但不生成确定性 Java。`SEARCH` 依赖表定义、OCCURS/INDEXED BY、索引状态、`AT END` 范围和 `WHEN` 后续动作，leaf 层上下文不足，不能臆造循环。

## 分型结果

以下形态均稳定返回 `([], False)`，交由 fallback 处理：

- `SEARCH table WHEN condition`
- `SEARCH table AT END ... WHEN condition ...`
- `SEARCH table VARYING index WHEN condition ...`
- `SEARCH ALL table WHEN condition ...`

## 实现点

- `translator/leaf/search.py`：新增 `translate_search`，只做 verb 识别和显式 fallback。
- `translator/leaf/__init__.py`：在统一 leaf 入口接入 `SEARCH`。
- `test_translation.py`：新增 `TestLeafSearchExtract`，锁定 SEARCH 不被误译。

## 验证

```powershell
python -m unittest test_translation.TestLeafSearchExtract test_translation.TestUnifiedLeafEntry -v
python scripts/check.py --suite leaf
```
