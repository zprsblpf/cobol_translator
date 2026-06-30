#!/usr/bin/env python3
"""
COBOL → Java 翻译器回归测试。

固化了 2026-05 修复的若干 bug 的检测，外加本地模型的连通性 / 翻译能力验证。
零第三方依赖，直接用标准库 unittest。

运行：
    /data/models/llm-fa312/bin/python -m unittest test_translation -v
    # 或
    /data/models/llm-fa312/bin/python test_translation.py

说明：
- 纯逻辑测试（后处理、变量解析）始终运行，不依赖模型。
- 本地模型测试在 vLLM (http://localhost:8000) 不可用时自动 skip。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

LLM_BASE_URL = "http://localhost:8000"


def _llm_available() -> bool:
    """探测本地 vLLM 是否在线。"""
    try:
        import requests
        resp = requests.get(f"{LLM_BASE_URL}/v1/models", timeout=3)
        return resp.status_code == 200 and bool(resp.json().get("data"))
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
# 1. 后处理：_postprocess_java_body
#    Bug：旧正则把 setter/finder 方法调用误判成 COBOL 数组下标。
# ══════════════════════════════════════════════════════════════════════════════
class TestPostprocessJavaBody(unittest.TestCase):
    def setUp(self):
        from translator.postprocess import _postprocess_java_body
        self.fn = _postprocess_java_body

    def test_setter_call_not_converted(self):
        """对象的 setter 调用不应被改成数组下标。"""
        out = self.fn("itemparams.setIntDate(wsaaIntDate);")
        self.assertEqual(out, "itemparams.setIntDate(wsaaIntDate);")

    def test_finder_call_not_converted(self):
        """repository.findByKey(...) 不应被改成下标。"""
        out = self.fn("itemRepository.findByKey(itemparams);")
        self.assertEqual(out, "itemRepository.findByKey(itemparams);")

    def test_method_with_string_literal_not_converted(self):
        out = self.fn('itemparams.setFunction("READR");')
        self.assertEqual(out, 'itemparams.setFunction("READR");')

    def test_cobol_subscript_converted(self):
        """COBOL 1-based 下标 wsaaP(ix) → wsaaP[ix - 1]。"""
        out = self.fn("wsaaP(ix) = 1;")
        self.assertEqual(out, "wsaaP[ix - 1] = 1;")

    def test_cobol_subscript_in_loop(self):
        out = self.fn("wsaaNamePer(iw) = 1;")
        self.assertEqual(out, "wsaaNamePer[iw - 1] = 1;")

    def test_existing_bracket_index_untouched(self):
        """已经是 [i - 1] 形式的不应被破坏。"""
        src = 'wsaaName[iw - 1] = "";'
        self.assertEqual(self.fn(src), src)

    def test_setlength_zero_rewritten(self):
        out = self.fn("wsaaText.setLength(0);")
        self.assertEqual(out, 'wsaaText = "";')

    def test_method_signature_stripped(self):
        out = self.fn("private void foo() {\nx = 1;")
        self.assertNotIn("private void foo", out)
        self.assertIn("x = 1;", out)


# ══════════════════════════════════════════════════════════════════════════════
# 2. 变量解析：resolve / generate_field_declarations
#    Bug A：同名字段被重复声明 → Java 编译失败。
#    Bug B：无 PIC 的 GROUP OCCURS 声明成 Object[] 却初始化 new String[]。
# ══════════════════════════════════════════════════════════════════════════════
class TestVariableResolver(unittest.TestCase):
    def setUp(self):
        from parser.cobol_parser import Variable
        from parser.variable_resolver import resolve, generate_field_declarations
        self.Variable = Variable
        self.resolve = resolve
        self.gen = generate_field_declarations

    def _var(self, name, pic="X(10)", occurs=0, redefines="", is_group=False, comp=""):
        # Variable(level, name, pic, comp, occurs, redefines, is_group)
        return self.Variable(1, name, pic, comp, occurs, redefines, is_group)

    def test_duplicate_scalar_deduped(self):
        fields = self.resolve([
            self._var("WSCC-PROG"),
            self._var("WSCC-PROG"),
        ])
        names = [f.java_name for f in fields]
        self.assertEqual(names.count("wsccProg"), 1)

    def test_duplicate_array_deduped(self):
        fields = self.resolve([
            self._var("WSAA-RPU-ROW", occurs=4),
            self._var("WSAA-RPU-ROW", occurs=4),
        ])
        names = [f.java_name for f in fields]
        self.assertEqual(names.count("wsaaRpuRow"), 1)

    def test_declaration_has_no_duplicates(self):
        """生成的字段声明里没有重复的字段名。"""
        decl = self.gen(self.resolve([
            self._var("WSCC-PROG"),
            self._var("WSCC-PROG"),
            self._var("WSAA-RPU-ROW", occurs=4),
            self._var("WSAA-RPU-ROW", occurs=4),
        ]))
        self.assertEqual(decl.count("wsccProg ="), 1)
        self.assertEqual(decl.count("wsaaRpuRow ="), 1)

    def test_group_array_type_consistent(self):
        """无 PIC 的 GROUP OCCURS 字段类型与初始化器一致（不能 Object[] = new String[]）。"""
        decl = self.gen(self.resolve([
            self._var("WSAA-NAME-PER", pic="", occurs=10, is_group=True),
        ]))
        self.assertIn("private String[] wsaaNamePer = new String[10];", decl)
        self.assertNotIn("Object[]", decl)

    def test_array_type_init_match(self):
        """所有数组声明：左侧类型与右侧 new T[] 一致。"""
        import re
        decl = self.gen(self.resolve([
            self._var("ARR-STR", pic="X(5)", occurs=3),
            self._var("ARR-NUM", pic="9(5)", occurs=3),
            self._var("ARR-DEC", pic="S9(5)V9(2)", occurs=3),
        ]))
        for m in re.finditer(r"private (\w+)\[\] \w+ = new (\w+)\[", decl):
            self.assertEqual(m.group(1), m.group(2),
                             f"数组类型不匹配: {m.group(0)}")


# ══════════════════════════════════════════════════════════════════════════════
# 3. SECTION 名 → 方法名
# ══════════════════════════════════════════════════════════════════════════════
class TestSectionToMethod(unittest.TestCase):
    def setUp(self):
        from translator.skeleton import _section_to_method
        self.fn = _section_to_method

    def test_num_word(self):
        self.assertEqual(self.fn("1000-INIT"), "init1000")

    def test_word_only(self):
        # 无数字段时回退到拼接
        self.assertTrue(self.fn("SYSERR-SECTION"))


# ══════════════════════════════════════════════════════════════════════════════
# 3a2. PERFORM A THRU B 跨段不丢中间段（步骤12 §2）
#     Bug：旧实现只取 header[0] 当过程名，THRU B 被忽略 → 跨多段时丢中间段。
# ══════════════════════════════════════════════════════════════════════════════
class TestPerformThru(unittest.TestCase):
    def _ctx(self, order):
        import translator.rules as r
        return r.Ctx(field_type_map={}, section_to_method=lambda s: "p_" + s.replace("-", "").lower(),
                     known_sections=set(order), section_order=list(order))

    def _range(self, header, order):
        import translator.rules as r
        hu = [h.upper() for h in header]
        return r._perform_range(header, hu, header[0].upper(), self._ctx(order), 0)

    def test_thru_spans_sections_expanded(self):
        """A THRU B 跨段 → 区间内每段都生成调用，不丢中间段 C。"""
        order = ["A-SEC", "C-SEC", "B-SEC"]
        out = "\n".join(self._range(["A-SEC", "THRU", "B-SEC"], order))
        self.assertIn("p_asec();", out)
        self.assertIn("p_csec();", out)   # 中间段不可丢
        self.assertIn("p_bsec();", out)

    def test_thru_single_unit_one_call(self):
        """A THRU B 相邻且 B 紧接（A==B 或仅一段）→ 单调用，不啰嗦。"""
        out = self._range(["A-SEC", "THRU", "A-SEC"], ["A-SEC", "B-SEC"])
        self.assertEqual([l for l in out if "p_" in l], ["this.p_asec();"])

    def test_thru_unknown_endpoint_todo(self):
        """端点非已知 SECTION（paragraph 级）→ 退化 TODO + pA()，不臆测、不静默丢。"""
        out = "\n".join(self._range(["2000-INIT", "THRU", "2000-EXIT"], ["2000-INIT"]))
        self.assertIn("TODO", out)
        self.assertIn("p_2000init();", out)

    def test_no_thru_single_call_unchanged(self):
        """无 THRU → 单调用，历史行为不变。"""
        out = self._range(["A-SEC"], ["A-SEC", "B-SEC"])
        self.assertEqual(out, ["this.p_asec();"])

    # ── 步骤13：paragraph 级 THRU 区间（路线b 合成区间方法）──
    def _pctx(self, proc_order, section_order=None):
        import translator.rules as r
        return r.Ctx(field_type_map={}, section_to_method=lambda s: "p_" + s.replace("-", "").lower(),
                     known_sections=set(section_order or []), section_order=list(section_order or []),
                     proc_order=list(proc_order))

    def _prange(self, header, ctx):
        import translator.rules as r
        hu = [h.upper() for h in header]
        return r._perform_range(header, hu, header[0].upper(), ctx, 0)

    def test_thru_paragraph_range_synthesizes_method(self):
        """paragraph 级 A THRU B（同段，B 在后）→ 合成区间方法、登记 pending、调用点单次 this.xThruY()。"""
        proc = [("S", "section", "S", []),
                ("PARA-A", "paragraph", "S", ["  MOVE 1 TO X"]),
                ("PARA-M", "paragraph", "S", ["  MOVE 2 TO Y"]),
                ("PARA-B", "paragraph", "S", ["  MOVE 3 TO Z"])]
        ctx = self._pctx(proc)
        out = "\n".join(self._prange(["PARA-A", "THRU", "PARA-B"], ctx))
        mname = "p_paraaThruP_parab"
        self.assertIn(f"this.{mname}();", out)              # 单次合成调用
        self.assertIn(mname, ctx.pending_range_methods)     # 已登记落地
        # 区间内三单元按 proc_order 序、带标签登记（步骤14 §2.1：不丢中间 PARA-M、不丢标签）
        self.assertEqual(ctx.pending_range_methods[mname],
                         [("PARA-A", ["  MOVE 1 TO X"]), ("PARA-M", ["  MOVE 2 TO Y"]),
                          ("PARA-B", ["  MOVE 3 TO Z"])])

    def test_thru_paragraph_range_cross_section(self):
        """跨 SECTION 的 paragraph 区间（D2）：proc_order 含 SECTION 头单元，区间天然覆盖、不丢。"""
        proc = [("S1", "section", "S1", []),
                ("PARA-A", "paragraph", "S1", ["  A"]),
                ("S2", "section", "S2", ["  SHDR"]),
                ("PARA-B", "paragraph", "S2", ["  B"])]
        ctx = self._pctx(proc)
        out = "\n".join(self._prange(["PARA-A", "THRU", "PARA-B"], ctx))
        self.assertIn("this.p_paraaThruP_parab();", out)
        self.assertEqual(ctx.pending_range_methods["p_paraaThruP_parab"],
                         [("PARA-A", ["  A"]), ("S2", ["  SHDR"]), ("PARA-B", ["  B"])])

    def test_thru_paragraph_idempotent(self):
        """同区间重复 PERFORM 只合成一次（幂等）。"""
        proc = [("PARA-A", "paragraph", "S", ["  A"]), ("PARA-B", "paragraph", "S", ["  B"])]
        ctx = self._pctx(proc)
        self._prange(["PARA-A", "THRU", "PARA-B"], ctx)
        self._prange(["PARA-A", "THRU", "PARA-B"], ctx)
        self.assertEqual(len(ctx.pending_range_methods), 1)

    def test_thru_paragraph_duplicate_name_degrades(self):
        """端点重名（无法保守界定边界，D3）→ 退化 TODO，不臆测、不合成。"""
        proc = [("PARA-A", "paragraph", "S", ["  A"]), ("PARA-B", "paragraph", "S", ["  B"]),
                ("PARA-A", "paragraph", "S2", ["  A2"])]
        ctx = self._pctx(proc)
        out = "\n".join(self._prange(["PARA-A", "THRU", "PARA-B"], ctx))
        self.assertIn("TODO", out)
        self.assertEqual(ctx.pending_range_methods, {})

    def test_thru_paragraph_b_before_a_degrades(self):
        """B 在 A 之前 / 单单元（含 C-3 单条 PERFORM paragraph）→ 退化 TODO，不合成。"""
        proc = [("PARA-B", "paragraph", "S", ["  B"]), ("PARA-A", "paragraph", "S", ["  A"])]
        ctx = self._pctx(proc)
        out = "\n".join(self._prange(["PARA-A", "THRU", "PARA-B"], ctx))
        self.assertIn("TODO", out)
        self.assertEqual(ctx.pending_range_methods, {})

    # ── 步骤14 D14-1：合成区间方法保留 paragraph 标签（让区间内 GO TO 可被状态机路由）──
    def test_thru_paragraph_registers_labeled_units(self):
        """登记的不是无标签拼接行，而是带标签的单元序列 [(label, body), …]，
        让 build_section 重见区间内 paragraph 边界（步骤14 §2.1 根因修复）。"""
        proc = [("PARA-A", "paragraph", "S", ["  MOVE 1 TO X"]),
                ("PARA-M", "paragraph", "S", ["  MOVE 2 TO Y"]),
                ("PARA-B", "paragraph", "S", ["  MOVE 3 TO Z"])]
        ctx = self._pctx(proc)
        self._prange(["PARA-A", "THRU", "PARA-B"], ctx)
        self.assertEqual(ctx.pending_range_methods["p_paraaThruP_parab"],
                         [("PARA-A", ["  MOVE 1 TO X"]),
                          ("PARA-M", ["  MOVE 2 TO Y"]),
                          ("PARA-B", ["  MOVE 3 TO Z"])])

    # ── 步骤15（C-3）：单条 PERFORM <paragraph> → 合成单段方法，调用点 this.pXxx() 不变 ──
    def test_perform_single_paragraph_synthesizes_method(self):
        """单条 PERFORM PARA-X（X 为 paragraph、非 SECTION）→ 登记单单元 pending 方法、
        调用点 this.p_parax();（补出之前缺失的方法定义）。"""
        proc = [("S", "section", "S", []), ("PARA-X", "paragraph", "S", ["  MOVE 1 TO X"])]
        ctx = self._pctx(proc)
        out = "\n".join(self._prange(["PARA-X"], ctx))
        self.assertIn("this.p_parax();", out)
        self.assertEqual(ctx.pending_range_methods["p_parax"], [("PARA-X", ["  MOVE 1 TO X"])])

    def test_perform_single_section_unchanged(self):
        """单条 PERFORM SOME-SEC（已知 SECTION）→ 真实方法已在，不登记 pending（零回归）。"""
        proc = [("SOME-SEC", "section", "SOME-SEC", [])]
        ctx = self._pctx(proc, section_order=["SOME-SEC"])
        out = "\n".join(self._prange(["SOME-SEC"], ctx))
        self.assertIn("this.p_somesec();", out)
        self.assertEqual(ctx.pending_range_methods, {})

    def test_perform_single_unknown_conservative(self):
        """单条 PERFORM NOPE（proc_order 无、非 SECTION）→ 维持 this.pNope() + 可见 TODO，不登记、不臆造。"""
        proc = [("PARA-X", "paragraph", "S", ["  A"])]
        ctx = self._pctx(proc)
        out = "\n".join(self._prange(["NOPE"], ctx))
        self.assertIn("this.p_nope();", out)
        self.assertIn("TODO", out)
        self.assertEqual(ctx.pending_range_methods, {})

    def test_perform_single_paragraph_idempotent(self):
        """同 paragraph 多次单条 PERFORM → 只合成一次（幂等）。"""
        proc = [("PARA-X", "paragraph", "S", ["  A"])]
        ctx = self._pctx(proc)
        self._prange(["PARA-X"], ctx)
        self._prange(["PARA-X"], ctx)
        self.assertEqual(len(ctx.pending_range_methods), 1)


# ══════════════════════════════════════════════════════════════════════════════
# 步骤14：THRU 区间内 GO TO 交互。合成区间方法保留标签后，区间内 GO TO 经 build_section
#         状态机精确路由（回跳→循环 / 前向→跳转 / 出口→return / 区间外→保守 TODO）。
# ══════════════════════════════════════════════════════════════════════════════
class TestThruRangeGoto(unittest.TestCase):
    def _ctx(self, proc_order):
        import translator.rules as r
        return r.Ctx(field_type_map={}, section_to_method=lambda s: "p_" + s.replace("-", "").lower(),
                     known_sections=set(), section_order=[], proc_order=list(proc_order))

    def _render(self, proc_order, a, b):
        """登记 A THRU B 区间方法 → drain 渲染，返回该合成方法的 Java 体字符串。"""
        import translator.rules as r
        from translator.skeleton_gen.body_context import render_pending_range_methods
        ctx = self._ctx(proc_order)
        r._perform_range([a, "THRU", b], [a.upper(), "THRU", b.upper()], a.upper(), ctx, 0)
        rendered = render_pending_range_methods(ctx, ws_field_names=[], call_args="", known_methods=set())
        return "\n".join(rendered.values())

    def test_thru_goto_back_edge_loop(self):
        """命门：区间内回跳 GO TO（PARA-B → PARA-A）→ 合成方法体出 __pc 状态机，循环不被打断。"""
        proc = [("PARA-A", "paragraph", "S", ["       MOVE 1 TO WS-X."]),
                ("PARA-B", "paragraph", "S", ["       GO TO PARA-A."])]
        body = self._render(proc, "PARA-A", "PARA-B")
        self.assertIn("switch (__pc)", body)
        self.assertIn('__pc = "PARA-A"; continue FLOW;', body)

    def test_thru_goto_forward_intra_state_machine(self):
        """D14-3 方案 a：区间内前向 GO TO（PARA-A → PARA-C，无回跳）→ 仍建状态机精确跳转，
        跳过中间 PARA-B，不再误退/挂 TODO。"""
        proc = [("PARA-A", "paragraph", "S", ["       GO TO PARA-C."]),
                ("PARA-B", "paragraph", "S", ["       MOVE 9 TO WS-Y."]),
                ("PARA-C", "paragraph", "S", ["       MOVE 3 TO WS-Z."])]
        body = self._render(proc, "PARA-A", "PARA-C")
        self.assertIn("switch (__pc)", body)
        self.assertIn('__pc = "PARA-C"; continue FLOW;', body)

    def test_thru_goto_out_of_range_todo(self):
        """D14-4 保守：区间内 GO TO 跳到区间外段（OTHER-SEC）→ 保守 // TODO-GOTO，不臆测落点。"""
        proc = [("PARA-A", "paragraph", "S", ["       GO TO OTHER-SEC."]),
                ("PARA-B", "paragraph", "S", ["       MOVE 1 TO WS-X."])]
        body = self._render(proc, "PARA-A", "PARA-B")
        self.assertIn("TODO-GOTO", body)
        self.assertNotIn('__pc = "OTHER-SEC"', body)

    def test_thru_no_goto_unchanged(self):
        """区间无 GO TO → 扁平拼接，无状态机（零回归，与步骤13 一致）。"""
        proc = [("PARA-A", "paragraph", "S", ["       MOVE 1 TO WS-X."]),
                ("PARA-B", "paragraph", "S", ["       MOVE 2 TO WS-Y."])]
        body = self._render(proc, "PARA-A", "PARA-B")
        self.assertNotIn("switch (__pc)", body)

    def test_perform_single_paragraph_renders_method(self):
        """步骤15：单条 PERFORM PARA-X 登记的单段方法经 drain 渲染，方法体含该 paragraph 译文。"""
        import translator.rules as r
        from translator.skeleton_gen.body_context import render_pending_range_methods
        proc = [("S", "section", "S", []),
                ("PARA-X", "paragraph", "S", ["       MOVE 7 TO WS-X."])]
        ctx = self._ctx(proc)
        r._perform_range(["PARA-X"], ["PARA-X"], "PARA-X", ctx, 0)
        rendered = render_pending_range_methods(ctx, ws_field_names=[], call_args="", known_methods=set())
        self.assertIn("p_parax", rendered)
        self.assertIn("7", rendered["p_parax"])


