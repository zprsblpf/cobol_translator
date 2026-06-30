# 步骤27　READR/READS 单条读结构吸收迁 visitor 操作记录

状态：🟢已实现（2026-06-29）

对应设计：`../详细设计/步骤27-READR单条读结构吸收迁visitor设计.md`

---

## 1. 执行内容

1. `asg/nodes.py` 新增 `IoReadSingleStmt`。
2. `asg/structure_rewrite.py`：
   - `rewrite_structures` 增 READR pass；
   - 新增 `rewrite_readr_single`；
   - 新增 typed-node 版 `_statuz_form`、`_setup_func_code_nodes`、`_move_key_target_node`、`_match_readr_single_nodes` 等。
3. `asg/section_visitor.py`：
   - 新增 `visit_IoReadSingleStmt`；
   - 支持 `plain/ok/notok/error`；
   - then/else/try_tail 通过 `_render_rebound_body` 应用 record 重绑定。
4. `test_translation.py` 新增 5 条测试，覆盖 ok/error/不吸收与旧新 SECTION 产物一致。

---

## 2. 验收结果

```text
python -m unittest test_translation.TestAsgReadrSingleRewrite test_translation.TestAsgReadrSingleVisitor -v
Ran 5 tests
OK
```

```text
python -m unittest test_translation
Ran 169 tests
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
- 只迁 READR/READS 单条读；写 IO 未迁。
