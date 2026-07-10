"""
T13-T14 WS 字段视图测试（合格字段引用 + REDEFINES 数组视图）。

覆盖 COBOL 的 OF/IN 限定名解析和 REDEFINES 在 OCCURS 内的切片访问器生成。
"""
import unittest
from types import SimpleNamespace

from parser.ws.model import WsNode
from translator.leaf.expr import _operand
from translator.naming import parse_qualified_field_reference, resolve_qualified_field_reference
from translator.wsaa.render_class import render_wsaa


def _leaf(name, pic="X(1)", java_type="String", byte_len=1, occurs=0, redefines=""):
    return WsNode(
        level=5,
        name=name,
        pic=pic,
        java_type=java_type,
        byte_len=byte_len,
        occurs=occurs,
        redefines=redefines,
        raw=f"05 {name} PIC {pic}.",
    )


class TestT13QualifiedFieldReferences(unittest.TestCase):
    def test_parse_qualified_field_reference_accepts_of_and_in(self):
        self.assertEqual(
            parse_qualified_field_reference("STATUS OF HEADER"),
            ("STATUS", ("HEADER",)),
        )
        self.assertEqual(
            parse_qualified_field_reference("AMOUNT IN DETAIL IN ORDER-REC"),
            ("AMOUNT", ("DETAIL", "ORDER-REC")),
        )

    def test_resolve_qualified_field_reference_uses_explicit_map(self):
        ctx = SimpleNamespace(
            field_type_map={
                "hdrStatus": {"type": "String"},
                "dtlStatus": {"type": "String"},
            },
            qualified_field_map={
                ("STATUS", ("HEADER",)): "hdrStatus",
                ("STATUS", ("DETAIL",)): "dtlStatus",
            },
            io_struct_prefixes=set(),
        )

        self.assertEqual(resolve_qualified_field_reference("STATUS OF HEADER", ctx), "hdrStatus")
        self.assertEqual(resolve_qualified_field_reference("STATUS IN DETAIL", ctx), "dtlStatus")
        self.assertEqual(_operand("STATUS OF HEADER", ctx), "hdrStatus")

    def test_unresolved_qualified_field_reference_is_explicit_todo_literal(self):
        ctx = SimpleNamespace(field_type_map={}, qualified_field_map={}, io_struct_prefixes=set())

        self.assertIn("TODO unresolved qualified field", _operand("STATUS OF HEADER", ctx))


class TestT14RedefinesArrayViews(unittest.TestCase):
    def test_redefines_inside_occurs_generates_indexed_slice_accessors(self):
        root = WsNode(level=1, name="WSAA-ROOT", raw="01 WSAA-ROOT.")
        row = WsNode(level=3, name="WSAA-ROW", occurs=2, raw="03 WSAA-ROW OCCURS 2.")
        target = _leaf("WSAA-RAW", pic="X(4)", byte_len=4)
        alias = WsNode(
            level=5,
            name="WSAA-ALIAS",
            redefines="WSAA-RAW",
            raw="05 WSAA-ALIAS REDEFINES WSAA-RAW.",
        )
        alias.children.append(_leaf("WSAA-PART", pic="X(2)", byte_len=2))
        row.children.extend([target, alias])
        root.children.append(row)

        src = render_wsaa([root], "ZTEST")

        self.assertNotIn("TODO REDEFINES WSAA-RAW", src)
        self.assertNotIn("private String[] wsaaPart", src)
        self.assertIn("public String getWsaaPart(int i)", src)
        self.assertIn("_pad(wsaaRaw[i - 1], 4).substring(0, 2)", src)
        self.assertIn("public void setWsaaPart(int i, String v)", src)
        self.assertIn("wsaaRaw[i - 1] = _n;", src)

    def test_redefines_inside_two_occurs_generates_two_index_parameters(self):
        root = WsNode(level=1, name="WSAA-ROOT", raw="01 WSAA-ROOT.")
        line = WsNode(level=3, name="WSAA-LINE", occurs=2, raw="03 WSAA-LINE OCCURS 2.")
        row = WsNode(level=5, name="WSAA-ROW", occurs=3, raw="05 WSAA-ROW OCCURS 3.")
        target = _leaf("WSAA-RAW", pic="X(4)", byte_len=4)
        alias = WsNode(
            level=7,
            name="WSAA-ALIAS",
            redefines="WSAA-RAW",
            raw="07 WSAA-ALIAS REDEFINES WSAA-RAW.",
        )
        alias.children.append(_leaf("WSAA-PART", pic="X(2)", byte_len=2))
        row.children.extend([target, alias])
        line.children.append(row)
        root.children.append(line)

        src = render_wsaa([root], "ZTEST")

        self.assertNotIn("TODO REDEFINES WSAA-RAW", src)
        self.assertIn("public String getWsaaPart(int i, int j)", src)
        self.assertIn("_pad(wsaaRaw[i - 1][j - 1], 4).substring(0, 2)", src)
        self.assertIn("public void setWsaaPart(int i, int j, String v)", src)
        self.assertIn("wsaaRaw[i - 1][j - 1] = _n;", src)

    def test_redefines_with_mismatched_occurs_dimensions_stays_todo(self):
        root = WsNode(level=1, name="WSAA-ROOT", raw="01 WSAA-ROOT.")
        row = WsNode(level=3, name="WSAA-ROW", occurs=2, raw="03 WSAA-ROW OCCURS 2.")
        target = _leaf("WSAA-RAW", pic="X(4)", byte_len=4)
        alias = WsNode(
            level=5,
            name="WSAA-ALIAS",
            occurs=2,
            redefines="WSAA-RAW",
            raw="05 WSAA-ALIAS REDEFINES WSAA-RAW OCCURS 2.",
        )
        alias.children.append(_leaf("WSAA-PART", pic="X(2)", byte_len=2))
        row.children.extend([target, alias])
        root.children.append(row)

        src = render_wsaa([root], "ZTEST")

        self.assertIn("TODO REDEFINES WSAA-RAW", src)
        self.assertNotIn("public String getWsaaPart(int i)", src)


if __name__ == "__main__":
    unittest.main()
