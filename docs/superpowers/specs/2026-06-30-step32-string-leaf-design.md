# 步骤32 STRING 叶子语句固化设计

## 目标

通过共享入口 `translator.leaf.translate_leaf_stmt`，为 COBOL `STRING` 叶子语句增加一个窄范围、可保守验证的确定性翻译能力。

## 范围

步骤32只新增一个叶子翻译器：

- 支持 `STRING ... DELIMITED BY ... INTO target`，前提是每个源项都使用简单分隔符。
- 通过 `translate_leaf_stmt` 接入，让 `translator.rules` 和 ASG visitor 共用同一实现。
- 不支持的 `STRING` 形态继续返回 `([], False)`，保留现有 TODO 兜底行为。
- 增加直接叶子翻译、统一入口、rules 兼容 wrapper、ASG `LeafJavaVisitor` 的聚焦测试。

首版支持：

- 一个或多个源项。
- 每个源项必须紧跟 `DELIMITED BY SIZE`、`DELIMITED BY SPACE` 或 `DELIMITED BY <literal-or-token>`。
- 单个 `INTO <target>` 子句。
- 源操作数和目标左值继续使用 `translator.leaf.expr` 里的现有 helper，保证命名、字面量、结构字段访问和字段类型判断与叶子层其它翻译保持一致。

非目标：

- 不实现 `UNSTRING`、`INSPECT`、`SEARCH` 或其它新动词。
- 不实现 `WITH POINTER`、`ON OVERFLOW`、`NOT ON OVERFLOW` 或多个 `INTO` 目标。
- 不新增 ASG 节点类型；`STRING` 仍然保持为 `Leaf`。
- 不修改 SECTION 路由、legacy fallback 或 `rules.build_section`。
- 不改变未支持动词的 TODO 文案。

## 语义

新增模块 `translator/leaf/string.py`，对外提供：

```python
def translate_string(tokens, ctx) -> tuple[list[str], bool]:
    ...
```

解析规则：

1. 第一个 token 必须是 `STRING`。
2. 从 `STRING` 后开始读取重复的源项，直到 `INTO`。
3. 每个源项形态必须是：

   ```text
   <source> DELIMITED BY <delimiter>
   ```

4. 缺少 `DELIMITED BY`、缺少 `INTO`、缺少目标字段，或目标字段后出现不支持的尾随子句时，返回 `([], False)`。
5. 出现 `WITH POINTER`、`ON OVERFLOW`、`NOT ON OVERFLOW` 时，首版不臆造语义，返回 `([], False)`。

渲染规则：

- `DELIMITED BY SIZE`：使用完整源操作数。
- `DELIMITED BY SPACE`：截取源字符串中第一个空格之前的部分。
- `DELIMITED BY <literal-or-token>`：截取源字符串中第一个 delimiter 之前的部分。
- 最终输出单条 Java 赋值：

  ```java
  target = part1 + part2 + part3;
  ```

分隔符处理不新增 Java runtime helper，直接生成局部表达式：

- `SIZE`：直接输出 `source`
- `SPACE`：按 `" "` 作为 delimiter
- 其它 delimiter：生成如下表达式

  ```java
  String.valueOf(source).split(java.util.regex.Pattern.quote(delimiter), 2)[0]
  ```

这样首版改动只停留在叶子翻译层。后续如果需要减少重复表达式，可以单独设计 Java helper 注入策略。

字面量和字段处理：

- 源项用 `_operand(source, ctx)`。
- 目标用 `_lvalue(target, ctx)`。
- delimiter 优先用 `_operand(delimiter, ctx)`，但 `SPACE` 固定归一为 `" "`。

必须保持未命中的例子：

- `STRING A DELIMITED BY SIZE INTO B WITH POINTER P`
- `STRING A DELIMITED BY SIZE INTO B ON OVERFLOW MOVE 1 TO C`
- `STRING A INTO B`
- `UNSTRING A DELIMITED BY SPACE INTO B`

## 架构

`translator.leaf` 已经是 rules 和 ASG 叶子渲染的共享门面。步骤32在门面下新增 `translate_string`，并把它接入 `translate_leaf_stmt`。

步骤32后的分派顺序：

1. `MOVE`
2. 算术和赋值动词
3. `CALL`
4. `STRING`
5. 控制类叶子词

现有已支持动词的行为不变。`STRING` 当前在所有路径都会 fall through，因此接入后属于覆盖率单调增加：rules 叶子兜底和 ASG `LeafJavaVisitor.visit_Leaf` 会通过同一个入口得到同一输出。

`rules._dispatch_leaf` 继续作为兼容 wrapper 保留，不新增自己的 `STRING` 分支。

## 测试

在 `test_translation.py` 新增 `TestLeafStringExtract`：

- `DELIMITED BY SIZE`：两个源字段拼接赋值。
- `DELIMITED BY SPACE`：输出“第一个空格前”截取表达式。
- 字面量 delimiter：输出 delimiter 截取表达式。
- 不支持子句返回 `([], False)`。
- 非 `STRING` 动词返回 `([], False)`。

扩展 `TestUnifiedLeafEntry`：

- `translate_leaf_stmt("STRING ...")` 与 `rules._dispatch_leaf` 输出一致。
- `LeafJavaVisitor.visit(Leaf(...STRING...))` 对支持形态输出同一条 Java，而不是 `// TODO-LEAF`。
- 不支持的 `STRING` 仍从入口返回 `([], False)`，ASG 侧仍输出 `// TODO-LEAF`。

验收命令：

```powershell
python -m unittest test_translation.TestLeafStringExtract test_translation.TestUnifiedLeafEntry -v
python -m unittest test_translation.TestAsgIfVisitor test_translation.TestAsgLeafArithVisitor -v
python -m unittest test_translation
python scripts/check.py
```

## 文档

实现完成后补齐项目文档：

- `docs/详细设计/步骤32-STRING叶子语句固化设计.md`
- `docs/操作记录/步骤32-STRING叶子语句固化操作记录.md`
- 更新 `docs/架构索引/项目总览.md`：增加步骤32记录，并在叶子翻译公共底座表中加入 `translator/leaf/string.py`。

## 风险

- COBOL `STRING` 的定长字段、overflow、pointer 语义比首版范围更复杂；无法保守建模的形态必须返回 `([], False)`。
- inline delimiter 表达式会偏长。这个步骤接受这一点，因为它避免把 Java helper 注入机制引入叶子层。
- `DELIMITED BY SPACE` 的 COBOL 语义是“到第一个空格为止”，不是普通的去首尾空白。测试必须锁定这一点，避免实现误用 `strip` 或 `trim`。
