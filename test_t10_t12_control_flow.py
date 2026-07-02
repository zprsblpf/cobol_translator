import unittest
from types import SimpleNamespace

from asg.nodes import GotoStmt, IfStmt, Leaf
from asg.registry import ProcRef
from asg.section_visitor import SectionJavaVisitor
from asg.visitor import LeafJavaVisitor
from asg.builder import _goto_target
from translator.leaf.cond import translate_condition
from translator.leaf.control import translate_control


def _ctx(known_sections=None, field_type_map=None):
    return SimpleNamespace(
        field_type_map=field_type_map or {},
        section_to_method=lambda s: "p_" + s.replace("-", "").lower(),
        known_sections=set(known_sections or ()),
        struct_objects={},
        io_struct_prefixes=set(),
        flow_label=None,
        flow_paragraphs=set(),
    )


class TestT10T12ControlFlow(unittest.TestCase):
    def test_condition_translates_and_or_comparison_shell(self):
        ctx = _ctx(field_type_map={"fieldA": {"type": "int"}, "fieldB": {"type": "String"}})

        self.assertEqual(
            "fieldA == 1 && StringUtils.isBlank(fieldB)",
            translate_condition(["FIELD-A", "=", "1", "AND", "FIELD-B", "=", "SPACES"], ctx),
        )

    def test_if_visitor_renders_translated_then_and_else_control_flow(self):
        ctx = _ctx(field_type_map={"fieldA": {"type": "int"}})
        node = IfStmt(
            cond=["FIELD-A", "=", "1"],
            then=[Leaf(tokens=["CONTINUE"], raw="CONTINUE")],
            els=[Leaf(tokens=["GOBACK"], raw="GOBACK")],
            raw="IF FIELD-A = 1",
        )

        self.assertEqual(
            [
                "if (fieldA == 1) {",
                "    ;  // CONTINUE",
                "} else {",
                "    return;",
                "}",
            ],
            LeafJavaVisitor(ctx).visit(node),
        )

    def test_go_to_depending_on_is_explicit_fallback_not_single_target_jump(self):
        ctx = _ctx({"PARA-1", "PARA-2"})

        lines, matched = translate_control(
            ["GO", "TO", "PARA-1", "PARA-2", "DEPENDING", "ON", "CHOICE"],
            ctx,
        )

        self.assertTrue(matched)
        self.assertEqual(
            [
                "// TODO-GOTO-DEPENDING: GO TO PARA-1 PARA-2 DEPENDING ON CHOICE requires indexed dispatch review",
                "return;",
            ],
            lines,
        )

    def test_asg_goto_depending_on_uses_same_explicit_fallback(self):
        ctx = _ctx({"PARA-1", "PARA-2"})
        node = GotoStmt(
            tokens=["GO", "TO", "PARA-1", "PARA-2", "DEPENDING", "ON", "CHOICE"],
            raw="GO TO PARA-1 PARA-2 DEPENDING ON CHOICE",
        )

        self.assertEqual(
            [
                "// TODO-GOTO-DEPENDING: GO TO PARA-1 PARA-2 DEPENDING ON CHOICE requires indexed dispatch review",
                "return;",
            ],
            LeafJavaVisitor(ctx).visit(node),
        )

    def test_builder_does_not_resolve_single_target_for_goto_depending_on(self):
        self.assertIsNone(
            _goto_target(["GO", "TO", "PARA-1", "PARA-2", "DEPENDING", "ON", "CHOICE"])
        )

    def test_section_visitor_does_not_dispatch_goto_depending_on_as_single_target(self):
        ctx = _ctx({"PARA-1", "PARA-2"})
        visitor = SectionJavaVisitor(ctx)
        visitor.flow_label = "FLOW"
        visitor.flow_paragraphs = {"PARA-1", "PARA-2"}
        node = GotoStmt(
            target=ProcRef("PARA-1"),
            tokens=["GO", "TO", "PARA-1", "PARA-2", "DEPENDING", "ON", "CHOICE"],
            raw="GO TO PARA-1 PARA-2 DEPENDING ON CHOICE",
        )

        self.assertEqual(
            [
                "// TODO-GOTO-DEPENDING: GO TO PARA-1 PARA-2 DEPENDING ON CHOICE requires indexed dispatch review",
                "return;",
            ],
            visitor.visit_GotoStmt(node),
        )


if __name__ == "__main__":
    unittest.main()
