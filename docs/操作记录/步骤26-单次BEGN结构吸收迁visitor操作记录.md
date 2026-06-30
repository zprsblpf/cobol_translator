# 步骤26　单次 BEGN 结构吸收迁 visitor 操作记录

状态：🟢已实现（2026-06-29）

对应设计：`../详细设计/步骤26-单次BEGN结构吸收迁visitor设计.md`

---

## 1. 执行内容

1. `asg/nodes.py` 新增 `BegnSingleStmt`。
2. `asg/structure_rewrite.py`：
   - 新增 `rewrite_structures` 统一入口；
   - 新增 `rewrite_begn_single`；
   - 复刻旧 `_match_begn_single` 的 setup+CALL+IF 识别；
   - then 分支含 GO TO 时保守不吸收。
3. `asg/section_visitor.py`：
   - `render_paragraphs` 改用 `rewrite_structures`；
   - 新增 `visit_BegnSingleStmt`，渲染 `List<Record> ... findBy...Begn(...)` 与 `if (list.isEmpty())`。
4. `test_translation.py` 新增 3 条测试，覆盖 rewrite 命中/不命中、旧新 SECTION 产物一致。

---

## 2. 验收结果

```text
python -m unittest test_translation.TestAsgBegnSingleRewrite test_translation.TestAsgBegnSingleVisitor -v
Ran 3 tests
OK
```

```text
python -m unittest test_translation
Ran 164 tests
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

```text
python -m py_compile asg\structure_rewrite.py asg\section_visitor.py asg\visitor.py asg\nodes.py
OK
```

---

## 3. 边界确认

- 未切换主线，`translator.skeleton_gen.body_context` 仍走 `rules.build_section`。
- 只迁单次 BEGN；READR/READS、写 IO 未迁。
