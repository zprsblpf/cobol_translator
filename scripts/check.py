#!/usr/bin/env python3
"""Project verification entry point.

This script intentionally runs checks that do not require a local LLM,
LangGraph, Chroma, or MongoDB service. Install requirements.txt before using
the full translation pipeline.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _py(*args: str) -> list[str]:
    """Build a Python command using the current interpreter."""
    return [sys.executable, *args]


SUITES: dict[str, list[list[str]]] = {
    "quick": [
        _py("-m", "py_compile", "main.py", "test_smoke.py", "scripts/deterministic_report.py"),
        _py("-m", "unittest", "test_smoke", "-v"),
        _py("-m", "unittest", "test_t16_deterministic_report", "-v"),
        _py(
            "main.py",
            "tests/fixtures/minimal.cob",
            "--parse-only",
        ),
    ],
    "leaf": [
        _py(
            "-m",
            "unittest",
            "test_translation.TestLeafMoveExtract",
            "test_translation.TestLeafCondExtract",
            "test_translation.TestLeafLoopExtract",
            "test_translation.TestLeafCallExtract",
            "test_translation.TestLeafArithExtract",
            "test_translation.TestLeafStringExtract",
            "test_translation.TestLeafUnstringExtract",
            "test_translation.TestLeafInspectExtract",
            "test_translation.TestLeafSearchExtract",
            "test_translation.TestUnifiedLeafEntry",
            "test_t13_t14_ws_views",
            "-v",
        ),
    ],
    "asg": [
        _py(
            "-m",
            "unittest",
            "test_translation.TestAsgBuild",
            "test_translation.TestAsgMoveVisitor",
            "test_translation.TestAsgIfVisitor",
            "test_translation.TestAsgPerformVisitor",
            "test_translation.TestAsgCallVisitor",
            "test_translation.TestAsgLeafArithVisitor",
            "test_translation.TestAsgControlVisitor",
            "test_translation.TestAsgSectionVisitorFlow",
            "test_translation.TestAsgSectionVisitorPerformTarget",
            "test_translation.TestDiffAsgVsLegacy",
            "test_translation.TestDiffAsgVsLegacyLeafFallback",
            "test_translation.TestDiffAsgVsLegacyVerbMatrix",
            "test_translation.TestDiffAsgVsLegacyIf",
            "test_translation.TestDiffAsgVsLegacyPerform",
            "test_translation.TestDiffAsgVsLegacyPerformCall",
            "test_translation.TestDiffAsgVsLegacyFlow",
            "test_translation.TestDiffAsgVsLegacyIo",
            "test_translation.TestDiffAsgVsLegacyCall",
            "test_translation.TestDiffAsgVsLegacyArith",
            "test_translation.TestDiffAsgVsLegacyControl",
            "test_translation.TestDiffAsgVsLegacySection",
            "test_translation.TestMainlineSectionViaAsg",
            "test_t10_t12_control_flow",
            "-v",
        ),
    ],
    "logic": [
        _py("-m", "unittest", "tests.test_logician", "-v"),
        _py(
            "scripts/generate_logic_doc.py",
            "--cob", "tests/fixtures/minimal.cob",
            "--out-dir", "output/logic-doc",
        ),
    ],
}

SUITES["all"] = [
    _py("-m", "py_compile", "main.py", "test_smoke.py"),
    _py("-m", "unittest", "-v"),
    _py(
        "main.py",
        "tests/fixtures/minimal.cob",
        "--parse-only",
    ),
    _py(
        "scripts/translate_skeleton.py",
        "--in",
        "tests/fixtures/minimal.cob",
        "--out",
        "output/check/Minismoke.java",
    ),
    _py(
        "main.py",
        "tests/fixtures/minimal.cob",
        "--no-llm",
        "--output",
        "output/check-main",
    ),
]


def run(args: list[str]) -> int:
    print("$ " + " ".join(args), flush=True)
    return subprocess.call(args, cwd=ROOT)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run project verification checks.")
    parser.add_argument(
        "--suite",
        choices=sorted(SUITES),
        default="all",
        help="Verification suite to run.",
    )
    args = parser.parse_args(argv)

    for cmd in SUITES[args.suite]:
        code = run(cmd)
        if code:
            return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
