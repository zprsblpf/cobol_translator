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

## 分派顺序

`translate_leaf_stmt` 的顺序调整为：

1. MOVE
2. 算术/赋值动词
3. CALL
4. STRING
5. 控制类叶子词

## 测试策略

- `TestLeafStringExtract` 锁定 `SIZE`、`SPACE`、字面量 delimiter、混合拼接和不支持形态。
- `TestUnifiedLeafEntry` 锁定 rules wrapper 与 ASG visitor 共用同一输出。
- 既有用 `STRING` 表示“未固化动词”的测试改用 `UNSTRING`，避免步骤32后语义含糊。
