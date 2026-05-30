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

    def test_io_call_runtime_dispatch(self):
        """功能码静态拿不到 → 运行时分发 execute(obj.getFunction(), obj)。"""
        ctx = self._ctx()  # struct_function 为空
        lines, matched = self.rules.translate_leaf(
            self._leaf("CALL 'ELPOIO' USING ELPO-PARAMS"), ctx)
        self.assertTrue(matched)
        self.assertEqual(
            lines,
            ["elpoParams = elpoRepository.execute(elpoParams.getFunction(), elpoParams);"])

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
        """MOVE 结构体→结构体 是拷贝赋值，不是 new（修复的 bug）。"""
        ctx = self._ctx()
        lines, matched = self.rules.translate_leaf(
            self._leaf("MOVE ELPO-PARAMS TO SYSR-PARAMS"), ctx)
        self.assertTrue(matched)
        self.assertEqual(lines, ["sysrParams = elpoParams;"])

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
