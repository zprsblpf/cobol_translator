import unittest
from pathlib import Path

from parser.cobol_parser import parse
from scripts import check
from scripts.scan_rule_coverage import scan_file
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
        self.assertIn("public void execute() {", java)
        self.assertIn("this.main1000(wsaa);", java)
        self.assertIn("void main1000(", java)
        self.assertIn("void done2000(", java)
        self.assertIn("wsaa.wsCounter = 1;", java)
        self.assertIn('wsaa.wsName = "OK";', java)
        self.assertNotIn("TODO 入口控制流待译", java)


class TestRuleCoverageScannerSmoke(unittest.TestCase):
    def test_minimal_fixture_reports_supported_and_unsupported_counts(self):
        report = scan_file(ROOT / "tests" / "fixtures" / "minimal.cob")

        self.assertEqual(report["program_id"], "MINISMOKE")
        self.assertGreaterEqual(report["supported"], 1)
        self.assertIn("unsupported", report)
        self.assertEqual(report["verbs"]["MOVE"]["supported"], 2)
        self.assertEqual(report["verbs"]["MOVE"]["unsupported"], 0)
        self.assertIn("GOBACK", report["verbs"])

    def test_rule_assets_are_loaded_into_report(self):
        report = scan_file(ROOT / "tests" / "fixtures" / "minimal.cob")

        self.assertIn("UNSTRING", report["rule_assets"])
        self.assertIn("STRING", report["rule_assets"])
        self.assertGreaterEqual(report["rule_assets"]["UNSTRING"]["implemented"], 1)
        self.assertGreaterEqual(report["rule_assets"]["STRING"]["unsupported"], 1)


class TestCheckSuiteConfig(unittest.TestCase):
    def test_default_suite_is_all(self):
        args = check.parse_args([])

        self.assertEqual(args.suite, "all")

    def test_quick_suite_uses_compile_smoke_and_minimal_parse(self):
        commands = check.suite_commands("quick")

        self.assertEqual(len(commands), 3)
        self.assertIn("py_compile", commands[0])
        self.assertEqual(commands[1][-1], "test_smoke")
        self.assertEqual(commands[2][-2:], ["tests/fixtures/minimal.cob", "--parse-only"])

    def test_leaf_suite_targets_leaf_test_classes(self):
        commands = check.suite_commands("leaf")

        self.assertEqual(len(commands), 1)
        self.assertIn("test_translation.TestLeaf*", commands[0])
        self.assertIn("test_translation.TestUnifiedLeafEntry.*", commands[0])
        self.assertEqual(commands[0][-1], "test_translation")

    def test_asg_suite_targets_asg_and_diff_test_classes(self):
        commands = check.suite_commands("asg")

        self.assertEqual(len(commands), 1)
        self.assertIn("test_translation.TestAsg*", commands[0])
        self.assertIn("test_translation.TestDiffAsgVsLegacy*", commands[0])
        self.assertEqual(commands[0][-1], "test_translation")

    def test_deterministic_suite_uses_minimal_no_llm_outputs(self):
        commands = check.suite_commands("deterministic")

        self.assertEqual(len(commands), 2)
        self.assertIn("scripts/translate_skeleton.py", commands[0])
        self.assertIn("--no-llm", commands[1])
        self.assertIn("tests/fixtures/minimal.cob", commands[1])

    def test_all_suite_keeps_full_gate(self):
        commands = check.suite_commands("all")

        self.assertEqual(len(commands), 5)
        self.assertEqual(commands[1], [check.sys.executable, "-m", "unittest", "-v"])
        self.assertIn("--parse-only", commands[2])
        self.assertIn("--no-llm", commands[4])


class TestCheckScriptSuites(unittest.TestCase):
    """并行开发：验证 scripts.check 暴露固定快速验证套件。"""

    def test_suite_names_are_stable(self):
        from scripts import check

        self.assertEqual(set(check.SUITES), {"quick", "leaf", "asg", "all"})

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
