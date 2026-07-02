import json
import tempfile
import unittest
from pathlib import Path


class TestDeterministicReportOutput(unittest.TestCase):
    def _write_cobol(self, root: Path, name: str, program_id: str, body: str) -> Path:
        path = root / name
        path.write_text(
            "\n".join([
                "       IDENTIFICATION DIVISION.",
                f"       PROGRAM-ID. {program_id}.",
                "       DATA DIVISION.",
                "       WORKING-STORAGE SECTION.",
                "       01 WS-COUNTER PIC 9(4).",
                "       PROCEDURE DIVISION.",
                "       1000-MAIN SECTION.",
                *body.splitlines(),
                "           GOBACK.",
            ]),
            encoding="utf-8",
        )
        return path

    def test_report_json_is_stable_and_machine_readable_for_multiple_inputs(self):
        from scripts.deterministic_report import build_report, write_report_json

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            first = self._write_cobol(root, "b.cob", "BRAVO", "           MOVE 1 TO WS-COUNTER.")
            second = self._write_cobol(root, "a.cob", "ALPHA", "           DISPLAY WS-COUNTER.")
            out_dir = root / "out"
            report_path = out_dir / "deterministic-report.json"

            report = build_report([first, second], out_dir, report_path)
            rendered = write_report_json(report, report_path)
            reread = report_path.read_text(encoding="utf-8")

            self.assertEqual(rendered, reread)
            self.assertEqual(json.loads(rendered), report)
            self.assertEqual(
                [Path(item["input"]).name for item in report["files"]],
                ["a.cob", "b.cob"],
            )
            self.assertEqual(
                [Path(item["output"]).name for item in report["files"]],
                ["Alpha.java", "Bravo.java"],
            )

            alpha = report["files"][0]
            self.assertEqual(alpha["program_id"], "ALPHA")
            self.assertEqual(alpha["todo_count"], 2)
            self.assertGreaterEqual(alpha["risk_count"], 1)
            self.assertEqual(alpha["asg_fallback_summary"], {"count": 0, "events": []})

            self.assertEqual(report["totals"]["file_count"], 2)
            self.assertEqual(report["totals"]["todo_count"], sum(f["todo_count"] for f in report["files"]))
            self.assertEqual(report["totals"]["risk_count"], sum(f["risk_count"] for f in report["files"]))
            self.assertEqual(report["totals"]["asg_fallback_count"], 0)
            self.assertEqual(
                [Path(p).name for p in report["command"]["inputs"]],
                ["a.cob", "b.cob"],
            )
            self.assertEqual(Path(report["command"]["output_dir"]), out_dir.resolve())
            self.assertEqual(Path(report["command"]["report_path"]), report_path.resolve())


if __name__ == "__main__":
    unittest.main()
