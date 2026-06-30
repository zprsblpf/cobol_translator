# 步骤30 rules.build_section 旧路降级设计
状态：已实现（2026-06-30）

## 1. 背景

步骤29 已将主线 SECTION 方法体渲染切到 ASG `SectionJavaVisitor`：

- `translate_paragraphs_body` 默认调用 `_translate_paragraphs_body_asg`；
- ASG 失败时回退旧 `rules.build_section`；
- `scripts/diff_asg_vs_legacy.py --verb SECTION` 仍需要旧路作为逐字符比对参照。

因此 `rules.build_section` 不再是主线产物正本，但仍有两个保留价值：

- 作为 ASG 渲染异常时的保守 fallback；
- 作为迁移期对比工具的 legacy reference。

## 2. 目标与非目标

目标：

1. 在代码命名和注释上明确 legacy 边界。
2. 保持主线默认只走 `SectionJavaVisitor`。
3. 保持 fallback 和 diff reference 能力不变。
4. 用测试锁定：ASG 成功时不调用 legacy，ASG 失败时才使用 legacy fallback。

非目标：

- 不删除 `rules.build_section`。
- 不删除 `_rewrite_begn_loops` 等旧结构吸收代码。
- 不改变 `SectionJavaVisitor` 的结构吸收行为。
- 不改变 Java 产物。

## 3. 设计

在 `translator.skeleton_gen.body_context` 中保留原 helper：

```python
def _translate_paragraphs_body_legacy(...):
    ...
```

它仍表示旧路完整渲染器，供历史测试和比对参照直接调用。

新增窄 wrapper：

```python
def _translate_paragraphs_body_legacy_fallback(...):
    """Legacy SECTION renderer retained only for ASG failure fallback and diff/reference tests."""
    return _translate_paragraphs_body_legacy(...)
```

主线入口只在 ASG 异常时调用该 wrapper：

```python
try:
    return _translate_paragraphs_body_asg(...)
except Exception:
    return _translate_paragraphs_body_legacy_fallback(...)
```

这样调用图上可以清楚区分：

- `_translate_paragraphs_body_asg`：主线正本；
- `_translate_paragraphs_body_legacy_fallback`：异常回退入口；
- `_translate_paragraphs_body_legacy`：legacy reference 实现。

## 4. 测试策略

新增测试：

- `_translate_paragraphs_body_legacy_fallback` 与 `_translate_paragraphs_body_legacy` 输出一致；
- 既有测试继续覆盖 ASG 成功时不调用 legacy；
- 既有测试继续覆盖 ASG 失败时 fallback 输出与 legacy 一致。

回归命令：

```powershell
python -m unittest test_translation.TestMainlineSectionViaAsg test_translation.TestMainlinePendingRangeViaAsg -v
python scripts\diff_asg_vs_legacy.py tests\fixtures\minimal.cob --verb SECTION
python -m unittest test_translation
python scripts/check.py
```

## 5. 后续

后续若要真正删除 `rules.build_section`，应另开步骤，先迁走或替换所有 fallback/reference 依赖，并确认对比闸不再需要 legacy 产物。
