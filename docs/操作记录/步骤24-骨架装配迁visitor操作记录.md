# 步骤24　骨架装配迁 visitor 操作记录

状态：🟢已实现（2026-06-29）

对应设计：`../详细设计/步骤24-骨架装配迁visitor设计.md`

---

## 1. 执行内容

1. 新增 `asg/section_visitor.py`，实现 `SectionJavaVisitor`：
   - paragraph 顺序装配；
   - GO TO 回跳/force_sm 前向跳转状态机壳；
   - flow 模式内 GO/EXIT dispatch；
   - PERFORM section / paragraph / paragraph THRU out-of-line 目标解析。
2. `asg.nodes.Paragraph` 增 `body_lines`，`asg.builder` 填原始 COBOL 行，保证 pending 合成方法沿用旧契约。
3. `asg.__init__` 导出 `SectionJavaVisitor`。
4. `scripts/diff_asg_vs_legacy.py` 增 `--verb SECTION`：
   - 旧路：`rules.build_section` 后回填 leaves；
   - 新路：`SectionJavaVisitor.render_section`；
   - 比对完整可迁 SECTION 产物。
5. `test_translation.py` 新增 7 条测试：
   - `TestAsgSectionVisitorFlow`：无跳转、回跳状态机、force_sm 前向跳转；
   - `TestAsgSectionVisitorPerformTarget`：section 调用、单 paragraph pending、paragraph THRU pending；
   - `TestDiffAsgVsLegacySection`：整程序 SECTION 两路逐字符一致。

---

## 2. 验收结果

```text
python -m unittest test_translation.TestAsgSectionVisitorFlow test_translation.TestAsgSectionVisitorPerformTarget test_translation.TestDiffAsgVsLegacySection -v
Ran 7 tests
OK
```

```text
python -m unittest test_translation
Ran 158 tests
OK (skipped=2)
```

```text
python scripts\diff_asg_vs_legacy.py tests\fixtures\minimal.cob --verb SECTION
[OK] tests\fixtures\minimal.cob [SECTION]：2 条 SECTION 两路逐字符一致
```

```text
python test_smoke.py
Ran 1 test
OK
```

---

## 3. 边界确认

- 未切换主线，`translator.skeleton_gen.body_context` 仍调用 `rules.build_section`。
- 未迁 BEGN/NEXTR、READR/写 IO 结构吸收。
- 未迁 `struct_rebind`。
- `flow_label/flow_paragraphs` 未进入 `LeafCtx`，只存在于 `SectionJavaVisitor` 实例。
