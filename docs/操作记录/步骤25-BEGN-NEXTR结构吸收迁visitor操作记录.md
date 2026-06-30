# 步骤25　BEGN/NEXTR 结构吸收迁 visitor 操作记录

状态：🟢已实现（2026-06-29）

对应设计：`../详细设计/步骤25-BEGN-NEXTR结构吸收迁visitor设计.md`

---

## 1. 执行内容

1. `asg/nodes.py` 新增 `BegnForeachStmt`。
2. 新增 `asg/structure_rewrite.py`：
   - `rewrite_begn_foreach` 复刻旧 `_rewrite_begn_loops` Pass 1；
   - 命中 BEGN+NEXTR 自跳循环后替换 loop paragraph；
   - 剥除前序同前缀 setup；
   - `tag_rebind_nodes` 递归标记 `struct_rebind`。
3. `asg/visitor.py` 的 `LeafJavaVisitor` 增 `_with_rebind`，让 visitor 直译路径支持旧 rules 的重绑定语义。
4. `asg/section_visitor.py`：
   - `render_paragraphs` 接入 `rewrite_begn_foreach`；
   - 新增 `visit_BegnForeachStmt`，渲染 `List<Record>` + `for-each` + filter continue + body。
5. `asg/__init__.py` 导出 `BegnForeachStmt`。
6. `test_translation.py` 新增 3 条测试，覆盖 rewrite 命中/不命中、旧新 SECTION 产物一致。

---

## 2. 验收结果

```text
python -m unittest test_translation.TestAsgBegnForeachRewrite test_translation.TestAsgBegnForeachVisitor -v
Ran 3 tests
OK
```

```text
python -m unittest test_translation
Ran 161 tests
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
- 只迁 BEGN+NEXTR foreach；单次 BEGN、READR/READS、写 IO 未迁。
- `struct_rebind` 仍为动态属性，后续是否升为显式节点待设计。
