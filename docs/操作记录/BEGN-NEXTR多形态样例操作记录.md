# 操作记录 · BEGN-NEXTR 多形态样例

## 目标

在现有 BEGN for-each 测试基础上，增加多键和嵌套 IF 等形态的测试覆盖。

## 修改

| 文件 | 修改 |
|------|------|
| `test_translation.py` | 扩展 `TestAsgBegnForeachRewrite`（+2 用例）+ `TestAsgBegnForeachVisitor`（+2 用例） |

### 新增 SRC 夹具

- **`SRC_MULTIKEY`**：双键 `CHDRNUM + CHDRCOY` 的 BEGN+NEXTR 循环
- **`SRC_NESTED_IF`**：for-each 体内含 `IF WSAA-FLAG = 'Y'` 条件分支

### 新增测试

| 测试 | 位置 | 验证点 |
|------|------|--------|
| `test_multikey_begn_foreach` | Rewrite | 多键 BEGN → 提取 2 个 key（CHDRNUM + CHDRCOY） |
| `test_begn_foreach_with_nested_if` | Rewrite | 循环体内 IF 保留在 body 中 |
| `test_multikey_begn_foreach_visitor` | Visitor | 多键渲染 → `And<Key2>Begn` 方法调用 |
| `test_begn_nested_if_visitor` | Visitor | 嵌套 IF → 循环体内 IF 保留 |

## 验证

```powershell
python -m unittest test_translation.TestAsgBegnForeachRewrite test_translation.TestAsgBegnForeachVisitor -v
# → 7 tests OK（含 4 新增）

python scripts/check.py --suite asg
# → 56 tests OK

python scripts/check.py --suite all
# → 无回归
```