# ══════════════════════════════════════════════════════════════════════════════
# 步骤16：PERFORM 循环复杂变体。WITH TEST AFTER → do-while；VARYING…AFTER → 嵌套 for；
#         任一子句兜不住 → 整条落 LLM 叶子（all-or-nothing）。
# ══════════════════════════════════════════════════════════════════════════════
class TestPerformLoop(unittest.TestCase):
    def _ctx(self, ftm=None):
        import translator.rules as r
        return r.Ctx(field_type_map=ftm or {}, section_to_method=lambda s: "p_" + s.replace("-", "").lower(),
                     known_sections=set())

    def _perform(self, header_str, ctx, body=("MOVE", "1", "TO", "WSAA-X")):
        import translator.rules as r
        from translator.segmenter import Stmt
        st = Stmt(kind="perform", tokens=header_str.split(),
                  children=[Stmt(kind="simple", tokens=list(body), raw=" ".join(body))])
        return "\n".join(r._sk_perform(st, ctx, 0))

    def test_until_test_after_do_while(self):
        """WITH TEST AFTER UNTIL cond → do { … } while (!(cond));（先执行一次再判，do-while）。"""
        ctx = self._ctx({"wsaaDone": {"type": "String"}})
        out = self._perform("WITH TEST AFTER UNTIL WSAA-DONE = 'Y'", ctx)
        self.assertIn("do {", out)
        self.assertRegex(out, r"\}\s*while\s*\(!\(")

    def test_until_test_before_unchanged(self):
        """普通 UNTIL（默认 TEST BEFORE）→ while (!(cond))（零回归，无 do）。"""
        ctx = self._ctx({"wsaaDone": {"type": "String"}})
        out = self._perform("UNTIL WSAA-DONE = 'Y'", ctx)
        self.assertIn("while (!(", out)
        self.assertNotIn("do {", out)

    def test_varying_after_nested(self):
        """VARYING i … UNTIL ci AFTER j … UNTIL cj → 外 for(i) 内 for(j) 双层嵌套。"""
        ctx = self._ctx({"wsaaI": {"type": "int"}, "wsaaJ": {"type": "int"}})
        out = self._perform("VARYING WSAA-I FROM 1 BY 1 UNTIL WSAA-I > 10 "
                            "AFTER WSAA-J FROM 1 BY 1 UNTIL WSAA-J > 5", ctx)
        self.assertEqual(out.count("for ("), 2)
        # 外层 i 在内层 j 之前（嵌套顺序）
        self.assertLess(out.index("wsaaI = 1"), out.index("wsaaJ = 1"))

    def test_varying_single_unchanged(self):
        """单层 VARYING（无 AFTER）→ 单 for(...)（零回归）。"""
        ctx = self._ctx({"wsaaI": {"type": "int"}})
        out = self._perform("VARYING WSAA-I FROM 1 BY 1 UNTIL WSAA-I > 10", ctx)
        self.assertEqual(out.count("for ("), 1)

    def test_varying_after_unparsable_falls_to_llm(self):
        """某层条件兜不住（88 条件名无关系符）→ 整条落 LLM 叶子，不出半个循环（D16-3）。"""
        ctx = self._ctx({"wsaaI": {"type": "int"}})
        out = self._perform("VARYING WSAA-I FROM 1 BY 1 UNTIL END-OF-FILE", ctx)
        self.assertNotIn("for (", out)

    def test_varying_test_after_conservative(self):
        """VARYING + WITH TEST AFTER（叠加，语义复杂）→ 保守落 LLM，不臆造（D16-1）。"""
        ctx = self._ctx({"wsaaI": {"type": "int"}})
        out = self._perform("WITH TEST AFTER VARYING WSAA-I FROM 1 BY 1 UNTIL WSAA-I > 10", ctx)
        self.assertNotIn("for (", out)
        self.assertNotIn("do {", out)


# ══════════════════════════════════════════════════════════════════════════════
# 3b. IO 调用固化：_t_call（CALL 'xxxIO'）+ 结构体拷贝/重置（_assign）
#     固化 IO 查询，把 BEGN/READR/NEXTR/UPDAT 从 LLM 收回确定性规则。
# ══════════════════════════════════════════════════════════════════════════════
class TestIoCallAndStructAssign(unittest.TestCase):
    def setUp(self):
        from translator import rules as _rules
        self.rules = _rules
        self.Stmt = _rules.Stmt

    def _ctx(self, **kw):
        base = dict(
            field_type_map={},
            section_to_method=lambda s: s,
            known_sections=set(),
            io_struct_prefixes={"ELPO", "SYSR"},
            io_programs={
                "ELPOIO": {
                    "field_name": "elpoRepository",
                    "param_struct": "ELPO-PARAMS",
                    "operations": {"READR": "findByKey({key})", "NEXTR": "findNext({key})"},
                }
            },
        )
        base.update(kw)
        return self.rules.Ctx(**base)

    def _leaf(self, src: str):
        return self.Stmt(kind="simple", tokens=src.split(), raw=src)

    def test_io_call_static_readr(self):
        """功能码已知（READR）→ 直出 findByKey，参数对象进出。"""
        ctx = self._ctx()
        ctx.struct_function["ELPO"] = "READR"
        lines, matched = self.rules.translate_leaf(
            self._leaf("CALL 'ELPOIO' USING ELPO-PARAMS"), ctx)
        self.assertTrue(matched)
        self.assertEqual(lines, ["elpoParams = elpoRepository.findByKey(elpoParams);"])

    def test_io_call_no_func_falls_to_llm(self):
        """决策 D（步骤10）：功能码恒为 CALL 前显性字面量，原 execute() 运行时分发是死代码已移除。
        叶子级散点 CALL 若功能码不在 operations（游标/未知）→ matched=False，交 LLM。"""
        ctx = self._ctx()  # struct_function 为空
        lines, matched = self.rules.translate_leaf(
            self._leaf("CALL 'ELPOIO' USING ELPO-PARAMS"), ctx)
        self.assertFalse(matched)

    def test_io_call_unmapped_falls_to_llm(self):
        """未映射的 IO 子程序 → matched=False，交 LLM。"""
        ctx = self._ctx()
        lines, matched = self.rules.translate_leaf(
            self._leaf("CALL 'FOOIO' USING FOO-PARAMS"), ctx)
        self.assertFalse(matched)

    def test_function_code_tracked_by_move(self):
        """MOVE READR TO ELPO-FUNCTION 应在 ctx.struct_function 登记功能码。"""
        ctx = self._ctx()
        self.rules.translate_leaf(self._leaf("MOVE READR TO ELPO-FUNCTION"), ctx)
        self.assertEqual(ctx.struct_function.get("ELPO"), "READR")

    def test_move_struct_to_struct_is_copy(self):
        """决策 C（步骤10）：MOVE xxx-PARAMS TO yyy-PARAMS → 同名字段互拷，
        以 BeanUtils.copyProperties 实现（名字对不上的自动忽略，无需拷贝簿字段表）；
        不再退化成引用别名 sysrParams = elpoParams（§2 违规#6，编译不过）。"""
        ctx = self._ctx()
        lines, matched = self.rules.translate_leaf(
            self._leaf("MOVE ELPO-PARAMS TO SYSR-PARAMS"), ctx)
        self.assertTrue(matched)
        self.assertEqual(lines, ["BeanUtils.copyProperties(elpoParams, sysrParams);"])

    def test_move_spaces_to_struct_is_reset(self):
        """MOVE SPACES→结构体 仍是 new 重置。"""
        ctx = self._ctx()
        lines, matched = self.rules.translate_leaf(
            self._leaf("MOVE SPACES TO ELPO-PARAMS"), ctx)
        self.assertTrue(matched)
        self.assertEqual(lines, ["elpoParams = new ElpoParams();"])

    def test_end_to_end_section_no_llm(self):
        """1500-READ-ELPO 整段经 build_section + 规则填叶子，不产生 LLM 待译项。"""
        from translator.segmenter import segment, split_paragraphs
        # 拷贝簿序号列已被 parser 剥离：Area A 标签在行首（无缩进），语句缩进。
        sec_lines = [
            "1510-START.",
            "           MOVE SPACES                 TO ELPO-PARAMS.",
            "           MOVE LETCMNT-RDOCNUM        TO ELPO-CHDRNUM.",
            "           MOVE READR                  TO ELPO-FUNCTION.",
            "           CALL 'ELPOIO'           USING  ELPO-PARAMS.",
            "1590-EXIT.",
            "           EXIT.",
        ]
        ctx = self._ctx(io_struct_prefixes={"ELPO", "SYSR", "LETCMNT"})
        paras = [(lbl, segment(body)) for lbl, body in split_paragraphs(sec_lines)]
        skel = "\n".join(self.rules.build_section(paras, ctx))
        # 逐叶子用规则翻译，断言全部命中（无一交 LLM）
        unmatched = []
        for lid, leaf in ctx.leaves:
            _lines, matched = self.rules.translate_leaf(leaf, ctx)
            if not matched:
                unmatched.append(leaf.raw or " ".join(leaf.tokens))
        self.assertEqual(unmatched, [], f"以下叶子未被固化、会交 LLM: {unmatched}")

    # ── 步骤10：单条读 READR 结构化吸收（setup+CALL+IF STATUZ → findBy…Readr + null 检查）──
    def _readr_ctx(self, **kw):
        """带完整 io_default_pattern（READR 模板含 findBy → 识别为单条读）的 ctx；
        清空 io_programs，让被测表走范式派生（field_name=<base>Repository，finder 按键派生）。"""
        return self._ctx(
            io_programs={},
            io_default_pattern={
                "class_suffix": "Repository", "field_suffix": "Repository",
                "param_struct_suffix": "-PARAMS", "import_package": "com.example.repository",
                "operations": {"READR": "findByKeyReadr({key})", "UPDAT": "save({entity})"}},
            **kw)

    def _build(self, ctx, sec_lines):
        from translator.segmenter import segment, split_paragraphs
        paras = [(lbl, segment(body)) for lbl, body in split_paragraphs(sec_lines)]
        return "\n".join(self.rules.build_section(paras, ctx))

    def test_readr_single_absorbed_ok_form(self):
        """READR + IF STATUZ = O-K → `Rec r = repo.findBy…Readr(键); if (r != null) {…}`，
        FUNCTION/FORMAT/SPACES/STATUZ 全吸收（§2 的 6 项违规清零）。"""
        ctx = self._readr_ctx(
            io_struct_prefixes={"ELPO"},
            field_type_map={n: {"type": "String"} for n in
                            ("wsaaCompany", "wsaaLanguage", "wsaaData")})
        skel = self._build(ctx, [
            "1510-START.",
            "           MOVE SPACES         TO ELPO-PARAMS.",
            "           MOVE WSAA-COMPANY   TO ELPO-CHDRCOY.",
            "           MOVE WSAA-LANGUAGE  TO ELPO-CHDRNUM.",
            "           MOVE ELPOREC        TO ELPO-FORMAT.",
            "           MOVE READR          TO ELPO-FUNCTION.",
            "           CALL 'ELPOIO'   USING ELPO-PARAMS.",
            "           IF ELPO-STATUZ = O-K",
            "              MOVE ELPO-DATA TO WSAA-DATA",
            "           END-IF.",
            "1590-EXIT.",
            "           EXIT.",
        ])
        self.assertIn(
            "ElpoRecord elpo = elpoRepository.findByChdrcoyAndChdrnumReadr("
            "wsaaCompany, wsaaLanguage);", skel)
        self.assertIn("if (elpo != null) {", skel)
        for leak in ("setFunction", "setFormat", "new ElpoParams", "getStatuz",
                     ".execute(", "findByKey(elpoParams"):
            self.assertNotIn(leak, skel, f"残留泄漏: {leak}\n{skel}")
        # 叶子全部命中 + 体内 ELPO-DATA 重绑定到 record
        body = [self.rules.translate_leaf(lf, ctx)[0]
                for _i, lf in ctx.leaves if lf.tokens and lf.tokens[0].upper() == "MOVE"]
        self.assertIn(["wsaaData = elpo.getData();"], body)

    def test_readr_single_absorbed_error_form(self):
        """决策 A：IF STATUZ NOT=O-K AND NOT=ENDP（PERFORM 580）→ try{finder+后续} catch{580}。"""
        ctx = self._readr_ctx(
            io_struct_prefixes={"ITDM"},
            known_sections={"580-DB-ERROR"},
            section_to_method=lambda s: "dbError580",
            field_type_map={n: {"type": "String"} for n in ("wsaaItem", "wsaaValue")})
        skel = self._build(ctx, [
            "2000-READ.",
            "           MOVE SPACES   TO ITDM-PARAMS.",
            "           MOVE WSAA-ITEM TO ITDM-ITEMKEY.",
            "           MOVE READR    TO ITDM-FUNCTION.",
            "           CALL 'ITDMIO' USING ITDM-PARAMS.",
            "           IF ITDM-STATUZ NOT = O-K AND ITDM-STATUZ NOT = ENDP",
            "              PERFORM 580-DB-ERROR",
            "           END-IF.",
            "           MOVE ITDM-VALUE TO WSAA-VALUE.",
            "2090-EXIT.",
            "           EXIT.",
        ])
        self.assertIn("try {", skel)
        self.assertIn("ItdmRecord itdm = itdmRepository.findByItemkeyReadr(wsaaItem);", skel)
        self.assertIn("} catch (Exception e) {", skel)
        self.assertNotIn("getStatuz", skel)
        # try 体内 ITDM-VALUE 重绑定到 record
        body = [self.rules.translate_leaf(lf, ctx)[0]
                for _i, lf in ctx.leaves if lf.tokens and lf.tokens[0].upper() == "MOVE"]
        self.assertIn(["wsaaValue = itdm.getValue();"], body)

    # ── 步骤11：单条写 IO（UPDAT/WRITE/DELET）结构化吸收 ──────────────────────
    def _write_ctx(self, **kw):
        """带写功能码（save/delete）的 io_default_pattern；io_programs 空走范式派生。"""
        return self._ctx(
            io_programs={},
            io_default_pattern={
                "class_suffix": "Repository", "field_suffix": "Repository",
                "param_struct_suffix": "-PARAMS", "import_package": "com.example.repository",
                "operations": {"READR": "findByKeyReadr({key})", "UPDAT": "save({entity})",
                               "WRITR": "save({entity})", "DELET": "delete({entity})"}},
            **kw)

    def test_write_single_updat_reuse_try_catch(self):
        """UPDAT（无 MOVE SPACES → 复用上文实体）+ IF STATUZ NOT=O-K（PERFORM 9999）
        → x.setField(...); try{ repo.save(x); } catch{ 错误段(); }。对照 knowledge §186。"""
        ctx = self._write_ctx(
            io_struct_prefixes={"TMLCLST"},
            known_sections={"9999-FATAL-ERROR"},
            section_to_method=lambda s: "fatalError9999",
            field_type_map={"wsaaNewValue": {"type": "String"}})
        skel = self._build(ctx, [
            "5000-UPDATE.",
            "           MOVE WSAA-NEW-VALUE TO TMLCLST-FIELD.",
            "           MOVE UPDAT          TO TMLCLST-FUNCTION.",
            "           CALL 'TMLCLSTIO' USING TMLCLST-PARAMS.",
            "           IF TMLCLST-STATUZ NOT = O-K",
            "              PERFORM 9999-FATAL-ERROR",
            "           END-IF.",
            "5090-EXIT.",
            "           EXIT.",
        ])
        self.assertIn("try {", skel)
        self.assertIn("tmlclstRepository.save(tmlclst);", skel)
        self.assertIn("} catch (Exception e) {", skel)
        self.assertIn("fatalError9999();", skel)
        for leak in ("getStatuz", "new TmlclstParams", "setFunction",
                     "= tmlclstRepository.save", "TmlclstRecord tmlclst = new"):
            self.assertNotIn(leak, skel, f"残留泄漏: {leak}\n{skel}")
        # setter 以叶子占位进入，translate_leaf 时经 rebind 标注 → 实体 setter（非 Params）
        body = [self.rules.translate_leaf(lf, ctx)[0]
                for _i, lf in ctx.leaves if lf.tokens and lf.tokens[0].upper() == "MOVE"]
        self.assertIn(["tmlclst.setField(wsaaNewValue);"], body)

    def test_write_single_write_new_entity(self):
        """WRITR（含 MOVE SPACES TO pfx-PARAMS → 插入）无 IF
        → XxxRecord x = new XxxRecord(); x.setField(...); repo.save(x);。
        （功能码用 WRITR：真实 LIFE 系统的写码为 5 字缩写，避开 COBOL 动词 WRITE 与切分器撞名）"""
        ctx = self._write_ctx(
            io_struct_prefixes={"TMLCLST"},
            field_type_map={"wsaaVal": {"type": "String"}})
        skel = self._build(ctx, [
            "6000-INSERT.",
            "           MOVE SPACES   TO TMLCLST-PARAMS.",
            "           MOVE WSAA-VAL TO TMLCLST-FIELD.",
            "           MOVE WRITR    TO TMLCLST-FUNCTION.",
            "           CALL 'TMLCLSTIO' USING TMLCLST-PARAMS.",
            "6090-EXIT.",
            "           EXIT.",
        ])
        self.assertIn("TmlclstRecord tmlclst = new TmlclstRecord();", skel)
        self.assertIn("tmlclstRepository.save(tmlclst);", skel)
        for leak in ("getStatuz", "new TmlclstParams", "setFunction",
                     "= tmlclstRepository.save"):
            self.assertNotIn(leak, skel, f"残留泄漏: {leak}\n{skel}")
        # setter 以叶子占位进入 → 实体 setter（rebind 标注）
        body = [self.rules.translate_leaf(lf, ctx)[0]
                for _i, lf in ctx.leaves if lf.tokens and lf.tokens[0].upper() == "MOVE"
                and "TMLCLST-FIELD" in [t.upper() for t in lf.tokens]]
        self.assertIn(["tmlclst.setField(wsaaVal);"], body)

    def test_write_single_delet(self):
        """DELET（决策 W-4 选项①）→ repo.delete(实体)，不出 deleteByKey。"""
        ctx = self._write_ctx(io_struct_prefixes={"TMLCLST"})
        skel = self._build(ctx, [
            "7000-DELETE.",
            "           MOVE DELET TO TMLCLST-FUNCTION.",
            "           CALL 'TMLCLSTIO' USING TMLCLST-PARAMS.",
            "7090-EXIT.",
            "           EXIT.",
        ])
        self.assertIn("tmlclstRepository.delete(tmlclst);", skel)
        self.assertNotIn("deleteByKey", skel)


