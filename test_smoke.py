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


if __name__ == "__main__":
    unittest.main()
