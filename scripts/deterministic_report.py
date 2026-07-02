"""Deterministic multi-file translation report output."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).parent.parent))

from parser.cobol_parser import parse
from translator.skeleton_gen.body_context import asg_fallback_summary
from translator.skeleton_gen.program_model import build_model
from translator.skeleton_gen.render_skeleton import render_skeleton_with_context
from validator.java_validator import scan_risks


SCHEMA_VERSION = 1


def _stable_paths(paths: Iterable[str | Path]) -> list[Path]:
    return sorted((Path(p).resolve() for p in paths), key=lambda p: str(p).lower())


def _todo_count(java_content: str) -> int:
    return java_content.count("TODO")


def _line_count(java_content: str) -> int:
    return java_content.count("\n") + 1 if java_content else 0


def build_report(inputs: Iterable[str | Path], output_dir: str | Path, report_path: str | Path | None = None) -> dict:
    """Translate each input and return a stable machine-readable report."""
    input_paths = _stable_paths(inputs)
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    report_file = Path(report_path).resolve() if report_path is not None else out_dir / "deterministic_report.json"

    files = []
    totals = {
        "file_count": 0,
        "todo_count": 0,
        "risk_count": 0,
        "asg_fallback_count": 0,
    }

    for infile in input_paths:
        program = parse(infile)
        model = build_model(program)
        java, ctx = render_skeleton_with_context(program)
        output = out_dir / f"{model.class_name}.java"
        output.write_text(java, encoding="utf-8")

        risks = scan_risks(java)
        fallback = asg_fallback_summary(ctx)
        item = {
            "input": str(infile),
            "output": str(output),
            "program_id": program.program_id,
            "class_name": model.class_name,
            "line_count": _line_count(java),
            "todo_count": _todo_count(java),
            "risk_count": len(risks),
            "risks": risks,
            "asg_fallback_summary": fallback,
        }
        files.append(item)
        totals["todo_count"] += item["todo_count"]
        totals["risk_count"] += item["risk_count"]
        totals["asg_fallback_count"] += fallback.get("count", 0)

    totals["file_count"] = len(files)

    return {
        "schema_version": SCHEMA_VERSION,
        "command": {
            "inputs": [str(p) for p in input_paths],
            "output_dir": str(out_dir),
            "report_path": str(report_file),
        },
        "files": files,
        "totals": totals,
    }


def write_report_json(report: dict, report_path: str | Path) -> str:
    """Write report JSON with deterministic formatting and return the rendered text."""
    path = Path(report_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(rendered, encoding="utf-8")
    return rendered


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write deterministic JSON report for COBOL skeleton translation.")
    ap.add_argument("--in", dest="inputs", action="append", required=True, help="Input .cob path; repeat for many files")
    ap.add_argument("--out-dir", required=True, help="Directory for generated Java files")
    ap.add_argument("--report", help="Report JSON path; defaults to <out-dir>/deterministic_report.json")
    args = ap.parse_args(argv)

    report_path = Path(args.report).resolve() if args.report else Path(args.out_dir).resolve() / "deterministic_report.json"
    report = build_report(args.inputs, args.out_dir, report_path)
    write_report_json(report, report_path)
    print(f"OK generated report {report_path} ({report['totals']['file_count']} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