# ══════════════════════════════════════════════════════════════════════════════
# 3b. 有符号 DISPLAY 存储串保符号（步骤12 §1，overpunch-on-negative）
#     Bug：旧实现 _toDigits 无条件 .abs()，负金额经 REDEFINES/组切片 round-trip 后静默变正。
# ══════════════════════════════════════════════════════════════════════════════
class TestSignedOverpunch(unittest.TestCase):
    _OVP = "}JKLMNOPQR"  # 须与 storage.NUM_HELPER 的 _OVP 一致

    def _to_digits(self, val: int, n: int) -> str:
        """镜像 Java _toDigits（scale=0 整数）：保符号 overpunch 编码。"""
        neg = val < 0
        s = str(abs(val))
        if len(s) > n:
            s = s[len(s) - n:]
        s = s.rjust(n, "0")
        if neg and s:
            s = s[:-1] + self._OVP[int(s[-1])]
        return s

    def _de_overpunch(self, s: str) -> int:
        """镜像 Java _deOverpunch + parse：解码 overpunch 还原带符号整数。"""
        idx = self._OVP.find(s[-1])
        if idx >= 0:
            return -int(s[:-1] + str(idx))
        return int(s)

    def test_negative_round_trip(self):
        """负值经 _toDigits → _deOverpunch 必须原样还原（含符号），正值不受影响。"""
        for v, n in [(-123, 5), (-1, 3), (-456, 3), (0, 4), (789, 4), (-7, 1)]:
            enc = self._to_digits(v, n)
            self.assertEqual(len(enc), n, f"宽度变了：{v}->{enc}")
            self.assertEqual(self._de_overpunch(enc), v, f"round-trip 丢符号：{v}->{enc}")

    def test_positive_unchanged_no_overpunch(self):
        """正/无符号值保持纯数字串（零回归）。"""
        self.assertEqual(self._to_digits(123, 5), "00123")
        self.assertTrue(self._to_digits(123, 5).isdigit())

    def test_helper_emits_overpunch_not_bare_abs(self):
        """生成的 Java helper 必含 overpunch 逻辑，且不再无条件 abs。"""
        from translator.wsaa.storage import NUM_HELPER, num_from_digits
        joined = "\n".join(NUM_HELPER)
        self.assertIn("_OVP", joined)
        self.assertIn("_deOverpunch", joined)
        self.assertIn("v.signum() < 0", joined)
        # int/long 解析须经 overpunch 解码
        self.assertIn("_deOverpunch", num_from_digits("seg", "long", 0))
        self.assertIn("_deOverpunch", num_from_digits("seg", "int", 0))


# ══════════════════════════════════════════════════════════════════════════════
# 3c. 命名碰撞：撞名字段改名保留，不静默丢（步骤12 §4）
# ══════════════════════════════════════════════════════════════════════════════
class TestNameCollision(unittest.TestCase):
    def test_disambiguate_parent_prefix(self):
        """父组名前缀消歧，且兜底序号保证唯一。"""
        from translator.wsaa.render_class import _disambiguate
        self.assertEqual(_disambiguate("wsaaX", "wsaaGroupA", {"wsaaX"}), "wsaaGroupAWsaaX")
        # 父前缀仍冲突 → 序号兜底
        self.assertEqual(_disambiguate("wsaaX", "wsaaG", {"wsaaX", "wsaaGWsaaX"}), "wsaaX_2")
        # 无父组名 → jn_2
        self.assertEqual(_disambiguate("wsaaX", "", {"wsaaX"}), "wsaaX_2")

    def test_collision_renamed_not_dropped(self):
        """两个不同父组下的同名叶子：第二个改名保留 + TODO，字段不丢。"""
        from parser.ws.model import WsNode
        from translator.wsaa.render_class import render_wsaa

        def leaf(name):
            return WsNode(level=3, name=name, pic="X(04)", raw=f"03 {name} PIC X(04).")

        def grp(name, child):
            g = WsNode(level=1, name=name, pic="", raw=f"01 {name}.")
            g.children = [child]
            return g
        roots = [grp("WSAA-GROUP-A", leaf("WSAA-DUP")), grp("WSAA-GROUP-B", leaf("WSAA-DUP"))]
        src = render_wsaa(roots, "ZTEST")
        self.assertIn("wsaaDup", src)                 # 首个保基名
        self.assertIn("命名碰撞", src)                 # 第二个标 TODO
        self.assertNotIn("重复名跳过", src)            # 旧的静默丢行为已移除
        self.assertEqual(src.count("private String wsaaDup ="), 1)  # 基名只一份
        # 第二个字段确实声明了（改名后），不是被吞掉
        self.assertIn("wsaaGroupBWsaaDup", src)


# ══════════════════════════════════════════════════════════════════════════════
# 4. 本地模型：连通性 + 翻译能力（vLLM 离线则 skip）
# ══════════════════════════════════════════════════════════════════════════════
@unittest.skipUnless(_llm_available(), f"本地 vLLM ({LLM_BASE_URL}) 不可用，跳过模型测试")
class TestLocalModel(unittest.TestCase):
    SECTION = """\
       1000-INIT SECTION.
       1000.
           MOVE SPACES        TO WSAA-STATUZ.
           MOVE 0             TO WSAA-SEQ.
           MOVE "O-K"         TO WSAA-STATUZ.
           PERFORM 2000-VALIDATE THRU 2000-EXIT.
           IF WSAA-STATUZ NOT = "O-K"
               GO TO 1000-EXIT
           END-IF.
           MOVE WSAA-CHDRNUM  TO CHDR-CHDRNUM.
       1000-EXIT.
           EXIT."""

    def test_model_listed(self):
        import requests
        data = requests.get(f"{LLM_BASE_URL}/v1/models", timeout=5).json()["data"]
        self.assertTrue(data)
        self.assertTrue(data[0]["id"])

    def test_translate_section_produces_java(self):
        """完整跑一遍 translate_section_node，断言关键翻译规则被遵守。"""
        from graph.nodes import translate_section_node
        from translator.skeleton import _section_to_method

        state = {
            "current_section": {
                "name": "1000-INIT",
                "lines": self.SECTION.splitlines(),
                "line_start": 1,
                "line_end": 12,
                "performs": ["2000-VALIDATE"],
                "calls": [],
                "go_tos": ["1000-EXIT"],
            },
            "variable_context": (
                "WSAA-STATUZ → wsaaStatuz [String]\n"
                "WSAA-SEQ → wsaaSeq [int]\n"
                "WSAA-CHDRNUM → wsaaChdrnum [String]\n"
                "CHDR-CHDRNUM → chdrChdrnum [String]"
            ),
        }
        result = translate_section_node(state)
        body = result["translated_sections"][_section_to_method("1000-INIT")]
        print("\n--- 模型翻译输出 ---\n" + body + "\n--------------------")

        # 不应是翻译失败的兜底文本
        self.assertNotIn("翻译失败", body)
        self.assertNotIn("throw new RuntimeException(\"未翻译", body)
        # MOVE SPACES TO WSAA-STATUZ → wsaaStatuz = "";
        self.assertIn("wsaaStatuz", body)
        # 应包含赋值（= ）语句
        self.assertIn("=", body)


class TestProcStartCommentImmune(unittest.TestCase):
    """步骤14 §1 / 架构演进初步设计 §7：proc_start 定位须跳过注释行，
    注释里的 "PROCEDURE DIVISION" 字样不得误判 → 数据段不应被当过程段。"""

    def _parse_src(self, src: str):
        import tempfile, os
        from parser.cobol_parser import parse
        fd, path = tempfile.mkstemp(suffix=".cob")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(src)
            return parse(path)
        finally:
            os.unlink(path)

    def test_comment_procedure_division_not_misdetected(self):
        # 第7列 '*' 的注释行含 "procedure division" 字样，真正 PROCEDURE DIVISION 在其后。
        src = (
            "       IDENTIFICATION DIVISION.\n"
            "       PROGRAM-ID. TPROG.\n"
            "      *   The basic procedure division logic reads records.\n"
            "       DATA DIVISION.\n"
            "       WORKING-STORAGE SECTION.\n"
            "       01 WSAA-PROG PIC X(07) VALUE 'TPROG'.\n"
            "       PROCEDURE DIVISION.\n"
            "       1000-MAIN SECTION.\n"
            "           MOVE 1 TO WSAA-PROG.\n"
        )
        prog = self._parse_src(src)
        names = {s.name.upper() for s in prog.sections}
        # 数据/环境段不得混入过程段
        self.assertNotIn("WORKING-STORAGE", names)
        self.assertNotIn("FILE", names)
        # 真过程段须在
        self.assertIn("1000-MAIN", names)


class TestDialectNormalize(unittest.TestCase):
    """步骤16：相1 方言归一（规则源自 config dialect_normalization，preprocess.dialect 应用）。
    本 shop 省 TO 的 GO 段名 → 标准 GO TO；GOBACK/已是 GO TO 不动；引号内文本不动。"""

    def test_go_without_to_normalized(self):
        from preprocess import dialect
        self.assertEqual(dialect.normalize("GO 2060-RECEIPT"), "GO TO 2060-RECEIPT")

    def test_go_to_idempotent(self):
        from preprocess import dialect
        self.assertEqual(dialect.normalize("GO TO 3190-EXIT"), "GO TO 3190-EXIT")

    def test_goback_untouched(self):
        from preprocess import dialect
        self.assertEqual(dialect.normalize("GOBACK"), "GOBACK")

    def test_quoted_go_protected(self):
        from preprocess import dialect
        self.assertEqual(dialect.normalize("MOVE 'GO HOME' TO WS-X"), "MOVE 'GO HOME' TO WS-X")


# ══════════════════════════════════════════════════════════════════════════════
# 步骤17：相2 自研轻量 ASG（旁路并存）。验收四项（设计 §5）——
#   ① build_asg 跑通、Program 节点树非空、SECTION 数与 parse 一致；
#   ② GO TO 解析：GotoStmt 目标解析到真实过程单元；
#   ③ PERFORM THRU 区间：resolve_thru 取 [A..B] 闭区间；
#   ④ 单点 visitor 自证：GotoJavaVisitor 输出 == rules._sk_control 对同一 GO 的 Java（逐字符）。
# 旁路不接旧路径，旧用例/快照零 diff 由旧代码未动天然成立（此处只自证新通路）。
# ══════════════════════════════════════════════════════════════════════════════
class TestAsgBuild(unittest.TestCase):
    """① 结构提升 + ② 引用解析：build_asg 在内联程序上跑通，GO TO 解析到真实单元。"""

    # 内联最小程序：两个 SECTION + EXIT paragraph + 一条 GO TO（仿 TestProcStartCommentImmune 列布局）。
    SRC = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. TASG.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 WSAA-X PIC X(04) VALUE 'A'.\n"
        "       PROCEDURE DIVISION.\n"
        "       1000-MAIN SECTION.\n"
        "           MOVE 1 TO WSAA-X.\n"
        "           GO TO 1000-EXIT.\n"
        "       1000-EXIT.\n"
        "           EXIT.\n"
        "       2000-NEXT SECTION.\n"
        "           MOVE 2 TO WSAA-X.\n"
    )

    def _parse(self, src: str):
        import tempfile, os
        from parser.cobol_parser import parse
        fd, path = tempfile.mkstemp(suffix=".cob")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(src)
            return parse(path)
        finally:
            os.unlink(path)

    def _collect_gotos(self, program):
        from asg import AsgVisitor
        found = []

        class _C(AsgVisitor):
            def visit_GotoStmt(self, node):
                found.append(node)
        _C().visit(program)
        return found

    def test_build_runs_and_sections_match_parse(self):
        """① build_asg 跑通，program_id 一致、SECTION 数与 parse 一致、节点树非空。"""
        from asg import build_asg, Program, Section
        prog = self._parse(self.SRC)
        asg = build_asg(prog)
        self.assertIsInstance(asg, Program)
        self.assertEqual(asg.program_id, prog.program_id)
        self.assertEqual(len(asg.sections), len(prog.sections))   # SECTION 数一致
        self.assertTrue(all(isinstance(s, Section) for s in asg.sections))
        # 节点树非空：至少有 paragraph 且有语句被提升
        self.assertTrue(any(s.paragraphs for s in asg.sections))
        self.assertTrue(any(p.stmts for s in asg.sections for p in s.paragraphs))

    def test_registry_attached_to_root(self):
        """build_asg 把 ProcRegistry 挂在 Program 根（相3 查表用）。"""
        from asg import build_asg, ProcRegistry
        asg = build_asg(self._parse(self.SRC))
        self.assertIsInstance(asg.registry, ProcRegistry)
        # 注册表含 SECTION 与 paragraph 单元
        names = {u.name for u in asg.registry.units}
        self.assertIn("1000-MAIN", names)
        self.assertIn("1000-EXIT", names)

    def test_goto_target_resolved_to_unit(self):
        """② GO TO 1000-EXIT → GotoStmt.target.unit 解析到真实 paragraph 单元（非 None）。"""
        asg = self._import_build()(self._parse(self.SRC))
        gotos = self._collect_gotos(asg)
        self.assertTrue(gotos, "应至少提升出一条 GotoStmt")
        g = gotos[0]
        self.assertEqual(g.target.name, "1000-EXIT")
        self.assertIsNotNone(g.target.unit, "目标在程序内 → 应解析到真实单元")
        self.assertEqual(g.target.unit.name, "1000-EXIT")

    def _import_build(self):
        from asg import build_asg
        return build_asg


