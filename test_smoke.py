import unittest
from pathlib import Path

from parser.cobol_parser import parse
from translator.skeleton_gen import render_skeleton


ROOT = Path(__file__).parent


class TestMinimalCobolSmoke(unittest.TestCase):
    def test_parse_and_render_skeleton_without_llm(self):
        program = parse(ROOT / "tests" / "fixtures" / "minimal.cob")

        self.assertEqual(program.program_id, "MINISMOKE")
        self.assertEqual([s.name for s in program.sections], ["1000-MAIN", "2000-DONE"])
        self.assertEqual(program.sections[0].performs, ["2000-DONE"])

        java = render_skeleton(program)

        self.assertIn("public class Minismoke", java)
        self.assertIn("void main1000(", java)
        self.assertIn("void done2000(", java)
        self.assertIn("wsaa.wsCounter = 1;", java)
        self.assertIn('wsaa.wsName = "OK";', java)


class TestCheckScriptSuites(unittest.TestCase):
    """并行开发：验证 scripts.check 暴露固定快速验证套件。"""

    def test_suite_names_are_stable(self):
        from scripts import check

        self.assertEqual(set(check.SUITES), {"quick", "leaf", "asg", "logic", "all"})

    def test_all_suite_preserves_legacy_gate_order(self):
        from scripts import check

        all_cmds = [cmd[1:] for cmd in check.SUITES["all"]]

        self.assertEqual(
            all_cmds,
            [
                ["-m", "py_compile", "main.py", "test_smoke.py"],
                ["-m", "unittest", "-v"],
                ["main.py", "tests/fixtures/minimal.cob", "--parse-only"],
                [
                    "scripts/translate_skeleton.py",
                    "--in",
                    "tests/fixtures/minimal.cob",
                    "--out",
                    "output/check/Minismoke.java",
                ],
                [
                    "main.py",
                    "tests/fixtures/minimal.cob",
                    "--no-llm",
                    "--output",
                    "output/check-main",
                ],
            ],
        )


if __name__ == "__main__":
    unittest.main()
