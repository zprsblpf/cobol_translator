# T13/T14 WS 字段限定与视图增强操作记录

日期：2026-07-02

## 范围

- T13：为 COBOL `A OF B` / `A IN B` 增加可测试的限定字段解析 helper。
- T14：按全局翻译规范增强 REDEFINES 处于 OCCURS 数组上下文时的视图生成。可证明 target/alias 处于同一祖先 OCCURS 维度时，生成带下标参数的 getter/setter；维度不一致或目标不可定宽时继续显式 TODO。

## 实现

- `translator/naming.py`
  - 新增 `parse_qualified_field_reference(text)`。
  - 新增 `resolve_qualified_field_reference(text, ctx)`，只通过 `ctx.qualified_field_map` 显式解析；未知或歧义时返回 `None`，不猜测绑定。
- `translator/leaf/expr.py`
  - `_operand` 识别单字符串形式的 `OF` / `IN` 限定字段。
  - 已登记限定名输出对应 Java 字段名；未登记限定名输出带 `TODO unresolved qualified field` 的字符串字面量，避免静默当成普通裸词。
- `translator/wsaa/render_class.py`
  - `_index_and_groups` 从数组布尔上下文扩展为数组维度表。
  - REDEFINES 渲染时向 view 层传递数组维度。
- `translator/wsaa/render_view.py`
  - `_todo_plain` 支持数组维度表。
  - 新增数组上下文 REDEFINES accessor：根据祖先 OCCURS 维度生成 `getX(int i, ...)` / `setX(int i, ..., v)`，内部访问 `field[i - 1]` / `field[i - 1][j - 1]`。
  - 只有 target 与 alias 维度一致、target 可定宽表示时转正；否则保守 TODO。

## 保守边界

- 未改 `translator/leaf/cond.py`、`translator/leaf/control.py`、`scripts/translate_skeleton.py` 等其他 worker 范围。
- 当前 T13 不重写多 token 语句流，例如 tokenized 的 `MOVE A OF B TO C` 仍需要后续在语句层组装限定字段 token。
- 未自动从 WS 树全量生成 `qualified_field_map`；本次先提供稳定 helper 和显式 ctx 接口。
- T14 只转正可证明一一对应的数组元素视图；维度不一致、COMP-3/编辑型/复杂嵌套组等形态继续 TODO，不静默猜测。

## 验证

- 红测试：
  - `python -m unittest test_t13_t14_ws_views -v`
  - 初始失败：缺少 `parse_qualified_field_reference` / `resolve_qualified_field_reference`。
  - T13 实现后，T14 失败暴露数组上下文退化字段丢失 OCCURS 维度。
- 绿测试：
  - `python -m unittest test_t13_t14_ws_views -v`：4 tests OK。
  - `python -m unittest test_t13_t14_ws_views test_translation.TestNameCollision test_translation.TestSignedOverpunch test_translation.TestLeafMoveExtract -v`：16 tests OK。
  - `python -m unittest test_translation test_t13_t14_ws_views -v`：234 tests OK，skipped=2。

## 2026-07-02 设计变更：数组 REDEFINES 受限转正

用户确认 T14 不应长期保守 TODO；相关全局规则已补入 `docs/翻译标准/变量定义.md` 的“数组上下文内 REDEFINES 视图规范”。

本次补强：

- 一维祖先 `OCCURS` 下，`REDEFINES` target/alias 维度一致时生成 `getX(int i)` / `setX(int i, ..., v)`。
- 二维祖先 `OCCURS` 下生成 `getX(int i, int j)` / `setX(int i, int j, ..., v)`。
- getter/setter 内部只访问同一 backing 元素，例如 `wsaaRaw[i - 1]`、`wsaaRaw[i - 1][j - 1]`。
- target/alias 维度不一致时继续 TODO，不猜测跨元素覆盖。

新增验证：

```powershell
python -m unittest test_t13_t14_ws_views -v
python -m unittest test_translation.TestNameCollision test_translation.TestSignedOverpunch test_translation.TestLeafMoveExtract -v
```

结果：`test_t13_t14_ws_views` 6 tests OK；相关回归 12 tests OK。