class TestAsgRegistryThru(unittest.TestCase):
    """③ PERFORM THRU 区间：resolve_thru 在合成单元上取 [A..B] 闭区间，不丢中间、保守退化。"""

    def _reg(self, names):
        from asg import ProcUnit, ProcRegistry
        units = [ProcUnit(name=n, kind="paragraph", section="S", order=i)
                 for i, n in enumerate(names)]
        return ProcRegistry(units)

    def test_resolve_thru_closed_interval(self):
        """A THRU B → 取 [A..B] 闭区间所有单元（含中间 M，按 order 序）。"""
        reg = self._reg(["A", "M", "B", "Z"])
        units = reg.resolve_thru("A", "B")
        self.assertEqual([u.name for u in units], ["A", "M", "B"])   # 中间 M 不丢，Z 不越界

    def test_resolve_thru_missing_b_degrades_single(self):
        """B 缺失/解析不到 → 退化为单元 [A]（保守，不臆测区间）。"""
        reg = self._reg(["A", "B"])
        self.assertEqual([u.name for u in reg.resolve_thru("A", None)], ["A"])
        self.assertEqual([u.name for u in reg.resolve_thru("A", "NOPE")], ["A"])

    def test_resolve_thru_b_before_a_degrades(self):
        """B 在 A 之前 → 退化为 [A]（不倒序取区间）。"""
        reg = self._reg(["B", "A"])
        self.assertEqual([u.name for u in reg.resolve_thru("A", "B")], ["A"])

    def test_resolve_thru_unknown_a_empty(self):
        """A 解析不到 → []（端点未知不臆测）。"""
        reg = self._reg(["X", "Y"])
        self.assertEqual(reg.resolve_thru("NOPE", "Y"), [])

    def test_resolve_case_insensitive(self):
        """按名解析大小写不敏感。"""
        reg = self._reg(["1000-MAIN"])
        self.assertIsNotNone(reg.resolve("1000-main").unit)


class TestAsgGotoVisitor(unittest.TestCase):
    """④ 单点 visitor 自证：GotoJavaVisitor 输出与 rules._sk_control 对同一 GO 逐字符一致。"""

    def _sk_control_goto(self, target: str):
        """非 dispatch（flow_label=None）、target 不在 known_sections 时 _sk_control 对 GO 的输出。"""
        import translator.rules as r
        from translator.segmenter import Stmt
        ctx = r.Ctx(field_type_map={}, section_to_method=lambda s: s, known_sections=set())
        st = Stmt(kind="simple", tokens=["GO", "TO", target], raw=f"GO TO {target}")
        return r._sk_control(st, ctx, 0)

    def _visitor_goto(self, target: str):
        # 步骤23：GotoJavaVisitor demo 退役，能力并入 LeafJavaVisitor.visit_GotoStmt（经 translate_control）
        from asg import GotoStmt, LeafJavaVisitor, ProcRef
        node = GotoStmt(target=ProcRef(name=target, unit=None), tokens=["GO", "TO", target])
        return LeafJavaVisitor(_leaf_ctx()).visit(node)

    def test_exit_target_char_exact(self):
        """目标 …EXIT → 两侧均 `return;  // GO TO X`，逐字符一致。"""
        self.assertEqual(self._visitor_goto("1000-EXIT"), self._sk_control_goto("1000-EXIT"))

    def test_unknown_target_char_exact(self):
        """未知段（非 EXIT、非 known_sections）→ 两侧均 [// TODO-GOTO…, return;]，逐字符一致。"""
        self.assertEqual(self._visitor_goto("9000-WHERE"), self._sk_control_goto("9000-WHERE"))

    def test_no_target_returns(self):
        """目标缺失（退化节点，无 token）→ return;（兜底，不臆测）。"""
        from asg import GotoStmt, LeafJavaVisitor
        self.assertEqual(LeafJavaVisitor(_leaf_ctx()).visit(GotoStmt(target=None)), ["return;"])


# ──────────────────────────────────────────────────────────────────────────────
# 步骤18 绞杀项3① MOVE 迁 visitor（抽公用 translate_move + ASG 提升/visit + 比对闸）
#   ① translate_move 抽出后输出正确（普通/figurative/数值/结构体/FUNCTION/PARAMS 互拷）
#   ② build_asg 把 MOVE 提升为 MoveStmt 且 tokens 与 segmenter 一致
#   ③ LeafJavaVisitor.visit(MoveStmt) == translate_move（同函数同 ctx，逐字符自证）
#   ④ diff_asg_vs_legacy 两路 MOVE 在整程序上逐字符一致
# 对应设计：docs/详细设计/步骤18-绞杀项3①MOVE迁visitor设计.md §7。
# ──────────────────────────────────────────────────────────────────────────────

def _leaf_ctx(field_type_map=None, prefixes=None, objects=None, classes=None):
    """构造满足 LeafCtx 的 rules.Ctx（叶子译器只读其判型/结构体命名字段）。"""
    import translator.rules as r
    return r.Ctx(
        field_type_map=field_type_map or {}, section_to_method=lambda s: s,
        known_sections=set(), io_struct_prefixes=prefixes or set(),
        struct_objects=objects or {}, struct_classes=classes or {},
    )


class TestLeafMoveExtract(unittest.TestCase):
    """① 抽出的 translate_move 输出正确（覆盖 MOVE 各形态）。"""

    FTM = {"wsaaName": {"type": "String"}, "wsaaCount": {"type": "int"},
           "wsaaAmt": {"type": "BigDecimal"}, "wsaaFlag": {"type": "String"}}

    def _mv(self, line, **kw):
        from translator.leaf import translate_move
        ctx = _leaf_ctx(field_type_map=self.FTM, **kw)
        toks = line.split()
        lines, ok = translate_move(toks, ctx)
        return lines, ok, ctx

    def test_figurative_blank_string(self):
        self.assertEqual(self._mv("MOVE SPACES TO WSAA-NAME")[0], ['wsaaName = "";'])

    def test_figurative_zero_int(self):
        self.assertEqual(self._mv("MOVE ZERO TO WSAA-COUNT")[0], ["wsaaCount = 0;"])

    def test_numeric_literal_to_bigdecimal(self):
        self.assertEqual(self._mv("MOVE 100 TO WSAA-AMT")[0], ['wsaaAmt = new BigDecimal("100");'])

    def test_literal_to_string(self):
        self.assertEqual(self._mv("MOVE 'Y' TO WSAA-FLAG")[0], ['wsaaFlag = "Y";'])

    def test_struct_field_setter(self):
        lines, ok, _ = self._mv("MOVE 'Y' TO PS01CHR-CHDRCOY",
                                prefixes={"PS01CHR"}, objects={"PS01CHR": "ps01chrParams"})
        self.assertTrue(ok)
        self.assertEqual(lines, ['ps01chrParams.setChdrcoy("Y");'])

    def test_function_move_records_no_line(self):
        """MOVE READR TO ELPO-FUNCTION → 不出行，仅记 struct_function（供 CALL 吸收）。"""
        lines, ok, ctx = self._mv("MOVE READR TO ELPO-FUNCTION", prefixes={"ELPO"})
        self.assertEqual(lines, [])
        self.assertEqual(ctx.struct_function.get("ELPO"), "READR")

    def test_params_copy_beanutils(self):
        lines, ok, _ = self._mv(
            "MOVE LETC-PARAMS TO PS01-PARAMS", prefixes={"LETC", "PS01"},
            objects={"LETC": "letcParams", "PS01": "ps01Params"})
        self.assertEqual(lines, ["BeanUtils.copyProperties(letcParams, ps01Params);"])


class TestAsgMoveLift(unittest.TestCase):
    """② build_asg 把 MOVE 提升为 MoveStmt，tokens 与 segmenter 切分一致。"""

    SRC = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. TMV.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 WSAA-X PIC 9(04) VALUE 0.\n"
        "       PROCEDURE DIVISION.\n"
        "       1000-MAIN SECTION.\n"
        "           MOVE 1 TO WSAA-X.\n"
    )

    def _parse(self, src):
        import tempfile, os
        from parser.cobol_parser import parse
        fd, path = tempfile.mkstemp(suffix=".cob")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(src)
            return parse(path)
        finally:
            os.unlink(path)

    def test_move_lifted_to_movestmt(self):
        from asg import build_asg, MoveStmt
        asg = build_asg(self._parse(self.SRC))
        moves = [st for s in asg.sections for p in s.paragraphs
                 for st in p.stmts if isinstance(st, MoveStmt)]
        self.assertTrue(moves, "MOVE 应提升为 MoveStmt（不再落 Leaf）")
        self.assertEqual([t.upper() for t in moves[0].tokens], ["MOVE", "1", "TO", "WSAA-X"])

    def test_move_not_leaf(self):
        from asg import build_asg, Leaf
        asg = build_asg(self._parse(self.SRC))
        leaves = [st for s in asg.sections for p in s.paragraphs
                  for st in p.stmts if isinstance(st, Leaf)
                  and st.tokens and st.tokens[0].upper() == "MOVE"]
        self.assertEqual(leaves, [], "MOVE 不应再落 Leaf 兜底")


class TestAsgMoveVisitor(unittest.TestCase):
    """③ LeafJavaVisitor.visit(MoveStmt) == translate_move（同函数同 ctx，逐字符自证）。"""

    def test_visitor_equals_translate_move(self):
        from asg import MoveStmt, LeafJavaVisitor
        from translator.leaf import translate_move
        ctx = _leaf_ctx(field_type_map={"wsaaCount": {"type": "int"}})
        toks = ["MOVE", "5", "TO", "WSAA-COUNT"]
        node = MoveStmt(tokens=list(toks))
        self.assertEqual(LeafJavaVisitor(ctx).visit(node), translate_move(toks, ctx)[0])


class TestDiffAsgVsLegacy(unittest.TestCase):
    """④ 整程序上旧/新两路 MOVE 逐字符一致（复用比对脚本的枚举/渲染逻辑）。"""

    SRC = TestAsgMoveLift.SRC + (
        "           MOVE WSAA-X TO WSAA-X.\n"
        "           IF WSAA-X = 1\n"
        "               MOVE 2 TO WSAA-X\n"
        "           END-IF.\n"
    )

    def _harness(self):
        import importlib.util, pathlib
        p = pathlib.Path(__file__).parent / "scripts" / "diff_asg_vs_legacy.py"
        spec = importlib.util.spec_from_file_location("diff_asg_vs_legacy", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_legacy_equals_asg(self):
        from translator.skeleton_gen.body_context import build_body_ctx
        mod = self._harness()
        prog = TestAsgMoveLift()._parse(self.SRC)
        ctx, _ = build_body_ctx(prog)
        legacy = mod._legacy_moves(prog, ctx)
        asg = mod._asg_moves(prog, ctx)
        self.assertEqual(len(legacy), len(asg))
        self.assertTrue(len(legacy) >= 3, "样例应含多条 MOVE（含 IF 内嵌套）")
        self.assertEqual([x[1] for x in legacy], [x[1] for x in asg])


# ──────────────────────────────────────────────────────────────────────────────
# 步骤19 绞杀项3② IF 迁 visitor（抽公用 translate_condition + visit_IfStmt + 比对闸扩 IF）
#   ① translate_condition 抽出后输出正确（数值/NOT/SPACES/BigDecimal/AND-OR/复杂→None）
#   ② visit_IfStmt 条件行 == rules._try_condition；cond=None→TODO-IF；body 直译已迁/占位未迁/嵌套递归
#   ③ diff_asg_vs_legacy --verb IF 两路条件串逐字符一致（含嵌套/AND-OR/NOT）
# 对应设计：docs/详细设计/步骤19-绞杀项3②IF迁visitor设计.md §7。
# ──────────────────────────────────────────────────────────────────────────────

class TestLeafCondExtract(unittest.TestCase):
    """① 抽出的 translate_condition 输出正确（覆盖条件各形态）。"""

    FTM = {"wsaaCount": {"type": "int"}, "wsaaAmt": {"type": "BigDecimal"},
           "wsaaName": {"type": "String"}}

    def _c(self, line):
        from translator.leaf import translate_condition
        ctx = _leaf_ctx(field_type_map=self.FTM)
        return translate_condition(line.split(), ctx)

    def test_numeric_eq(self):
        self.assertEqual(self._c("WSAA-COUNT = 1"), "wsaaCount == 1")

    def test_numeric_gt(self):
        self.assertEqual(self._c("WSAA-COUNT > 5"), "wsaaCount > 5")

    def test_not_numeric_eq_inverts(self):
        self.assertEqual(self._c("NOT WSAA-COUNT = 1"), "wsaaCount != 1")

    def test_spaces_is_blank(self):
        self.assertEqual(self._c("WSAA-NAME = SPACES"), "StringUtils.isBlank(wsaaName)")

    def test_bigdecimal_compareto(self):
        self.assertEqual(self._c("WSAA-AMT = 100"),
                         '(wsaaAmt.compareTo(new BigDecimal("100")) == 0)')

    def test_and_or_compound(self):
        self.assertEqual(self._c("WSAA-COUNT = 1 AND WSAA-NAME = SPACES"),
                         "wsaaCount == 1 && StringUtils.isBlank(wsaaName)")

    def test_condition_name_falls_to_none(self):
        """88 条件名 / 无关系运算符 → None（交 LLM）。"""
        self.assertIsNone(self._c("WSAA-STATUS-OK"))


class TestAsgIfVisitor(unittest.TestCase):
    """② visit_IfStmt 复刻 _sk_if 形状，条件经同一 translate_condition → 与 rules._try_condition 一致。"""

    def _ctx(self):
        return _leaf_ctx(field_type_map={"wsaaCount": {"type": "int"}})

    def test_if_condition_matches_legacy(self):
        from asg import IfStmt, MoveStmt, LeafJavaVisitor
        import translator.rules as rules
        ctx = self._ctx()
        node = IfStmt(cond=["WSAA-COUNT", "=", "1"],
                      then=[MoveStmt(tokens=["MOVE", "2", "TO", "WSAA-COUNT"])])
        out = LeafJavaVisitor(ctx).visit(node)
        self.assertEqual(out[0], f"if ({rules._try_condition(['WSAA-COUNT', '=', '1'], ctx)}) {{")
        self.assertEqual(out[0], "if (wsaaCount == 1) {")
        self.assertEqual(out[-1], "}")
        self.assertIn("    wsaaCount = 2;", out)        # body MOVE 直译 + 一级缩进

    def test_if_cond_none_falls_to_todo(self):
        from asg import IfStmt, LeafJavaVisitor
        node = IfStmt(cond=["WSAA-STATUS-OK"], raw="IF WSAA-STATUS-OK")
        self.assertEqual(LeafJavaVisitor(self._ctx()).visit(node), ["// TODO-IF: IF WSAA-STATUS-OK"])

    def test_if_body_unmigrated_leaf_placeholder(self):
        # 步骤32：STRING 已固化，改用仍未固化的 UNSTRING 验诚实占位
        from asg import IfStmt, Leaf, LeafJavaVisitor
        node = IfStmt(cond=["WSAA-COUNT", "=", "1"],
                      then=[Leaf(tokens=["UNSTRING", "WSAA-A", "DELIMITED", "BY", "SPACE", "INTO", "WSAA-B"],
                                 raw="UNSTRING WSAA-A DELIMITED BY SPACE INTO WSAA-B")])
        self.assertIn("    // TODO-LEAF: UNSTRING WSAA-A DELIMITED BY SPACE INTO WSAA-B",
                      LeafJavaVisitor(self._ctx()).visit(node))

    def test_nested_if_renders_indented(self):
        from asg import IfStmt, MoveStmt, LeafJavaVisitor
        inner = IfStmt(cond=["WSAA-COUNT", ">", "0"],
                       then=[MoveStmt(tokens=["MOVE", "0", "TO", "WSAA-COUNT"])])
        node = IfStmt(cond=["WSAA-COUNT", "=", "1"], then=[inner])
        out = LeafJavaVisitor(self._ctx()).visit(node)
        self.assertIn("    if (wsaaCount > 0) {", out)

    def test_if_else_branch(self):
        from asg import IfStmt, MoveStmt, LeafJavaVisitor
        node = IfStmt(cond=["WSAA-COUNT", "=", "1"],
                      then=[MoveStmt(tokens=["MOVE", "2", "TO", "WSAA-COUNT"])],
                      els=[MoveStmt(tokens=["MOVE", "3", "TO", "WSAA-COUNT"])])
        out = LeafJavaVisitor(self._ctx()).visit(node)
        self.assertIn("} else {", out)
        self.assertIn("    wsaaCount = 3;", out)


class TestDiffAsgVsLegacyIf(unittest.TestCase):
    """③ 整程序上旧/新两路 IF 条件串逐字符一致（含嵌套 / AND-OR / NOT）。"""

    SRC = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. TIF.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 WSAA-X PIC 9(04) VALUE 0.\n"
        "       01 WSAA-NM PIC X(10).\n"
        "       PROCEDURE DIVISION.\n"
        "       1000-MAIN SECTION.\n"
        "           IF WSAA-X = 1 AND WSAA-NM = SPACES\n"
        "               MOVE 2 TO WSAA-X\n"
        "               IF NOT WSAA-X > 5\n"
        "                   MOVE 0 TO WSAA-X\n"
        "               END-IF\n"
        "           END-IF.\n"
    )

    def test_legacy_equals_asg_if(self):
        from translator.skeleton_gen.body_context import build_body_ctx
        mod = TestDiffAsgVsLegacy()._harness()
        prog = TestAsgMoveLift()._parse(self.SRC)
        ctx, _ = build_body_ctx(prog)
        legacy = mod._legacy_ifs(prog, ctx)
        asg = mod._asg_ifs(prog, ctx)
        self.assertEqual(len(legacy), len(asg))
        self.assertTrue(len(legacy) >= 2, "样例应含嵌套 IF")
        self.assertEqual([x[1] for x in legacy], [x[1] for x in asg])


