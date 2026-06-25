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
        # 区间内三单元体按 proc_order 序拼接（不丢中间 PARA-M）
        self.assertEqual(ctx.pending_range_methods[mname],
                         ["  MOVE 1 TO X", "  MOVE 2 TO Y", "  MOVE 3 TO Z"])

    def test_thru_paragraph_range_cross_section(self):
        """跨 SECTION 的 paragraph 区间（D2）：proc_order 含 SECTION 头单元，区间天然覆盖、不丢。"""
        proc = [("S1", "section", "S1", []),
                ("PARA-A", "paragraph", "S1", ["  A"]),
                ("S2", "section", "S2", ["  SHDR"]),
                ("PARA-B", "paragraph", "S2", ["  B"])]
        ctx = self._pctx(proc)
        out = "\n".join(self._prange(["PARA-A", "THRU", "PARA-B"], ctx))
        self.assertIn("this.p_paraaThruP_parab();", out)
        self.assertEqual(ctx.pending_range_methods["p_paraaThruP_parab"], ["  A", "  SHDR", "  B"])

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
