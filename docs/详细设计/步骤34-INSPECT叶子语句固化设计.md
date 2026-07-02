# 步骤34-INSPECT叶子语句固化设计

## 状态

已实现。

## 目标

为保守子集的 `INSPECT ... REPLACING` 与 `INSPECT ... TALLYING` 增加确定性 Java 翻译，并接入 `translator.leaf.translate_leaf_stmt`。

## 支持范围

### REPLACING

支持：

```cobol
INSPECT WSAA-A REPLACING ALL 'A' BY 'B'
```

生成：

```java
wsaaA = String.valueOf(wsaaA).replace("A", "B");
```

### TALLYING

支持：

```cobol
INSPECT WSAA-A TALLYING WSAA-COUNT FOR ALL 'A'
```

生成：

```java
wsaaCount += (String.valueOf(wsaaA).length() - String.valueOf(wsaaA).replace("A", "").length()) / "A".length();
```

## 保守边界

以下形态继续返回 `([], False)`：

- `REPLACING FIRST`
- `TALLYING ... FOR CHARACTERS`
- `CONVERTING`
- 非字面量替换值
- 其它复杂组合子句

## 实现点

- `translator/leaf/inspect.py`：新增 `translate_inspect`
- `translator/leaf/__init__.py`：在统一 leaf 入口接入 `INSPECT`
- `test_translation.py`：新增 `TestLeafInspectExtract`，扩展 `TestUnifiedLeafEntry` 与 ASG visitor 共享输出测试

## 验证

```powershell
python -m unittest test_translation.TestLeafInspectExtract test_translation.TestUnifiedLeafEntry -v
python scripts/check.py --suite leaf
```