# ──────────────────────────────────────────────────────────────────────────────
# 步骤20 绞杀项3③ PERFORM 循环子句迁 visitor（抽 leaf/loop.py + visit_PerformStmt + 比对闸扩 PERFORM）
#   ① translate_perform_loop 抽出后循环壳正确（UNTIL/TEST AFTER/TIMES/VARYING/AFTER；无循环→([],[])；兜不住→None）
#   ② visit_PerformStmt 循环壳 == _perform_loop；inline_body 直译；out-of-line→TODO-PERFORM-CALL；None→TODO-PERFORM
#   ③ diff_asg_vs_legacy --verb PERFORM 两路循环壳逐字符一致（UNTIL/TIMES/VARYING 多形）
# 对应设计：docs/详细设计/步骤20-绞杀项3③PERFORM循环子句迁visitor设计.md §7。
# 只切①循环子句；②THRU区间/③struct_rebind 留后续刀（设计 §1 非目标）。
# ──────────────────────────────────────────────────────────────────────────────

class TestLeafLoopExtract(unittest.TestCase):
    """① 抽出的 translate_perform_loop 循环壳正确（覆盖各循环形态）。"""

    FTM = {"wsaaX": {"type": "int"}, "wsaaI": {"type": "int"}, "wsaaJ": {"type": "int"}}

    def _loop(self, header):
        from translator.leaf import translate_perform_loop
        return translate_perform_loop(header, _leaf_ctx(field_type_map=self.FTM), 0)

    def test_until_while(self):
        self.assertEqual(self._loop(["UNTIL", "WSAA-X", ">", "5"]),
                         (["while (!(wsaaX > 5)) {"], ["}"]))

    def test_until_test_after_do_while(self):
        self.assertEqual(self._loop(["WITH", "TEST", "AFTER", "UNTIL", "WSAA-X", ">", "5"]),
                         (["do {"], ["} while (!(wsaaX > 5));"]))

    def test_times_for(self):
        self.assertEqual(self._loop(["3", "TIMES"]),
                         (["for (int _i = 0; _i < 3; _i++) {"], ["}"]))

    def test_varying_single_for(self):
        self.assertEqual(
            self._loop(["VARYING", "WSAA-I", "FROM", "1", "BY", "1", "UNTIL", "WSAA-I", ">", "3"]),
            (["for (wsaaI = 1; !(wsaaI > 3); wsaaI = wsaaI + 1) {"], ["}"]))

    def test_varying_after_nested_for(self):
        open_lines, close_lines = self._loop(
            ["VARYING", "WSAA-I", "FROM", "1", "BY", "1", "UNTIL", "WSAA-I", ">", "3",
             "AFTER", "WSAA-J", "FROM", "1", "BY", "1", "UNTIL", "WSAA-J", ">", "2"])
        self.assertEqual(open_lines, ["for (wsaaI = 1; !(wsaaI > 3); wsaaI = wsaaI + 1) {",
                                      "    for (wsaaJ = 1; !(wsaaJ > 2); wsaaJ = wsaaJ + 1) {"])
        self.assertEqual(close_lines, ["    }", "}"])

    def test_no_loop_empty(self):
        self.assertEqual(self._loop(["2000-SUB"]), ([], []))

    def test_until_uncond_falls_to_none(self):
        """UNTIL 条件兜不住（88/无关系符）→ None（整条交 LLM）。"""
        self.assertIsNone(self._loop(["UNTIL", "WSAA-STATUS-OK"]))

    def test_varying_test_after_none(self):
        """VARYING + TEST AFTER → None（D16-1 保守落 LLM）。"""
        self.assertIsNone(self._loop(
            ["VARYING", "WSAA-I", "FROM", "1", "BY", "1", "WITH", "TEST", "AFTER",
             "UNTIL", "WSAA-I", ">", "3"]))


class TestAsgPerformVisitor(unittest.TestCase):
    """② visit_PerformStmt 循环壳经同一 translate_perform_loop → 与 rules._perform_loop 一致。"""

    def _ctx(self):
        return _leaf_ctx(field_type_map={"wsaaX": {"type": "int"}})

    def test_loop_shell_matches_legacy(self):
        from asg import PerformStmt, MoveStmt, LeafJavaVisitor
        import translator.rules as rules
        ctx = self._ctx()
        hdr = ["UNTIL", "WSAA-X", ">", "5"]
        node = PerformStmt(header=hdr, inline_body=[MoveStmt(tokens=["MOVE", "2", "TO", "WSAA-X"])])
        out = LeafJavaVisitor(ctx).visit(node)
        op, cl = rules._perform_loop(hdr, [h.upper() for h in hdr], ctx, 0)
        self.assertEqual(out[0], op[0])            # 循环壳首行 == 旧 _perform_loop
        self.assertEqual(out[-1], cl[-1])
        self.assertEqual(out, ["while (!(wsaaX > 5)) {", "    wsaaX = 2;", "}"])

    def test_out_of_line_target_placeholder(self):
        from asg import PerformStmt, ProcRef, LeafJavaVisitor
        node = PerformStmt(header=["2000-SUB"], target=ProcRef(name="2000-SUB"))
        self.assertEqual(LeafJavaVisitor(self._ctx()).visit(node), ["// TODO-PERFORM-CALL: 2000-SUB"])

    def test_out_of_line_thru_placeholder(self):
        from asg import PerformStmt, ProcRef, LeafJavaVisitor
        node = PerformStmt(header=["1000-A", "THRU", "2000-B"],
                           target=ProcRef(name="1000-A"), thru=ProcRef(name="2000-B"))
        self.assertEqual(LeafJavaVisitor(self._ctx()).visit(node),
                         ["// TODO-PERFORM-CALL: 1000-A THRU 2000-B"])

    def test_loop_none_falls_to_todo(self):
        from asg import PerformStmt, LeafJavaVisitor
        node = PerformStmt(header=["UNTIL", "WSAA-STATUS-OK"], raw="PERFORM UNTIL WSAA-STATUS-OK")
        self.assertEqual(LeafJavaVisitor(self._ctx()).visit(node),
                         ["// TODO-PERFORM: PERFORM UNTIL WSAA-STATUS-OK"])


class TestDiffAsgVsLegacyPerform(unittest.TestCase):
    """③ 整程序上旧/新两路 PERFORM 循环壳逐字符一致（UNTIL / TIMES / VARYING AFTER / out-of-line）。"""

    SRC = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. TPF.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 WSAA-X    PIC 9(04) VALUE 0.\n"
        "       01 WSAA-I    PIC 9(04) VALUE 0.\n"
        "       01 WSAA-J    PIC 9(04) VALUE 0.\n"
        "       PROCEDURE DIVISION.\n"
        "       1000-MAIN SECTION.\n"
        "           PERFORM UNTIL WSAA-X > 5\n"
        "               MOVE 1 TO WSAA-X\n"
        "           END-PERFORM.\n"
        "           PERFORM 3 TIMES\n"
        "               MOVE 2 TO WSAA-X\n"
        "           END-PERFORM.\n"
        "           PERFORM VARYING WSAA-I FROM 1 BY 1 UNTIL WSAA-I > 3\n"
        "                   AFTER WSAA-J FROM 1 BY 1 UNTIL WSAA-J > 2\n"
        "               MOVE WSAA-I TO WSAA-X\n"
        "           END-PERFORM.\n"
        "           PERFORM 2000-SUB.\n"
        "       2000-SUB SECTION.\n"
        "           MOVE 9 TO WSAA-X.\n"
    )

    def test_legacy_equals_asg_perform(self):
        from translator.skeleton_gen.body_context import build_body_ctx
        mod = TestDiffAsgVsLegacy()._harness()
        prog = TestAsgMoveLift()._parse(self.SRC)
        ctx, _ = build_body_ctx(prog)
        legacy = mod._legacy_performs(prog, ctx)
        asg = mod._asg_performs(prog, ctx)
        self.assertEqual(len(legacy), len(asg))
        self.assertTrue(len(legacy) >= 4, "样例应含 UNTIL/TIMES/VARYING/out-of-line 多条 PERFORM")
        self.assertEqual([x[1] for x in legacy], [x[1] for x in asg])


# ──────────────────────────────────────────────────────────────────────────────
# 步骤21 绞杀项3④ CALL 迁 visitor（抽 leaf/call.py + visit_CallStmt + 比对闸扩 CALL）
#   ① translate_call 抽出后输出正确（IO固化/功能码未设→([],False)/未映射→([],False)/系统子程序）
#   ② visit_CallStmt 输出 == translate_call；matched=False→// TODO-CALL
#   ③ diff_asg_vs_legacy --verb CALL 两路 (lines,matched) 逐字符一致（IO/非IO/嵌套于 IF/PERFORM）
# 对应设计：docs/详细设计/步骤21-绞杀项3④CALL迁visitor设计.md §7。
# 只切①散点 CALL 兜底；②结构吸收/③struct_rebind 留后续刀（设计 §1 非目标）。
# ──────────────────────────────────────────────────────────────────────────────

class TestLeafCallExtract(unittest.TestCase):
    """① 抽出的 translate_call 输出正确（覆盖 CALL 各形态，与抽取前 rules._t_call 一致）。"""

    def _ctx(self, **kw):
        import translator.rules as r
        base = dict(
            field_type_map={}, section_to_method=lambda s: s, known_sections=set(),
            io_struct_prefixes={"ELPO"},
            io_programs={"ELPOIO": {"field_name": "elpoRepository",
                                    "param_struct": "ELPO-PARAMS",
                                    "operations": {"READR": "findByKey({key})"}}},
        )
        base.update(kw)
        return r.Ctx(**base)

    def test_io_static_when_function_set(self):
        """功能码已知（READR，经 struct_function）→ 直出 findByKey，参数对象进出。"""
        from translator.leaf import translate_call
        ctx = self._ctx()
        ctx.struct_function["ELPO"] = "READR"
        lines, ok = translate_call("CALL 'ELPOIO' USING ELPO-PARAMS".split(), ctx)
        self.assertTrue(ok)
        self.assertEqual(lines, ["elpoParams = elpoRepository.findByKey(elpoParams);"])

    def test_no_function_falls_to_llm(self):
        """struct_function 未设功能码（游标/未知）→ ([],False)，交 LLM。"""
        from translator.leaf import translate_call
        lines, ok = translate_call("CALL 'ELPOIO' USING ELPO-PARAMS".split(), self._ctx())
        self.assertFalse(ok)
        self.assertEqual(lines, [])

    def test_unmapped_falls_to_llm(self):
        """未映射子程序 → ([],False)，交 LLM。"""
        from translator.leaf import translate_call
        lines, ok = translate_call("CALL 'FOOIO' USING FOO-PARAMS".split(), self._ctx())
        self.assertFalse(ok)

    def test_system_program_java_code(self):
        """系统子程序（java_code）→ 直出补分号。"""
        from translator.leaf import translate_call
        ctx = self._ctx(system_programs={"SYSERR": {"java_code": "throw new RuntimeException()"}})
        lines, ok = translate_call("CALL 'SYSERR' USING X".split(), ctx)
        self.assertTrue(ok)
        self.assertEqual(lines, ["throw new RuntimeException();"])


class TestAsgCallVisitor(unittest.TestCase):
    """② visit_CallStmt 经同一 translate_call → 与 rules._t_call 一致；matched=False→// TODO-CALL。"""

    def _ctx(self, **kw):
        return TestLeafCallExtract()._ctx(**kw)

    def test_matched_call_matches_legacy(self):
        from asg import CallStmt, LeafJavaVisitor
        import translator.rules as rules
        ctx = self._ctx()
        ctx.struct_function["ELPO"] = "READR"
        toks = "CALL 'ELPOIO' USING ELPO-PARAMS".split()
        node = CallStmt(name="ELPOIO", tokens=toks, raw="CALL 'ELPOIO' USING ELPO-PARAMS")
        out = LeafJavaVisitor(ctx).visit(node)
        self.assertEqual(out, rules._t_call(toks, ctx)[0])
        self.assertEqual(out, ["elpoParams = elpoRepository.findByKey(elpoParams);"])

    def test_unmatched_call_todo_placeholder(self):
        from asg import CallStmt, LeafJavaVisitor
        node = CallStmt(name="SOMESUB", tokens="CALL 'SOMESUB' USING WSAA-X".split(),
                        raw="CALL 'SOMESUB' USING WSAA-X")
        self.assertEqual(LeafJavaVisitor(self._ctx()).visit(node),
                         ["// TODO-CALL: CALL 'SOMESUB' USING WSAA-X"])


class TestDiffAsgVsLegacyCall(unittest.TestCase):
    """③ 整程序上旧/新两路 CALL 的 (lines,matched) 逐字符一致（IO/非IO/嵌套于 IF 与 PERFORM）。"""

    SRC = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. TCALL.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 WSAA-X    PIC 9(04) VALUE 0.\n"
        "       01 AGNT-PARAMS.\n"
        "          03 AGNT-FUNCTION PIC X(05).\n"
        "       PROCEDURE DIVISION.\n"
        "       1000-MAIN SECTION.\n"
        "           MOVE READR TO AGNT-FUNCTION.\n"
        "           CALL 'AGNTIO' USING AGNT-PARAMS.\n"
        "           CALL 'SOMESUB' USING WSAA-X.\n"
        "           IF WSAA-X = 1\n"
        "               CALL 'CLNTIO' USING CLNT-PARAMS\n"
        "           END-IF.\n"
        "           PERFORM UNTIL WSAA-X > 5\n"
        "               CALL 'CHDRENQIO' USING CHDRENQ-PARAMS\n"
        "           END-PERFORM.\n"
    )

    def test_legacy_equals_asg_call(self):
        from translator.skeleton_gen.body_context import build_body_ctx
        mod = TestDiffAsgVsLegacy()._harness()
        prog = TestAsgMoveLift()._parse(self.SRC)
        ctx, _ = build_body_ctx(prog)
        legacy = mod._legacy_calls(prog, ctx)
        asg = mod._asg_calls(prog, ctx)
        self.assertEqual(len(legacy), len(asg))
        self.assertTrue(len(legacy) >= 4, "样例应含 IO/非IO/嵌套于 IF 与 PERFORM 多条 CALL")
        self.assertEqual([x[1] for x in legacy], [x[1] for x in asg])


# ──────────────────────────────────────────────────────────────────────────────
# 步骤22 绞杀项3⑤ 算术/赋值动词迁 visitor（拆 leaf/assign.py + leaf/arith.py）
#   ① translate_assign/translate_arith/translate_arith_assign 抽出后输出正确
#   ② visit_Leaf 经 translate_arith_assign → 7 类直译；未固化（STRING）→ // TODO-LEAF；IF/PERFORM body 内直译可见
#   ③ diff_asg_vs_legacy --verb ARITH 两路 (lines,matched) 逐字符一致（含嵌套于 IF）
# 对应设计：docs/详细设计/步骤22-绞杀项3⑤算术赋值动词迁visitor设计.md §7。
# ──────────────────────────────────────────────────────────────────────────────

class TestLeafArithExtract(unittest.TestCase):
    """① 抽出的 translate_assign/translate_arith/translate_arith_assign 输出正确。"""

    FTM = {"wsaaCount": {"type": "int"}, "wsaaAmt": {"type": "BigDecimal"},
           "wsaaFlag": {"type": "String"}}

    def _ctx(self, **kw):
        return _leaf_ctx(field_type_map=self.FTM, **kw)

    def test_add_int_compound(self):
        from translator.leaf import translate_arith_assign
        self.assertEqual(translate_arith_assign("ADD 1 TO WSAA-COUNT".split(), self._ctx()),
                         (["wsaaCount += 1;"], True))

    def test_add_bigdecimal_chain(self):
        from translator.leaf import translate_arith_assign
        self.assertEqual(translate_arith_assign("ADD 1 TO WSAA-AMT".split(), self._ctx()),
                         (['wsaaAmt = wsaaAmt.add(new BigDecimal("1"));'], True))

    def test_subtract_int(self):
        from translator.leaf import translate_arith_assign
        self.assertEqual(translate_arith_assign("SUBTRACT 1 FROM WSAA-COUNT".split(), self._ctx()),
                         (["wsaaCount -= 1;"], True))

    def test_multiply_int(self):
        from translator.leaf import translate_arith_assign
        self.assertEqual(translate_arith_assign("MULTIPLY 2 BY WSAA-COUNT".split(), self._ctx()),
                         (["wsaaCount = wsaaCount * 2;"], True))

    def test_divide_into_giving(self):
        from translator.leaf import translate_arith_assign
        self.assertEqual(translate_arith_assign("DIVIDE 10 INTO WSAA-COUNT".split(), self._ctx()),
                         (["wsaaCount = wsaaCount / 10;"], True))

    def test_compute_int_infix(self):
        from translator.leaf import translate_arith_assign
        self.assertEqual(translate_arith_assign("COMPUTE WSAA-COUNT = WSAA-COUNT + 1".split(), self._ctx()),
                         (["wsaaCount = wsaaCount + 1;"], True))

    def test_initialize_numeric_field(self):
        from translator.leaf import translate_arith_assign
        self.assertEqual(translate_arith_assign("INITIALIZE WSAA-COUNT".split(), self._ctx()),
                         (["wsaaCount = 0;"], True))

    def test_initialize_params_struct(self):
        from translator.leaf import translate_arith_assign
        ctx = self._ctx(prefixes={"ELPO"})
        self.assertEqual(translate_arith_assign("INITIALIZE ELPO-PARAMS".split(), ctx),
                         (["elpoParams = new ElpoParams();"], True))

    def test_set_to_number(self):
        from translator.leaf import translate_arith_assign
        self.assertEqual(translate_arith_assign("SET WSAA-COUNT TO 5".split(), self._ctx()),
                         (["wsaaCount = 5;"], True))

    def test_set_to_true_falls_to_llm(self):
        from translator.leaf import translate_arith_assign
        self.assertEqual(translate_arith_assign("SET WSAA-FLAG TO TRUE".split(), self._ctx()),
                         ([], False))

    def test_non_arith_verb_falls_through(self):
        from translator.leaf import translate_arith_assign
        self.assertEqual(translate_arith_assign("STRING WSAA-A DELIMITED BY SIZE INTO WSAA-B".split(), self._ctx()),
                         ([], False))

    def test_disjoint_dispatch(self):
        """两子分派器 verb 集互斥：assign 不接算术、arith 不接赋值。"""
        from translator.leaf import translate_assign, translate_arith
        self.assertEqual(translate_assign("ADD 1 TO WSAA-COUNT".split(), self._ctx()), ([], False))
        self.assertEqual(translate_arith("SET WSAA-COUNT TO 5".split(), self._ctx()), ([], False))


