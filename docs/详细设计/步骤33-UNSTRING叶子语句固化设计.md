# 步骤33-UNSTRING叶子语句固化设计

## 状态

已实现。

## 目标

为保守子集的 `UNSTRING ... DELIMITED BY ... INTO ...` 增加确定性 Java 翻译，并接入 `translator.leaf.translate_leaf_stmt`，让 legacy rules 与 ASG visitor 共用同一实现。

## 支持范围

- `UNSTRING source DELIMITED BY SPACE INTO target`
- `UNSTRING source DELIMITED BY literal INTO target1 target2 ...`

生成形态：

```java
{
    String[] __unstringTarget = String.valueOf(source).split(java.util.regex.Pattern.quote(delimiter), -1);
    target1 = __unstringTarget.length > 0 ? __unstringTarget[0] : "";
    target2 = __unstringTarget.length > 1 ? __unstringTarget[1] : "";
}
```

外层块用于限制临时数组变量作用域，避免同一 Java 方法内多条 UNSTRING 生成重复局部变量声明。

## 保守边界

以下形态继续返回 `([], False)`，交由 fallback 处理：

- 缺少 `DELIMITED BY`
- 缺少 `INTO` 或目标字段
- `WITH POINTER`
- `ON OVERFLOW` / `NOT ON OVERFLOW`
- `COUNT` / `DELIMITER` 相关子句

## 实现点

- `translator/leaf/unstring.py`：新增 `translate_unstring`
- `translator/leaf/__init__.py`：在统一 leaf 入口接入 `UNSTRING`
- `test_translation.py`：新增 `TestLeafUnstringExtract`，扩展 `TestUnifiedLeafEntry` 与 ASG visitor 共享输出测试

## 验证

```powershell
python -m unittest test_translation.TestLeafUnstringExtract test_translation.TestUnifiedLeafEntry -v
python scripts/check.py --suite leaf
```
