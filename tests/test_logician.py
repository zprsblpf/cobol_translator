"""
逻辑文档生成器 — 单元测试。

覆盖：
- 词元提取（每 ASG 节点类型）
- 结果叶子识别
- 路径追踪（minimal.cob 端到端）
- JSON / Markdown 输出
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest

from asg import nodes
from logician.models import (
    LogicDoc, LogicNode, LogicEdge, LogicPath, ResultLeaf, IOCall,
)
from logician.tokens import (
    extract_tokens, extract_io_call, expand_88_condition,
    SEM_ASSIGN, SEM_RESET, SEM_FUNC_SET,
    SEM_BRANCH_IF, SEM_BRANCH_SWITCH,
    SEM_CALL_PROC, SEM_LOOP, SEM_CALL_PROG,
    SEM_JUMP, SEM_RETURN,
    SEM_DB_READR, SEM_DB_BEGN, SEM_DB_WRITR, SEM_DB_UPDAT, SEM_DB_DELET,
    SEM_MATH, SEM_TEXT_OP, SEM_SEARCH, SEM_FATAL, SEM_UNRESOLVED,
)
from logician.results import find_results
from logician.output.json_output import to_dict, save as save_json
from logician.output.md_output import render as render_md


# ── 词元提取测试 ──────────────────────────────────────────────────────────

class TestTokens(unittest.TestCase):
    """测试每类 ASG 节点的词元提取。"""

    def test_move_assign(self):
        """MOVE A TO B → ASSIGN"""
        stmt = nodes.MoveStmt(tokens=["MOVE", "A", "TO", "B"])
        sem, verb = extract_tokens(stmt)
        self.assertEqual([SEM_ASSIGN], sem)
        self.assertEqual(["MOVE"], verb)

    def test_move_reset(self):
        """MOVE SPACES TO WS-STRUCT → RESET"""
        stmt = nodes.MoveStmt(tokens=["MOVE", "SPACES", "TO", "WS-STRUCT"])
        sem, verb = extract_tokens(stmt)
        self.assertEqual([SEM_RESET], sem)

    def test_move_func_set(self):
        """MOVE READR TO XXX-FUNCTION → FUNC_SET"""
        stmt = nodes.MoveStmt(tokens=["MOVE", "READR", "TO", "TMLCLST-FUNCTION"])
        sem, verb = extract_tokens(stmt)
        self.assertEqual([SEM_FUNC_SET], sem)

    def test_call_io_readr(self):
        """CALL 'TMLCLSTIO' + READR → DB_READR"""
        stmt = nodes.CallStmt(
            name="TMLCLSTIO",
            tokens=["CALL", "'TMLCLSTIO'", "USING", "TMLCLST-PARAMS"],
        )
        sem, verb = extract_tokens(stmt)
        self.assertEqual([SEM_CALL_PROG], sem)  # 原始 CallStmt 没有 FUNCTION 信息
        self.assertEqual(["CALL"], verb)

    def test_if_branch(self):
        """IF cond → BRANCH_IF"""
        stmt = nodes.IfStmt(cond=["A", "=", "1"])
        sem, verb = extract_tokens(stmt)
        self.assertEqual([SEM_BRANCH_IF], sem)
        self.assertEqual(["IF"], verb)

    def test_evaluate_switch(self):
        """EVALUATE → BRANCH_SWITCH"""
        stmt = nodes.EvaluateStmt(subject=["A"])
        sem, verb = extract_tokens(stmt)
        self.assertEqual([SEM_BRANCH_SWITCH], sem)
        self.assertEqual(["EVALUATE"], verb)

    def test_perform_call_proc(self):
        """PERFORM section → CALL_PROC"""
        stmt = nodes.PerformStmt(target=nodes.ProcRef(name="1000-INIT"))
        sem, verb = extract_tokens(stmt)
        self.assertEqual([SEM_CALL_PROC], sem)
        self.assertEqual(["PERFORM"], verb)

    def test_perform_loop(self):
        """PERFORM inline loop → LOOP"""
        stmt = nodes.PerformStmt(
            header=["VARYING", "I"],
            inline_body=[nodes.MoveStmt(tokens=["MOVE", "I", "TO", "J"])],
        )
        sem, verb = extract_tokens(stmt)
        self.assertEqual([SEM_LOOP], sem)
        self.assertEqual(["PERFORM"], verb)

    def test_goto_jump(self):
        """GO TO → JUMP"""
        stmt = nodes.GotoStmt(target=nodes.ProcRef(name="1090-EXIT"))
        sem, verb = extract_tokens(stmt)
        self.assertEqual([SEM_JUMP], sem)
        self.assertEqual(["GO"], verb)

    def test_leaf_exit_return(self):
        """EXIT → RETURN"""
        stmt = nodes.Leaf(tokens=["EXIT"])
        sem, verb = extract_tokens(stmt)
        self.assertEqual([SEM_RETURN], sem)
        self.assertEqual(["EXIT"], verb)

    def test_leaf_goback_return(self):
        """GOBACK → RETURN"""
        stmt = nodes.Leaf(tokens=["GOBACK"])
        sem, verb = extract_tokens(stmt)
        self.assertEqual([SEM_RETURN], sem)
        self.assertEqual(["GOBACK"], verb)

    def test_leaf_math(self):
        """ADD → MATH"""
        stmt = nodes.Leaf(tokens=["ADD", "1", "TO", "X"])
        sem, verb = extract_tokens(stmt)
        self.assertEqual([SEM_MATH], sem)
        self.assertEqual(["ADD"], verb)

    def test_leaf_string_text_op(self):
        """STRING → TEXT_OP"""
        stmt = nodes.Leaf(tokens=["STRING", "A", "DELIMITED", "BY", "SIZE"])
        sem, verb = extract_tokens(stmt)
        self.assertEqual([SEM_TEXT_OP], sem)
        self.assertEqual(["STRING"], verb)

    def test_leaf_unresolved(self):
        """未知动词 → UNRESOLVED"""
        stmt = nodes.Leaf(tokens=["SOME-VERB", "X", "Y"])
        sem, verb = extract_tokens(stmt)
        self.assertEqual([SEM_UNRESOLVED], sem)
        self.assertEqual(["SOME-VERB"], verb)

    def test_io_write_single(self):
        """IoWriteSingleStmt → DB_WRITR"""
        stmt = nodes.IoWriteSingleStmt(func="WRITR", name="TMRDPF")
        sem, verb = extract_tokens(stmt)
        self.assertEqual([SEM_DB_WRITR], sem)
        self.assertEqual(["WRITR"], verb)

    def test_begn_foreach(self):
        """BegnForeachStmt → DB_BEGN"""
        stmt = nodes.BegnForeachStmt(name="TMLCLST")
        sem, verb = extract_tokens(stmt)
        self.assertEqual([SEM_DB_BEGN], sem)
        self.assertEqual(["BEGN"], verb)

    def test_raw_returns_empty(self):
        """Raw 节点不产生词元"""
        stmt = nodes.Raw(lines=["someJavaLine();"])
        sem, verb = extract_tokens(stmt)
        self.assertEqual([], sem)
        self.assertEqual([], verb)


# ── IO 调用提取测试 ──────────────────────────────────────────────────────

class TestExtractIoCall(unittest.TestCase):
    """测试从 ASG 节点提取 IO 调用信息。"""

    def test_io_write_extracts_call(self):
        stmt = nodes.IoWriteSingleStmt(func="WRITR", name="TMRDPF", raw="CALL 'TMRDPFIO'")
        io = extract_io_call(stmt)
        self.assertIsNotNone(io)
        self.assertEqual("WRITR", io.func)
        self.assertEqual("TMRDPF", io.table)

    def test_begn_foreach_extracts_call(self):
        stmt = nodes.BegnForeachStmt(name="TMLCLST")
        io = extract_io_call(stmt)
        self.assertIsNotNone(io)
        self.assertEqual("BEGN", io.func)
        self.assertEqual("TMLCLST", io.table)

    def test_non_io_node_returns_none(self):
        stmt = nodes.MoveStmt(tokens=["MOVE", "A", "TO", "B"])
        io = extract_io_call(stmt)
        self.assertIsNone(io)


# ── 结果叶子识别测试 ──────────────────────────────────────────────────────

class TestResults(unittest.TestCase):
    """测试结果叶子识别。"""

    def _make_program(self, stmts_in_section: list, sec_name: str = "1000-TEST") -> nodes.Program:
        """构造一个简单的 ASG Program 用于测试。"""
        para = nodes.Paragraph(label=sec_name, stmts=stmts_in_section)
        sec = nodes.Section(name=sec_name, paragraphs=[para])
        return nodes.Program(program_id="TEST", sections=[sec])

    def test_writr_is_table_insert(self):
        """WRITR → table_insert"""
        stmts = [nodes.IoWriteSingleStmt(func="WRITR", name="TMRDPF")]
        prog = self._make_program(stmts)
        results = find_results(prog)
        self.assertEqual(1, len(results))
        self.assertEqual("table_insert", results[0].kind)
        self.assertEqual("TMRDPF", results[0].target)

    def test_updat_is_table_update(self):
        """UPDAT → table_update"""
        stmts = [nodes.IoWriteSingleStmt(func="UPDAT", name="HREPTRD")]
        prog = self._make_program(stmts)
        results = find_results(prog)
        self.assertEqual(1, len(results))
        self.assertEqual("table_update", results[0].kind)
        self.assertEqual("HREPTRD", results[0].target)

    def test_delet_is_table_delete(self):
        """DELET → table_delete"""
        stmts = [nodes.IoWriteSingleStmt(func="DELET", name="TMLCLST")]
        prog = self._make_program(stmts)
        results = find_results(prog)
        self.assertEqual(1, len(results))
        self.assertEqual("table_delete", results[0].kind)
        self.assertEqual("TMLCLST", results[0].target)

    def test_exit_is_return(self):
        """EXIT → return"""
        stmts = [nodes.Leaf(tokens=["EXIT"])]
        prog = self._make_program(stmts)
        results = find_results(prog)
        self.assertEqual(1, len(results))
        self.assertEqual("return", results[0].kind)

    def test_goback_is_return(self):
        """GOBACK → return"""
        stmts = [nodes.Leaf(tokens=["GOBACK"])]
        prog = self._make_program(stmts)
        results = find_results(prog)
        self.assertEqual(1, len(results))
        self.assertEqual("return", results[0].kind)

    def test_stop_run_is_return(self):
        """STOP RUN → return"""
        stmts = [nodes.Leaf(tokens=["STOP", "RUN"])]
        prog = self._make_program(stmts)
        results = find_results(prog)
        self.assertEqual(1, len(results))
        self.assertEqual("return", results[0].kind)

    def test_call_error_is_abend(self):
        """CALL 'xxxERROR' → abend"""
        stmts = [nodes.CallStmt(name="TMTFERROR")]
        prog = self._make_program(stmts)
        results = find_results(prog)
        self.assertEqual(1, len(results))
        self.assertEqual("abend", results[0].kind)

    def test_perform_error_section_is_abend(self):
        """PERFORM 5xx-ERROR → abend"""
        stmts = [nodes.PerformStmt(target=nodes.ProcRef(name="500-ERROR"))]
        prog = self._make_program(stmts)
        results = find_results(prog)
        self.assertEqual(1, len(results))
        self.assertEqual("abend", results[0].kind)

    def test_goto_exit_is_return(self):
        """GO TO xxx-EXIT → return"""
        stmts = [nodes.GotoStmt(target=nodes.ProcRef(name="1090-EXIT"))]
        prog = self._make_program(stmts)
        results = find_results(prog)
        self.assertEqual(1, len(results))
        self.assertEqual("return", results[0].kind)

    def test_no_result_when_no_op(self):
        """无相关语句 → 空结果"""
        stmts = [nodes.MoveStmt(tokens=["MOVE", "A", "TO", "B"])]
        prog = self._make_program(stmts)
        results = find_results(prog)
        self.assertEqual(0, len(results))

    def test_multiple_results(self):
        """多结果识别"""
        stmts = [
            nodes.IoWriteSingleStmt(func="WRITR", name="TMRDPF"),
            nodes.IoWriteSingleStmt(func="UPDAT", name="HREPTRD"),
        ]
        prog = self._make_program(stmts)
        results = find_results(prog)
        self.assertEqual(2, len(results))
        kinds = {r.kind for r in results}
        self.assertIn("table_insert", kinds)
        self.assertIn("table_update", kinds)


# ── JSON 输出测试 ────────────────────────────────────────────────────────

class TestJsonOutput(unittest.TestCase):
    """测试 JSON 序列化。"""

    def test_to_dict_basic(self):
        """LogicDoc → dict，含主要字段"""
        doc = LogicDoc(
            program_id="TEST",
            entry=LogicNode(node_id="ENTRY", type="entry", label="1000-MAIN"),
            results=[ResultLeaf(id="R-01", kind="return", target="GOBACK", section="2000-DONE")],
            paths=[LogicPath(path_id="PATH-01", result_id="R-01")],
        )
        d = to_dict(doc)
        self.assertEqual("TEST", d["program_id"])
        self.assertIn("entry", d)
        self.assertIn("results", d)
        self.assertIn("paths", d)

    def test_save_and_load(self):
        """保存 JSON 后读回，字段完整"""
        doc = LogicDoc(program_id="TEST")
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            tmp_path = f.name
        try:
            save_json(doc, tmp_path)
            with open(tmp_path, encoding="utf-8") as f:
                loaded = json.load(f)
            self.assertEqual("TEST", loaded["program_id"])
            self.assertEqual("1.0", loaded["schema_version"])
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


# ── Markdown 输出测试 ────────────────────────────────────────────────────

class TestMdOutput(unittest.TestCase):
    """测试 Markdown 渲染。"""

    def test_render_contains_program_id(self):
        """Markdown 包含 program_id"""
        doc = LogicDoc(program_id="TEST")
        md = render_md(doc)
        self.assertIn("TEST", md)

    def test_render_entry(self):
        """Markdown 包含入口节点"""
        doc = LogicDoc(
            program_id="TEST",
            entry=LogicNode(node_id="ENTRY", type="entry", label="1000-MAIN"),
        )
        md = render_md(doc)
        self.assertIn("1000-MAIN", md)
        self.assertIn("入口", md)

    def test_render_results_table(self):
        """Markdown 渲染结果叶子表"""
        doc = LogicDoc(
            program_id="TEST",
            results=[
                ResultLeaf(id="R-01", kind="table_insert", target="TMRDPF", section="1500-READ"),
            ],
        )
        md = render_md(doc)
        self.assertIn("table_insert", md)
        self.assertIn("TMRDPF", md)

    def test_render_paths(self):
        """Markdown 渲染路径详情"""
        doc = LogicDoc(
            program_id="TEST",
            results=[ResultLeaf(id="R-01", kind="return", target="GOBACK", section="2000-DONE")],
            paths=[LogicPath(path_id="PATH-01", result_id="R-01",
                             node_sequence=["ENTRY", "N1"])],
            nodes={
                "ENTRY": LogicNode(node_id="ENTRY", type="entry", label="1000-MAIN"),
                "N1": LogicNode(node_id="N1", type="result", label="return: GOBACK"),
            },
        )
        md = render_md(doc)
        self.assertIn("PATH-01", md)
        self.assertIn("1000-MAIN", md)

    def test_render_intersections(self):
        """Markdown 渲染交叉点"""
        doc = LogicDoc(
            program_id="TEST",
            nodes={
                "N1": LogicNode(node_id="N1", type="box", label="1100-INIT",
                                path_tags=["PATH-01", "PATH-02"]),
            },
        )
        md = render_md(doc)
        self.assertIn("交叉点", md)
        self.assertIn("1100-INIT", md)

    def test_render_empty_doc(self):
        """空 LogicDoc 不崩溃"""
        doc = LogicDoc()
        md = render_md(doc)
        self.assertIsInstance(md, str)


# ── 端到端测试（基于 minimal.cob）────────────────────────────────────────

class Test88ConditionExpand(unittest.TestCase):
    """测试 88 条件名展开。"""

    def test_expand_single_value(self):
        """88 条件名单值 → HOLDER = 'VALUE'。"""
        from logician.tokens import expand_88_condition
        from parser.ws.model import WsNode, Condition

        ws_tree = [
            WsNode(
                level=3, name="WSAA-VAL28-PRD", pic="X(04)",
                conditions=[Condition(name="IS-6PWB", values=["6PWB"])],
            ),
        ]
        result = expand_88_condition("IS-6PWB", ws_tree)
        self.assertEqual(result, "WSAA-VAL28-PRD = '6PWB'")

    def test_expand_multiple_values(self):
        """88 条件名多值 → HOLDER IN ('V1', 'V2')。"""
        from logician.tokens import expand_88_condition
        from parser.ws.model import WsNode, Condition

        ws_tree = [
            WsNode(
                level=3, name="WSAA-VAL28-PRD", pic="X(04)",
                conditions=[
                    Condition(name="IS-MULTI", values=["VAL1", "VAL2"]),
                ],
            ),
        ]
        result = expand_88_condition("IS-MULTI", ws_tree)
        self.assertIn("IN", result)
        self.assertIn("VAL1", result)
        self.assertIn("VAL2", result)

    def test_expand_case_insensitive(self):
        """88 条件名大小写不敏感。"""
        from logician.tokens import expand_88_condition
        from parser.ws.model import WsNode, Condition

        ws_tree = [
            WsNode(
                level=3, name="WSAA-FLAG", pic="X(01)",
                conditions=[Condition(name="IS-YES", values=["Y"])],
            ),
        ]
        result = expand_88_condition("is-yes", ws_tree)
        self.assertEqual(result, "WSAA-FLAG = 'Y'")

    def test_expand_not_found_returns_none(self):
        """找不到 88 条件名 → None。"""
        from logician.tokens import expand_88_condition
        from parser.ws.model import WsNode, Condition

        ws_tree = [
            WsNode(
                level=3, name="WSAA-X", pic="X(01)",
                conditions=[Condition(name="IS-A", values=["A"])],
            ),
        ]
        result = expand_88_condition("IS-NOT-THERE", ws_tree)
        self.assertIsNone(result)

    def test_expand_none_ws_tree_returns_none(self):
        """ws_tree 为 None → None。"""
        from logician.tokens import expand_88_condition
        result = expand_88_condition("IS-ANY", None)
        self.assertIsNone(result)

    def test_expand_nested_holder_in_tree(self):
        """88 条件名在树深处能找到。"""
        from logician.tokens import expand_88_condition
        from parser.ws.model import WsNode, Condition

        ws_tree = [
            WsNode(level=1, name="WSAA-GROUP", pic="",
                   children=[
                       WsNode(level=3, name="WSAA-STATUS", pic="X(02)",
                              conditions=[
                                  Condition(name="IS-ACTIVE", values=["AC"]),
                              ]),
                   ]),
        ]
        result = expand_88_condition("IS-ACTIVE", ws_tree)
        self.assertEqual(result, "WSAA-STATUS = 'AC'")


class TestEndToEnd(unittest.TestCase):
    """基于 minimal.cob 的端到端生成测试。"""

    @classmethod
    def setUpClass(cls):
        """解析 minimal.cob 一次，供所有测试复用。"""
        from parser.cobol_parser import parse
        fixture = os.path.join(
            os.path.dirname(__file__), "tests", "fixtures", "minimal.cob",
        )
        if not os.path.exists(fixture):
            # 可能从项目根运行
            fixture = os.path.join("tests", "fixtures", "minimal.cob")
        cls.program = parse(fixture)

    def test_generate_returns_doc(self):
        """generate 返回 LogicDoc，包含 program_id"""
        from logician import generate
        doc = generate(self.program)
        self.assertIsInstance(doc, LogicDoc)
        self.assertEqual("MINISMOKE", doc.program_id)

    def test_generate_has_entry(self):
        """LogicDoc 有入口节点"""
        from logician import generate
        doc = generate(self.program)
        self.assertIsNotNone(doc.entry)
        self.assertEqual("entry", doc.entry.type)

    def test_generate_has_results(self):
        """minimal.cob 有 return 结果（GOBACK）"""
        from logician import generate
        doc = generate(self.program)
        self.assertGreater(len(doc.results), 0)
        returns = [r for r in doc.results if r.kind == "return"]
        self.assertGreater(len(returns), 0)

    def test_generate_has_paths(self):
        """minimal.cob 至少有 1 条路径"""
        from logician import generate
        doc = generate(self.program)
        self.assertGreater(len(doc.paths), 0)

    def test_generate_has_nodes(self):
        """minimal.cob 生成多个节点"""
        from logician import generate
        doc = generate(self.program)
        self.assertGreater(len(doc.nodes), 0)

    def test_generate_and_save(self):
        """generate_and_save 产出 JSON + MD 文件"""
        from logician import generate_and_save
        with tempfile.TemporaryDirectory() as tmpdir:
            doc, json_path, md_path = generate_and_save(
                self.program, tmpdir, "minimal",
            )
            self.assertTrue(os.path.isfile(json_path))
            self.assertTrue(os.path.isfile(md_path))
            with open(json_path, encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual("MINISMOKE", data["program_id"])
            with open(md_path, encoding="utf-8") as f:
                md_content = f.read()
            self.assertIn("MINISMOKE", md_content)


if __name__ == "__main__":
    unittest.main()