class TestLeafStringExtract(unittest.TestCase):
    """步骤32：STRING ... DELIMITED BY ... INTO ... 叶子翻译。"""

    FTM = {
        "wsaaA": {"type": "String"},
        "wsaaB": {"type": "String"},
        "wsaaC": {"type": "String"},
        "wsaaOut": {"type": "String"},
    }

    def _ctx(self):
        return _leaf_ctx(field_type_map=self.FTM)

    def test_delimited_by_size_concatenates_full_sources(self):
        from translator.leaf import translate_string

        toks = "STRING WSAA-A DELIMITED BY SIZE WSAA-B DELIMITED BY SIZE INTO WSAA-OUT".split()

        self.assertEqual(translate_string(toks, self._ctx()),
                         (["wsaaOut = wsaaA + wsaaB;"], True))

    def test_delimited_by_space_uses_first_space_boundary(self):
        from translator.leaf import translate_string

        toks = "STRING WSAA-A DELIMITED BY SPACE INTO WSAA-OUT".split()

        self.assertEqual(translate_string(toks, self._ctx()),
                         (['wsaaOut = String.valueOf(wsaaA).split(java.util.regex.Pattern.quote(" "), 2)[0];'],
                          True))

    def test_literal_delimiter_uses_first_delimiter_boundary(self):
        from translator.leaf import translate_string

        toks = ["STRING", "WSAA-A", "DELIMITED", "BY", "'/'", "INTO", "WSAA-OUT"]

        self.assertEqual(translate_string(toks, self._ctx()),
                         (['wsaaOut = String.valueOf(wsaaA).split(java.util.regex.Pattern.quote("/"), 2)[0];'],
                          True))

    def test_mixed_delimiters_concatenate_rendered_parts(self):
        from translator.leaf import translate_string

        toks = ["STRING", "WSAA-A", "DELIMITED", "BY", "SIZE",
                "WSAA-B", "DELIMITED", "BY", "SPACE",
                "WSAA-C", "DELIMITED", "BY", "'/'",
                "INTO", "WSAA-OUT"]

        self.assertEqual(translate_string(toks, self._ctx()),
                         (['wsaaOut = wsaaA + String.valueOf(wsaaB).split(java.util.regex.Pattern.quote(" "), 2)[0] + String.valueOf(wsaaC).split(java.util.regex.Pattern.quote("/"), 2)[0];'],
                          True))

    def test_unsupported_clauses_fall_through(self):
        from translator.leaf import translate_string

        cases = [
            "STRING WSAA-A DELIMITED BY SIZE INTO WSAA-OUT WITH POINTER WSAA-B",
            "STRING WSAA-A DELIMITED BY SIZE INTO WSAA-OUT ON OVERFLOW MOVE 1 TO WSAA-C",
            "STRING WSAA-A INTO WSAA-OUT",
            "STRING WSAA-A DELIMITED BY SIZE",
        ]
        for line in cases:
            self.assertEqual(translate_string(line.split(), self._ctx()), ([], False))

    def test_non_string_verb_falls_through(self):
        from translator.leaf import translate_string

        self.assertEqual(translate_string("UNSTRING WSAA-A DELIMITED BY SPACE INTO WSAA-OUT".split(),
                                          self._ctx()),
                         ([], False))


class TestAsgLeafArithVisitor(unittest.TestCase):
    """② visit_Leaf 经同一 translate_arith_assign → 与之逐字符一致；未固化→// TODO-LEAF；IF body 内直译可见。"""

    def _ctx(self):
        return _leaf_ctx(field_type_map={"wsaaCount": {"type": "int"}})

    def test_leaf_arith_matches_translate(self):
        from asg import Leaf, LeafJavaVisitor
        from translator.leaf import translate_arith_assign
        ctx = self._ctx()
        toks = "ADD 1 TO WSAA-COUNT".split()
        node = Leaf(tokens=list(toks), raw="ADD 1 TO WSAA-COUNT")
        self.assertEqual(LeafJavaVisitor(ctx).visit(node), translate_arith_assign(toks, ctx)[0])
        self.assertEqual(LeafJavaVisitor(ctx).visit(node), ["wsaaCount += 1;"])

    def test_unmigrated_leaf_placeholder(self):
        from asg import Leaf, LeafJavaVisitor
        node = Leaf(tokens="UNSTRING WSAA-A DELIMITED BY SPACE INTO WSAA-B".split(),
                    raw="UNSTRING WSAA-A DELIMITED BY SPACE INTO WSAA-B")
        self.assertEqual(LeafJavaVisitor(self._ctx()).visit(node),
                         ["// TODO-LEAF: UNSTRING WSAA-A DELIMITED BY SPACE INTO WSAA-B"])

    def test_arith_inside_if_body_direct(self):
        from asg import IfStmt, Leaf, LeafJavaVisitor
        node = IfStmt(cond=["WSAA-COUNT", "=", "1"],
                      then=[Leaf(tokens="ADD 2 TO WSAA-COUNT".split(), raw="ADD 2 TO WSAA-COUNT")])
        out = LeafJavaVisitor(self._ctx()).visit(node)
        self.assertIn("    wsaaCount += 2;", out)
        self.assertNotIn("    // TODO-LEAF: ADD 2 TO WSAA-COUNT", out)


class TestUnifiedLeafEntry(unittest.TestCase):
    """Step 31: rules and ASG visitor share translator.leaf.translate_leaf_stmt."""

    def _ctx(self):
        ctx = _leaf_ctx(field_type_map={
            "wsaaCount": {"type": "int"},
            "wsaaA": {"type": "String"},
            "wsaaB": {"type": "String"},
            "wsaaOut": {"type": "String"},
        })
        ctx.system_programs = {"SYSERR": {"java_code": "throw new RuntimeException()"}}
        return ctx

    def test_translate_leaf_stmt_matches_rules_dispatch_for_supported_verbs(self):
        from translator.leaf import translate_leaf_stmt
        import translator.rules as rules

        ctx = self._ctx()
        cases = [
            "MOVE 1 TO WSAA-COUNT",
            "ADD 1 TO WSAA-COUNT",
            "CALL 'SYSERR'",
            "STRING WSAA-A DELIMITED BY SIZE WSAA-B DELIMITED BY SIZE INTO WSAA-OUT",
        ]
        for line in cases:
            toks = line.split()
            self.assertEqual(translate_leaf_stmt(toks, ctx), rules._dispatch_leaf(toks, ctx))

    def test_translate_leaf_stmt_handles_control_leaf_words(self):
        from translator.leaf import translate_leaf_stmt

        self.assertEqual(translate_leaf_stmt(["CONTINUE"], self._ctx()), ([";  // CONTINUE"], True))

    def test_translate_leaf_stmt_falls_through_for_unmigrated_verbs(self):
        from translator.leaf import translate_leaf_stmt

        self.assertEqual(translate_leaf_stmt("UNSTRING WSAA-A DELIMITED BY SPACE INTO WSAA-B".split(),
                                             self._ctx()),
                         ([], False))

    def test_asg_leaf_uses_shared_string_output(self):
        from asg import Leaf, LeafJavaVisitor

        ctx = self._ctx()
        raw = "STRING WSAA-A DELIMITED BY SIZE WSAA-B DELIMITED BY SIZE INTO WSAA-OUT"
        node = Leaf(tokens=raw.split(), raw=raw)

        self.assertEqual(LeafJavaVisitor(ctx).visit(node), ["wsaaOut = wsaaA + wsaaB;"])

    def test_asg_leaf_keeps_unsupported_string_placeholder(self):
        from asg import Leaf, LeafJavaVisitor

        raw = "STRING WSAA-A DELIMITED BY SIZE INTO WSAA-OUT WITH POINTER WSAA-B"
        node = Leaf(tokens=raw.split(), raw=raw)

        self.assertEqual(LeafJavaVisitor(self._ctx()).visit(node), [f"// TODO-LEAF: {raw}"])

    def test_rules_and_asg_leaf_share_supported_output(self):
        from asg import Leaf, LeafJavaVisitor
        from translator.segmenter import Stmt
        import translator.rules as rules

        ctx = self._ctx()
        stmt = Stmt(kind="simple", tokens="ADD 1 TO WSAA-COUNT".split(), raw="ADD 1 TO WSAA-COUNT")
        node = Leaf(tokens=list(stmt.tokens), raw=stmt.raw)

        lines, matched = rules.translate_leaf(stmt, ctx)
        self.assertTrue(matched)
        self.assertEqual(LeafJavaVisitor(ctx).visit(node), lines)


class TestDiffAsgVsLegacyArith(unittest.TestCase):
    """③ 整程序上旧/新两路 ARITH 的 (lines,matched) 逐字符一致（INITIALIZE/SET/ADD/SUBTRACT/COMPUTE，含嵌套于 IF）。"""

    SRC = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. TARITH.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 WSAA-COUNT    PIC 9(04) VALUE 0.\n"
        "       PROCEDURE DIVISION.\n"
        "       1000-MAIN SECTION.\n"
        "           INITIALIZE WSAA-COUNT.\n"
        "           SET WSAA-COUNT TO 5.\n"
        "           ADD 1 TO WSAA-COUNT.\n"
        "           SUBTRACT 1 FROM WSAA-COUNT.\n"
        "           COMPUTE WSAA-COUNT = WSAA-COUNT + 1.\n"
        "           IF WSAA-COUNT = 1\n"
        "               ADD 2 TO WSAA-COUNT\n"
        "           END-IF.\n"
    )

    def test_legacy_equals_asg_arith(self):
        from translator.skeleton_gen.body_context import build_body_ctx
        mod = TestDiffAsgVsLegacy()._harness()
        prog = TestAsgMoveLift()._parse(self.SRC)
        ctx, _ = build_body_ctx(prog)
        legacy = mod._legacy_arith(prog, ctx)
        asg = mod._asg_arith(prog, ctx)
        self.assertEqual(len(legacy), len(asg))
        self.assertTrue(len(legacy) >= 5, "样例应含 INITIALIZE/SET/ADD/SUBTRACT/COMPUTE + 嵌套于 IF 的 ADD")
        self.assertEqual([x[1] for x in legacy], [x[1] for x in asg])


# ──────────────────────────────────────────────────────────────────────────────
# 步骤23 绞杀项3⑥ 控制流动词 EVALUATE/GOTO 迁 visitor（leaf/control.py）
#   ① translate_control（各控制词 flow_label-无关）/ translate_evaluate / evaluate_case_label 抽出后正确
#   ② visit_GotoStmt==translate_control；CONTINUE 经 visit_Leaf 兜底；visit_EvaluateStmt 渲 switch 壳
#   ③ diff_asg_vs_legacy --verb CONTROL 两路壳逐字符一致（EVALUATE+GO TO+CONTINUE，含嵌套）
# 对应设计：docs/详细设计/步骤23-绞杀项3⑥控制流动词EVALUATE-GOTO迁visitor设计.md §7。
# ──────────────────────────────────────────────────────────────────────────────

class TestLeafControlExtract(unittest.TestCase):
    """① translate_control / translate_evaluate / evaluate_case_label 输出正确。"""

    def _c(self, line, known=None):
        from translator.leaf import translate_control
        ctx = _leaf_ctx()
        if known:
            ctx.known_sections = set(known)
        return translate_control(line.split(), ctx)

    def test_goto_exit(self):
        self.assertEqual(self._c("GO TO 1000-EXIT"), (["return;  // GO TO 1000-EXIT"], True))

    def test_goto_unknown(self):
        self.assertEqual(self._c("GO TO 9000-WHERE"),
                         (["// TODO-GOTO: 跳转 9000-WHERE，需人工核对控制流", "return;"], True))

    def test_goto_known_section_proc_call(self):
        lines, ok = self._c("GO TO 2000-SEC", known={"2000-SEC"})
        self.assertTrue(ok)
        self.assertEqual(lines, ["// TODO-GOTO: 跳转 2000-SEC，需人工核对控制流",
                                 "this.2000-SEC();", "return;"])

    def test_goto_no_target(self):
        self.assertEqual(self._c("GO"), (["return;"], True))

    def test_goback_stop_return(self):
        self.assertEqual(self._c("GOBACK"), (["return;"], True))
        self.assertEqual(self._c("STOP RUN"), (["return;"], True))

    def test_exit_non_dispatch(self):
        self.assertEqual(self._c("EXIT"), (["return;  // EXIT"], True))

    def test_continue_next(self):
        self.assertEqual(self._c("CONTINUE"), ([";  // CONTINUE"], True))
        self.assertEqual(self._c("NEXT SENTENCE"), ([";  // NEXT SENTENCE"], True))

    def test_non_control_falls_through(self):
        self.assertEqual(self._c("MOVE A TO B"), ([], False))

    def test_evaluate_subject_single_token(self):
        from translator.leaf import translate_evaluate
        ctx = _leaf_ctx(field_type_map={"wsaaX": {"type": "String"}})
        self.assertEqual(translate_evaluate(["WSAA-X"], ctx), "wsaaX.trim()")

    def test_evaluate_true_and_multitoken_none(self):
        from translator.leaf import translate_evaluate
        ctx = _leaf_ctx()
        self.assertIsNone(translate_evaluate(["TRUE"], ctx))
        self.assertIsNone(translate_evaluate(["WSAA-X", "WSAA-Y"], ctx))
        self.assertIsNone(translate_evaluate([], ctx))

    def test_evaluate_case_label(self):
        from translator.leaf import evaluate_case_label
        ctx = _leaf_ctx()
        self.assertEqual(evaluate_case_label(["OTHER"], ctx), "default")
        self.assertEqual(evaluate_case_label([], ctx), "default")
        self.assertEqual(evaluate_case_label(["'A'"], ctx), 'case "A"')


class TestAsgControlVisitor(unittest.TestCase):
    """② visit_GotoStmt==translate_control；CONTINUE 经 visit_Leaf 兜底；visit_EvaluateStmt 渲 switch 壳。"""

    def test_goto_via_visitor(self):
        from asg import GotoStmt, LeafJavaVisitor
        from translator.leaf import translate_control
        ctx = _leaf_ctx()
        node = GotoStmt(tokens="GO TO 1000-EXIT".split(), raw="GO TO 1000-EXIT")
        self.assertEqual(LeafJavaVisitor(ctx).visit(node),
                         translate_control(node.tokens, ctx)[0])

    def test_continue_via_visit_leaf(self):
        from asg import Leaf, LeafJavaVisitor
        node = Leaf(tokens=["CONTINUE"], raw="CONTINUE")
        self.assertEqual(LeafJavaVisitor(_leaf_ctx()).visit(node), [";  // CONTINUE"])

    def test_evaluate_switch_shell(self):
        from asg import EvaluateStmt, Leaf, LeafJavaVisitor
        ctx = _leaf_ctx(field_type_map={"wsaaX": {"type": "String"}})
        node = EvaluateStmt(subject=["WSAA-X"],
                            whens=[(["'A'"], [Leaf(tokens=["CONTINUE"], raw="CONTINUE")]),
                                   (["OTHER"], [])],
                            raw="EVALUATE WSAA-X")
        out = LeafJavaVisitor(ctx).visit(node)
        self.assertEqual(out[0], "switch (wsaaX.trim()) {")
        self.assertIn('    case "A": {', out)
        self.assertIn("        ;  // CONTINUE", out)   # WHEN 体直译可见（CONTINUE 经 visit_Leaf）
        self.assertIn("    default: {", out)
        self.assertEqual(out[-1], "}")

    def test_evaluate_true_todo(self):
        from asg import EvaluateStmt, LeafJavaVisitor
        node = EvaluateStmt(subject=["TRUE"], whens=[(["'A'"], [])], raw="EVALUATE TRUE")
        self.assertEqual(LeafJavaVisitor(_leaf_ctx()).visit(node), ["// TODO-EVALUATE: EVALUATE TRUE"])


class TestDiffAsgVsLegacyControl(unittest.TestCase):
    """③ 整程序上旧/新两路控制流壳逐字符一致（EVALUATE + GO TO + CONTINUE，含嵌套于 IF）。"""

    SRC = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. TCTRL.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 WSAA-X    PIC X(02) VALUE SPACE.\n"
        "       PROCEDURE DIVISION.\n"
        "       1000-MAIN SECTION.\n"
        "           EVALUATE WSAA-X\n"
        "               WHEN 'A'\n"
        "                   CONTINUE\n"
        "               WHEN OTHER\n"
        "                   GO TO 1000-EXIT\n"
        "           END-EVALUATE.\n"
        "           IF WSAA-X = 'B'\n"
        "               GO TO 1000-EXIT\n"
        "           END-IF.\n"
        "           CONTINUE.\n"
        "       1000-EXIT.\n"
        "           EXIT.\n"
    )

    def test_legacy_equals_asg_control(self):
        from translator.skeleton_gen.body_context import build_body_ctx
        mod = TestDiffAsgVsLegacy()._harness()
        prog = TestAsgMoveLift()._parse(self.SRC)
        ctx, _ = build_body_ctx(prog)
        legacy = mod._legacy_control(prog, ctx)
        asg = mod._asg_control(prog, ctx)
        self.assertEqual(len(legacy), len(asg))
        self.assertTrue(len(legacy) >= 4, "样例应含 EVALUATE + GO TO（嵌套于 EVALUATE/IF）+ CONTINUE + EXIT")
        self.assertEqual([x[1] for x in legacy], [x[1] for x in asg])


class TestAsgSectionVisitorFlow(unittest.TestCase):
    """步骤24：ASG SectionJavaVisitor 迁入 paragraph 装配与 flow dispatch。"""

    def _ctx(self, proc_order=None, sections=None):
        import translator.rules as r
        sections = sections or []
        return r.Ctx(field_type_map={},
                     section_to_method=lambda s: "p_" + s.replace("-", "").lower(),
                     known_sections=set(sections),
                     section_order=list(sections),
                     proc_order=list(proc_order or []))

    def test_flat_paragraphs_without_goto(self):
        from asg import Section, Paragraph, MoveStmt, SectionJavaVisitor
        ctx = self._ctx()
        sec = Section(name="S", paragraphs=[
            Paragraph(label="PARA-A", stmts=[MoveStmt(tokens="MOVE 1 TO X".split(), raw="MOVE 1 TO X")]),
            Paragraph(label="PARA-B", stmts=[MoveStmt(tokens="MOVE 2 TO Y".split(), raw="MOVE 2 TO Y")]),
        ])
        out = "\n".join(SectionJavaVisitor(ctx).render_section(sec))
        self.assertIn("// paragraph PARA-A", out)
        self.assertIn("// paragraph PARA-B", out)
        self.assertNotIn("switch (__pc)", out)

    def test_back_edge_goto_uses_state_machine(self):
        from asg import Section, Paragraph, GotoStmt, MoveStmt, SectionJavaVisitor
        from asg.registry import ProcRef
        ctx = self._ctx()
        sec = Section(name="S", paragraphs=[
            Paragraph(label="PARA-A", stmts=[MoveStmt(tokens="MOVE 1 TO X".split(), raw="MOVE 1 TO X")]),
            Paragraph(label="PARA-B", stmts=[GotoStmt(target=ProcRef("PARA-A"), tokens="GO TO PARA-A".split())]),
        ])
        out = "\n".join(SectionJavaVisitor(ctx).render_section(sec))
        self.assertIn("switch (__pc)", out)
        self.assertIn('__pc = "PARA-A"; continue FLOW;', out)

    def test_force_sm_forward_goto(self):
        from asg import Section, Paragraph, GotoStmt, MoveStmt, SectionJavaVisitor
        from asg.registry import ProcRef
        ctx = self._ctx()
        sec = Section(name="S", paragraphs=[
            Paragraph(label="PARA-A", stmts=[GotoStmt(target=ProcRef("PARA-C"), tokens="GO TO PARA-C".split())]),
            Paragraph(label="PARA-B", stmts=[MoveStmt(tokens="MOVE 2 TO Y".split(), raw="MOVE 2 TO Y")]),
            Paragraph(label="PARA-C", stmts=[MoveStmt(tokens="MOVE 3 TO Z".split(), raw="MOVE 3 TO Z")]),
        ])
        out = "\n".join(SectionJavaVisitor(ctx, force_sm=True).render_section(sec))
        self.assertIn("switch (__pc)", out)
        self.assertIn('__pc = "PARA-C"; continue FLOW;', out)


class TestAsgSectionVisitorPerformTarget(unittest.TestCase):
    """步骤24：PERFORM out-of-line 目标解析迁入 SectionJavaVisitor。"""

    def _ctx(self, proc_order=None, sections=None):
        import translator.rules as r
        sections = sections or []
        return r.Ctx(field_type_map={},
                     section_to_method=lambda s: "p_" + s.replace("-", "").lower(),
                     known_sections=set(sections),
                     section_order=list(sections),
                     proc_order=list(proc_order or []))

    def test_perform_section(self):
        from asg import PerformStmt, SectionJavaVisitor
        from asg.registry import ProcRef
        ctx = self._ctx(sections=["A-SEC"])
        node = PerformStmt(target=ProcRef("A-SEC"), header=["A-SEC"])
        self.assertEqual(SectionJavaVisitor(ctx).visit(node), ["this.p_asec();"])

    def test_perform_single_paragraph_registers_pending(self):
        from asg import PerformStmt, SectionJavaVisitor
        from asg.registry import ProcRef
        proc = [("PARA-X", "paragraph", "S", ["       MOVE 1 TO X."])]
        ctx = self._ctx(proc_order=proc)
        node = PerformStmt(target=ProcRef("PARA-X"), header=["PARA-X"])
        out = "\n".join(SectionJavaVisitor(ctx).visit(node))
        self.assertIn("this.p_parax();", out)
        self.assertEqual(ctx.pending_range_methods["p_parax"], [("PARA-X", ["       MOVE 1 TO X."])])

    def test_perform_paragraph_thru_registers_pending(self):
        from asg import PerformStmt, SectionJavaVisitor
        from asg.registry import ProcRef
        proc = [("PARA-A", "paragraph", "S", ["       MOVE 1 TO X."]),
                ("PARA-B", "paragraph", "S", ["       MOVE 2 TO Y."])]
        ctx = self._ctx(proc_order=proc)
        node = PerformStmt(target=ProcRef("PARA-A"), thru=ProcRef("PARA-B"),
                           header=["PARA-A", "THRU", "PARA-B"])
        out = "\n".join(SectionJavaVisitor(ctx).visit(node))
        self.assertIn("this.p_paraaThruP_parab();", out)
        self.assertEqual(ctx.pending_range_methods["p_paraaThruP_parab"],
                         [("PARA-A", ["       MOVE 1 TO X."]),
                          ("PARA-B", ["       MOVE 2 TO Y."])])


class TestDiffAsgVsLegacySection(unittest.TestCase):
    """步骤24：整程序 SECTION 骨架旧/新两路逐字符一致（不含结构吸收 pass）。"""

    SRC = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. TSECT.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 WS-X PIC 9(02) VALUE 0.\n"
        "       PROCEDURE DIVISION.\n"
        "       1000-MAIN SECTION.\n"
        "       PARA-A.\n"
        "           MOVE 1 TO WS-X.\n"
        "       PARA-B.\n"
        "           IF WS-X = 1\n"
        "               GO TO PARA-A\n"
        "           END-IF.\n"
        "           EXIT.\n"
    )

    def test_legacy_equals_asg_section(self):
        from translator.skeleton_gen.body_context import build_body_ctx
        mod = TestDiffAsgVsLegacy()._harness()
        prog = TestAsgMoveLift()._parse(self.SRC)
        ctx1, _ = build_body_ctx(prog)
        ctx2, _ = build_body_ctx(prog)
        legacy = mod._legacy_sections(prog, ctx1)
        asg = mod._asg_sections(prog, ctx2)
        self.assertEqual(legacy, asg)


class TestAsgBegnForeachRewrite(unittest.TestCase):
    """步骤25：ASG 侧 BEGN+NEXTR 自跳循环 rewrite。"""

    SRC = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. TBEGN.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 WSAA-KEY PIC X(02).\n"
        "       01 WSAA-OUT PIC X(02).\n"
        "       01 ELPO-PARAMS.\n"
        "          03 ELPO-FUNCTION PIC X(05).\n"
        "       PROCEDURE DIVISION.\n"
        "       1000-MAIN SECTION.\n"
        "       SETUP-PARA.\n"
        "           MOVE WSAA-KEY TO ELPO-CHDRNUM.\n"
        "           MOVE BEGN TO ELPO-FUNCTION.\n"
        "       LOOP-PARA.\n"
        "           CALL 'ELPOIO' USING ELPO-PARAMS.\n"
        "           IF ELPO-STATUZ NOT = O-K OR ELPO-CHDRNUM NOT = WSAA-KEY\n"
        "               GO TO EXIT-PARA\n"
        "           END-IF.\n"
        "           MOVE ELPO-DATA TO WSAA-OUT.\n"
        "           MOVE NEXTR TO ELPO-FUNCTION.\n"
        "           GO TO LOOP-PARA.\n"
        "       EXIT-PARA.\n"
        "           EXIT.\n"
    )

    def _program_and_ctx(self):
        from translator.skeleton_gen.body_context import build_body_ctx
        prog = TestAsgMoveLift()._parse(self.SRC)
        ctx, _ = build_body_ctx(prog)
        return prog, ctx

    def test_rewrite_replaces_loop_and_strips_setup(self):
        from asg import build_asg, BegnForeachStmt
        from asg.structure_rewrite import rewrite_begn_foreach
        prog, ctx = self._program_and_ctx()
        sec = build_asg(prog).sections[0]
        rewritten = rewrite_begn_foreach(sec.paragraphs, ctx)
        setup = rewritten[0]
        loop = rewritten[1]
        self.assertEqual(setup.stmts, [])
        self.assertIsInstance(loop.stmts[0], BegnForeachStmt)
        self.assertEqual(loop.stmts[0].pfx, "ELPO")
        self.assertEqual(loop.stmts[0].keys, [("CHDRNUM", "WSAA-KEY")])

    def test_non_adjacent_exit_not_rewritten(self):
        from asg import build_asg, Paragraph, MoveStmt, BegnForeachStmt
        from asg.structure_rewrite import rewrite_begn_foreach
        prog, ctx = self._program_and_ctx()
        sec = build_asg(prog).sections[0]
        paras = list(sec.paragraphs)
        paras.insert(2, Paragraph(label="MIDDLE-PARA",
                                  stmts=[MoveStmt(tokens="MOVE 1 TO WSAA-OUT".split())]))
        rewritten = rewrite_begn_foreach(paras, ctx)
        self.assertFalse(any(isinstance(st, BegnForeachStmt)
                             for para in rewritten for st in para.stmts))


class TestAsgBegnForeachVisitor(unittest.TestCase):
    """步骤25：BEGN foreach 经 SectionJavaVisitor 渲染，并支持 struct_rebind。"""

    def test_legacy_equals_asg_section_begn_foreach(self):
        from translator.skeleton_gen.body_context import build_body_ctx
        mod = TestDiffAsgVsLegacy()._harness()
        prog = TestAsgMoveLift()._parse(TestAsgBegnForeachRewrite.SRC)
        ctx1, _ = build_body_ctx(prog)
        ctx2, _ = build_body_ctx(prog)
        legacy = mod._legacy_sections(prog, ctx1)
        asg = mod._asg_sections(prog, ctx2)
        self.assertEqual(legacy, asg)
        rendered = "\n".join(asg[0][1])
        self.assertIn("List<ElpoRecord> elpoList = elpoRepository.findByChdrnumBegn(wsaaKey);", rendered)
        self.assertIn("for (ElpoRecord elpo : elpoList) {", rendered)
        self.assertIn("wsaaOut = elpo.getData();", rendered)
        self.assertNotIn("setFunction", rendered)


class TestAsgBegnSingleRewrite(unittest.TestCase):
    """步骤26：ASG 侧单次 BEGN rewrite。"""

    SRC = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. TBEG1.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 WSAA-KEY PIC X(02).\n"
        "       01 WSAA-OUT PIC X(02).\n"
        "       01 ELPO-PARAMS.\n"
        "          03 ELPO-FUNCTION PIC X(05).\n"
        "       PROCEDURE DIVISION.\n"
        "       1000-MAIN SECTION.\n"
        "       SINGLE-PARA.\n"
        "           MOVE SPACES TO ELPO-PARAMS.\n"
        "           MOVE WSAA-KEY TO ELPO-CHDRNUM.\n"
        "           MOVE BEGN TO ELPO-FUNCTION.\n"
        "           CALL 'ELPOIO' USING ELPO-PARAMS.\n"
        "           IF ELPO-STATUZ NOT = O-K OR ELPO-CHDRNUM NOT = WSAA-KEY\n"
        "               MOVE 1 TO WSAA-OUT\n"
        "           END-IF.\n"
        "           MOVE 2 TO WSAA-OUT.\n"
    )

    def _program_and_ctx(self):
        from translator.skeleton_gen.body_context import build_body_ctx
        prog = TestAsgMoveLift()._parse(self.SRC)
        ctx, _ = build_body_ctx(prog)
        return prog, ctx

    def test_rewrite_inserts_begn_single_preserves_after(self):
        from asg import build_asg, BegnSingleStmt, MoveStmt
        from asg.structure_rewrite import rewrite_begn_single
        prog, ctx = self._program_and_ctx()
        sec = build_asg(prog).sections[0]
        rewritten = rewrite_begn_single(sec.paragraphs, ctx)
        stmts = rewritten[0].stmts
        self.assertIsInstance(stmts[0], BegnSingleStmt)
        self.assertEqual(stmts[0].keys, [("CHDRNUM", "WSAA-KEY")])
        self.assertIsInstance(stmts[1], MoveStmt)
        self.assertEqual(stmts[1].tokens[:2], ["MOVE", "2"])

    def test_then_with_goto_not_rewritten(self):
        from asg import build_asg, GotoStmt, BegnSingleStmt
        from asg.registry import ProcRef
        from asg.structure_rewrite import rewrite_begn_single
        prog, ctx = self._program_and_ctx()
        sec = build_asg(prog).sections[0]
        if_node = sec.paragraphs[0].stmts[4]
        if_node.then = [GotoStmt(target=ProcRef("EXIT-PARA"), tokens="GO TO EXIT-PARA".split())]
        rewritten = rewrite_begn_single(sec.paragraphs, ctx)
        self.assertFalse(any(isinstance(st, BegnSingleStmt)
                             for para in rewritten for st in para.stmts))


class TestAsgBegnSingleVisitor(unittest.TestCase):
    """步骤26：单次 BEGN 经 SectionJavaVisitor 渲染，并与旧路逐字符一致。"""

    def test_legacy_equals_asg_section_begn_single(self):
        from translator.skeleton_gen.body_context import build_body_ctx
        mod = TestDiffAsgVsLegacy()._harness()
        prog = TestAsgMoveLift()._parse(TestAsgBegnSingleRewrite.SRC)
        ctx1, _ = build_body_ctx(prog)
        ctx2, _ = build_body_ctx(prog)
        legacy = mod._legacy_sections(prog, ctx1)
        asg = mod._asg_sections(prog, ctx2)
        self.assertEqual(legacy, asg)
        rendered = "\n".join(asg[0][1])
        self.assertIn("List<ElpoRecord> elpoList = elpoRepository.findByChdrnumBegn(wsaaKey);", rendered)
        self.assertIn("if (elpoList.isEmpty()) {", rendered)
        self.assertIn("wsaaOut = 1;", rendered)
        self.assertIn("wsaaOut = 2;", rendered)


class TestAsgReadrSingleRewrite(unittest.TestCase):
    """步骤27：ASG 侧 READR/READS 单条读 rewrite。"""

    SRC_OK = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. TREAD.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 WSAA-KEY PIC X(02).\n"
        "       01 WSAA-OUT PIC X(02).\n"
        "       01 ELPO-PARAMS.\n"
        "          03 ELPO-FUNCTION PIC X(05).\n"
        "       PROCEDURE DIVISION.\n"
        "       1000-MAIN SECTION.\n"
        "       READ-PARA.\n"
        "           MOVE SPACES TO ELPO-PARAMS.\n"
        "           MOVE WSAA-KEY TO ELPO-CHDRNUM.\n"
        "           MOVE READR TO ELPO-FUNCTION.\n"
        "           CALL 'ELPOIO' USING ELPO-PARAMS.\n"
        "           IF ELPO-STATUZ = O-K\n"
        "               MOVE ELPO-DATA TO WSAA-OUT\n"
        "           END-IF.\n"
    )

    SRC_ERROR = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. TRERR.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 WSAA-KEY PIC X(02).\n"
        "       01 WSAA-OUT PIC X(02).\n"
        "       01 ITDM-PARAMS.\n"
        "          03 ITDM-FUNCTION PIC X(05).\n"
        "       PROCEDURE DIVISION.\n"
        "       1000-MAIN SECTION.\n"
        "       READ-PARA.\n"
        "           MOVE SPACES TO ITDM-PARAMS.\n"
        "           MOVE WSAA-KEY TO ITDM-ITEMKEY.\n"
        "           MOVE READR TO ITDM-FUNCTION.\n"
        "           CALL 'ITDMIO' USING ITDM-PARAMS.\n"
        "           IF ITDM-STATUZ NOT = O-K AND ITDM-STATUZ NOT = ENDP\n"
        "               PERFORM 580-DB-ERROR\n"
        "           END-IF.\n"
        "           MOVE ITDM-VALUE TO WSAA-OUT.\n"
        "       580-DB-ERROR SECTION.\n"
        "           EXIT.\n"
    )

    def _program_and_ctx(self, src):
        from translator.skeleton_gen.body_context import build_body_ctx
        prog = TestAsgMoveLift()._parse(src)
        ctx, _ = build_body_ctx(prog)
        return prog, ctx

    def test_rewrite_ok_mode(self):
        from asg import build_asg, IoReadSingleStmt
        from asg.structure_rewrite import rewrite_readr_single
        prog, ctx = self._program_and_ctx(self.SRC_OK)
        sec = build_asg(prog).sections[0]
        rewritten = rewrite_readr_single(sec.paragraphs, ctx)
        stmt = rewritten[0].stmts[0]
        self.assertIsInstance(stmt, IoReadSingleStmt)
        self.assertEqual(stmt.mode, "ok")
        self.assertEqual(stmt.keys, [("CHDRNUM", "WSAA-KEY")])

    def test_rewrite_error_mode_consumes_tail(self):
        from asg import build_asg, IoReadSingleStmt
        from asg.structure_rewrite import rewrite_readr_single
        prog, ctx = self._program_and_ctx(self.SRC_ERROR)
        sec = build_asg(prog).sections[0]
        rewritten = rewrite_readr_single(sec.paragraphs, ctx)
        stmt = rewritten[0].stmts[0]
        self.assertIsInstance(stmt, IoReadSingleStmt)
        self.assertEqual(stmt.mode, "error")
        self.assertTrue(stmt.try_tail)
        self.assertEqual(len(rewritten[0].stmts), 1)

    def test_unknown_statuz_not_rewritten(self):
        from asg import build_asg, IoReadSingleStmt
        from asg.structure_rewrite import rewrite_readr_single
        src = self.SRC_OK.replace("IF ELPO-STATUZ = O-K", "IF ELPO-STATUZ = WEIRD")
        prog, ctx = self._program_and_ctx(src)
        sec = build_asg(prog).sections[0]
        rewritten = rewrite_readr_single(sec.paragraphs, ctx)
        self.assertFalse(any(isinstance(st, IoReadSingleStmt)
                             for para in rewritten for st in para.stmts))


class TestAsgReadrSingleVisitor(unittest.TestCase):
    """步骤27：READR 单条读经 SectionJavaVisitor 渲染，并与旧路逐字符一致。"""

    def test_legacy_equals_asg_section_readr_ok(self):
        from translator.skeleton_gen.body_context import build_body_ctx
        mod = TestDiffAsgVsLegacy()._harness()
        prog = TestAsgMoveLift()._parse(TestAsgReadrSingleRewrite.SRC_OK)
        ctx1, _ = build_body_ctx(prog)
        ctx2, _ = build_body_ctx(prog)
        legacy = mod._legacy_sections(prog, ctx1)
        asg = mod._asg_sections(prog, ctx2)
        self.assertEqual(legacy, asg)
        rendered = "\n".join(asg[0][1])
        self.assertIn("ElpoRecord elpo = elpoRepository.findByChdrnumReadr(wsaaKey);", rendered)
        self.assertIn("if (elpo != null) {", rendered)
        self.assertIn("wsaaOut = elpo.getData();", rendered)

    def test_legacy_equals_asg_section_readr_error(self):
        from translator.skeleton_gen.body_context import build_body_ctx
        mod = TestDiffAsgVsLegacy()._harness()
        prog = TestAsgMoveLift()._parse(TestAsgReadrSingleRewrite.SRC_ERROR)
        ctx1, _ = build_body_ctx(prog)
        ctx2, _ = build_body_ctx(prog)
        legacy = mod._legacy_sections(prog, ctx1)
        asg = mod._asg_sections(prog, ctx2)
        self.assertEqual(legacy, asg)
        rendered = "\n".join(asg[0][1])
        self.assertIn("try {", rendered)
        self.assertIn("ItdmRecord itdm = itdmRepository.findByItemkeyReadr(wsaaKey);", rendered)
        self.assertIn("} catch (Exception e) {", rendered)
        self.assertIn("wsaaOut = itdm.getValue();", rendered)


class TestAsgWriteSingleRewrite(unittest.TestCase):
    """步骤28：ASG 侧 UPDAT/WRITR/DELET 单条写 IO rewrite。"""

    SRC_WRITR = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. TWRIT.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 WSAA-VAL PIC X(02).\n"
        "       01 TMLCLST-PARAMS.\n"
        "          03 TMLCLST-FUNCTION PIC X(05).\n"
        "       PROCEDURE DIVISION.\n"
        "       1000-MAIN SECTION.\n"
        "       WRITE-PARA.\n"
        "           MOVE SPACES TO TMLCLST-PARAMS.\n"
        "           MOVE WSAA-VAL TO TMLCLST-FIELD.\n"
        "           MOVE WRITR TO TMLCLST-FUNCTION.\n"
        "           CALL 'TMLCLSTIO' USING TMLCLST-PARAMS.\n"
    )

    SRC_UPDAT_ERROR = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. TUPDT.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 WSAA-NEW-VALUE PIC X(02).\n"
        "       01 WSAA-OUT PIC X(02).\n"
        "       01 TMLCLST-PARAMS.\n"
        "          03 TMLCLST-FUNCTION PIC X(05).\n"
        "       PROCEDURE DIVISION.\n"
        "       1000-MAIN SECTION.\n"
        "       UPDATE-PARA.\n"
        "           MOVE WSAA-NEW-VALUE TO TMLCLST-FIELD.\n"
        "           MOVE UPDAT TO TMLCLST-FUNCTION.\n"
        "           CALL 'TMLCLSTIO' USING TMLCLST-PARAMS.\n"
        "           IF TMLCLST-STATUZ NOT = O-K\n"
        "               PERFORM 9999-FATAL-ERROR\n"
        "           END-IF.\n"
        "           MOVE TMLCLST-FIELD TO WSAA-OUT.\n"
        "       9999-FATAL-ERROR SECTION.\n"
        "           EXIT.\n"
    )

    SRC_DELET = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. TDELT.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 TMLCLST-PARAMS.\n"
        "          03 TMLCLST-FUNCTION PIC X(05).\n"
        "       PROCEDURE DIVISION.\n"
        "       1000-MAIN SECTION.\n"
        "       DELETE-PARA.\n"
        "           MOVE DELET TO TMLCLST-FUNCTION.\n"
        "           CALL 'TMLCLSTIO' USING TMLCLST-PARAMS.\n"
    )

    @staticmethod
    def _install_write_ops(ctx):
        ctx.io_default_pattern = {
            "class_suffix": "Repository",
            "field_suffix": "Repository",
            "param_struct_suffix": "-PARAMS",
            "import_package": "com.example.repository",
            "operations": {
                "READR": "findByKeyReadr({key})",
                "UPDAT": "save({entity})",
                "WRITR": "save({entity})",
                "DELET": "delete({entity})",
            },
        }
        ctx.io_struct_prefixes.add("TMLCLST")
        return ctx

    def _program_and_ctx(self, src):
        from translator.skeleton_gen.body_context import build_body_ctx
        prog = TestAsgMoveLift()._parse(src)
        ctx, _ = build_body_ctx(prog)
        return prog, self._install_write_ops(ctx)

    def test_rewrite_writr_new_plain(self):
        from asg import build_asg, IoWriteSingleStmt
        from asg.structure_rewrite import rewrite_write_single
        prog, ctx = self._program_and_ctx(self.SRC_WRITR)
        sec = build_asg(prog).sections[0]
        rewritten = rewrite_write_single(sec.paragraphs, ctx)
        stmt = rewritten[0].stmts[0]
        self.assertIsInstance(stmt, IoWriteSingleStmt)
        self.assertTrue(stmt.is_new)
        self.assertFalse(stmt.is_delete)
        self.assertEqual(stmt.mode, "plain")
        self.assertEqual(len(stmt.setters), 1)

    def test_rewrite_updat_error_consumes_tail(self):
        from asg import build_asg, IoWriteSingleStmt
        from asg.structure_rewrite import rewrite_write_single
        prog, ctx = self._program_and_ctx(self.SRC_UPDAT_ERROR)
        sec = build_asg(prog).sections[0]
        rewritten = rewrite_write_single(sec.paragraphs, ctx)
        stmt = rewritten[0].stmts[0]
        self.assertIsInstance(stmt, IoWriteSingleStmt)
        self.assertFalse(stmt.is_new)
        self.assertEqual(stmt.mode, "error")
        self.assertTrue(stmt.try_tail)
        self.assertEqual(len(rewritten[0].stmts), 1)

    def test_rewrite_delet_delete_mode(self):
        from asg import build_asg, IoWriteSingleStmt
        from asg.structure_rewrite import rewrite_write_single
        prog, ctx = self._program_and_ctx(self.SRC_DELET)
        sec = build_asg(prog).sections[0]
        rewritten = rewrite_write_single(sec.paragraphs, ctx)
        stmt = rewritten[0].stmts[0]
        self.assertIsInstance(stmt, IoWriteSingleStmt)
        self.assertTrue(stmt.is_delete)

    def test_unknown_statuz_not_rewritten(self):
        from asg import build_asg, IoWriteSingleStmt
        from asg.structure_rewrite import rewrite_write_single
        src = self.SRC_UPDAT_ERROR.replace("IF TMLCLST-STATUZ NOT = O-K", "IF TMLCLST-STATUZ = WEIRD")
        prog, ctx = self._program_and_ctx(src)
        sec = build_asg(prog).sections[0]
        rewritten = rewrite_write_single(sec.paragraphs, ctx)
        self.assertFalse(any(isinstance(st, IoWriteSingleStmt)
                             for para in rewritten for st in para.stmts))


class TestAsgWriteSingleVisitor(unittest.TestCase):
    """步骤28：写 IO 经 SectionJavaVisitor 渲染，并与旧路线逐字符串一致。"""

    def _sections(self, src):
        from translator.skeleton_gen.body_context import build_body_ctx
        mod = TestDiffAsgVsLegacy()._harness()
        prog = TestAsgMoveLift()._parse(src)
        ctx1, _ = build_body_ctx(prog)
        ctx2, _ = build_body_ctx(prog)
        TestAsgWriteSingleRewrite._install_write_ops(ctx1)
        TestAsgWriteSingleRewrite._install_write_ops(ctx2)
        return mod._legacy_sections(prog, ctx1), mod._asg_sections(prog, ctx2)

    def test_legacy_equals_asg_section_writr_new(self):
        legacy, asg = self._sections(TestAsgWriteSingleRewrite.SRC_WRITR)
        self.assertEqual(legacy, asg)
        rendered = "\n".join(asg[0][1])
        self.assertIn("TmlclstRecord tmlclst = new TmlclstRecord();", rendered)
        self.assertIn("tmlclst.setField(wsaaVal);", rendered)
        self.assertIn("tmlclstRepository.save(tmlclst);", rendered)

    def test_legacy_equals_asg_section_updat_error(self):
        legacy, asg = self._sections(TestAsgWriteSingleRewrite.SRC_UPDAT_ERROR)
        self.assertEqual(legacy, asg)
        rendered = "\n".join(asg[0][1])
        self.assertIn("try {", rendered)
        self.assertIn("tmlclstRepository.save(tmlclst);", rendered)
        self.assertIn("} catch (Exception e) {", rendered)
        self.assertIn("this.fatalError9999();", rendered)
        self.assertIn("wsaaOut = tmlclst.getField();", rendered)

    def test_legacy_equals_asg_section_delet(self):
        legacy, asg = self._sections(TestAsgWriteSingleRewrite.SRC_DELET)
        self.assertEqual(legacy, asg)
        rendered = "\n".join(asg[0][1])
        self.assertIn("tmlclstRepository.delete(tmlclst);", rendered)
        self.assertNotIn("deleteByKey", rendered)


class TestMainlineSectionViaAsg(unittest.TestCase):
    """步骤29：主线 translate_section_body / pending range 默认走 SectionJavaVisitor。"""

    SRC_SIMPLE = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. TMAIN.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 WSAA-OUT PIC X(02).\n"
        "       PROCEDURE DIVISION.\n"
        "       1000-MAIN SECTION.\n"
        "       MAIN-PARA.\n"
        "           MOVE 1 TO WSAA-OUT.\n"
    )

    def _program(self, src):
        return TestAsgMoveLift()._parse(src)

    def _known_methods(self, prog, ctx):
        return {ctx.section_to_method(s.name.upper()) for s in prog.sections}

    def _legacy_body(self, prog, ctx, ws_fields, section_index=0):
        from translator.segmenter import split_paragraphs
        from translator.skeleton_gen import body_context as bc
        sec = prog.sections[section_index]
        return bc._translate_paragraphs_body_legacy(
            split_paragraphs(sec.lines), ctx, ws_fields, "", self._known_methods(prog, ctx)
        )

    def _mainline_body(self, prog, ctx, ws_fields, section_index=0):
        from translator.skeleton_gen.body_context import translate_section_body
        sec = prog.sections[section_index]
        return translate_section_body(sec.lines, ctx, ws_fields, "", self._known_methods(prog, ctx))

    def test_mainline_section_matches_legacy_for_plain_section(self):
        from translator.skeleton_gen.body_context import build_body_ctx
        prog = self._program(self.SRC_SIMPLE)
        ctx1, ws1 = build_body_ctx(prog)
        ctx2, ws2 = build_body_ctx(prog)
        self.assertEqual(self._legacy_body(prog, ctx1, ws1), self._mainline_body(prog, ctx2, ws2))

    def test_mainline_uses_asg_without_calling_legacy(self):
        from translator.skeleton_gen import body_context as bc
        prog = self._program(self.SRC_SIMPLE)
        ctx, ws = bc.build_body_ctx(prog)
        original = bc._translate_paragraphs_body_legacy

        def _boom(*_args, **_kwargs):
            raise AssertionError("legacy path should not be called")

        bc._translate_paragraphs_body_legacy = _boom
        try:
            body = self._mainline_body(prog, ctx, ws)
        finally:
            bc._translate_paragraphs_body_legacy = original
        self.assertIn("wsaa.wsaaOut = 1;", body)

    def test_mainline_write_io_structure_absorption(self):
        from translator.skeleton_gen.body_context import build_body_ctx
        prog = self._program(TestAsgWriteSingleRewrite.SRC_WRITR)
        ctx, ws = build_body_ctx(prog)
        TestAsgWriteSingleRewrite._install_write_ops(ctx)
        body = self._mainline_body(prog, ctx, ws)
        self.assertIn("TmlclstRecord tmlclst = new TmlclstRecord();", body)
        self.assertIn("tmlclst.setField(wsaa.wsaaVal);", body)
        self.assertIn("tmlclstRepository.save(tmlclst);", body)

    def test_asg_failure_falls_back_to_legacy(self):
        from translator.segmenter import split_paragraphs
        from translator.skeleton_gen import body_context as bc
        prog = self._program(self.SRC_SIMPLE)
        ctx1, ws1 = bc.build_body_ctx(prog)
        ctx2, ws2 = bc.build_body_ctx(prog)
        paras = split_paragraphs(prog.sections[0].lines)
        expected = bc._translate_paragraphs_body_legacy(paras, ctx1, ws1, "", self._known_methods(prog, ctx1))
        original = bc._translate_paragraphs_body_asg

        def _boom(*_args, **_kwargs):
            raise RuntimeError("forced ASG failure")

        bc._translate_paragraphs_body_asg = _boom
        try:
            actual = bc.translate_paragraphs_body(paras, ctx2, ws2, "", self._known_methods(prog, ctx2))
        finally:
            bc._translate_paragraphs_body_asg = original
        self.assertEqual(expected, actual)

    def test_legacy_fallback_helper_is_explicit_reference_wrapper(self):
        from translator.segmenter import split_paragraphs
        from translator.skeleton_gen import body_context as bc
        prog = self._program(self.SRC_SIMPLE)
        ctx1, ws1 = bc.build_body_ctx(prog)
        ctx2, ws2 = bc.build_body_ctx(prog)
        paras = split_paragraphs(prog.sections[0].lines)
        expected = bc._translate_paragraphs_body_legacy(paras, ctx1, ws1, "", self._known_methods(prog, ctx1))
        actual = bc._translate_paragraphs_body_legacy_fallback(
            paras, ctx2, ws2, "", self._known_methods(prog, ctx2)
        )
        self.assertEqual(expected, actual)


class TestMainlinePendingRangeViaAsg(unittest.TestCase):
    """步骤29：pending THRU 合成区间方法也经 ASG paragraph 入口渲染。"""

    def _ctx(self, proc_order):
        import translator.rules as r
        return r.Ctx(field_type_map={}, section_to_method=lambda s: "p_" + s.replace("-", "").lower(),
                     known_sections=set(), section_order=[], proc_order=list(proc_order))

    def test_pending_range_force_sm_matches_legacy(self):
        import translator.rules as r
        from translator.skeleton_gen import body_context as bc
        proc = [("PARA-A", "paragraph", "S", ["       GO TO PARA-C."]),
                ("PARA-B", "paragraph", "S", ["       MOVE 9 TO WS-Y."]),
                ("PARA-C", "paragraph", "S", ["       MOVE 3 TO WS-Z."])]
        ctx_legacy = self._ctx(proc)
        r._perform_range(["PARA-A", "THRU", "PARA-C"], ["PARA-A", "THRU", "PARA-C"], "PARA-A", ctx_legacy, 0)
        expected = {
            name: bc._translate_paragraphs_body_legacy(paras, ctx_legacy, [], "", set(), force_sm=True)
            for name, paras in dict(ctx_legacy.pending_range_methods).items()
        }

        ctx_asg = self._ctx(proc)
        r._perform_range(["PARA-A", "THRU", "PARA-C"], ["PARA-A", "THRU", "PARA-C"], "PARA-A", ctx_asg, 0)
        actual = bc.render_pending_range_methods(ctx_asg, ws_field_names=[], call_args="", known_methods=set())
        self.assertEqual(expected, actual)
        body = "\n".join(actual.values())
        self.assertIn("switch (__pc)", body)
        self.assertIn('__pc = "PARA-C"; continue FLOW;', body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
