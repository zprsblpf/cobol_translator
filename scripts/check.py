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
SUITES = ("quick", "leaf", "asg", "deterministic", "all")


def _py(*args: str) -> list[str]:
    """Build a Python command using the current interpreter."""
    return [sys.executable, *args]


def py_compile_command() -> list[str]:
    return [
        sys.executable,
        "-m",
        "py_compile",
        "main.py",
        "test_smoke.py",
        "scripts/check.py",
    ]


def smoke_command() -> list[str]:
    return [sys.executable, "-m", "unittest", "-v", "test_smoke"]


def minimal_parse_command() -> list[str]:
    return [
        sys.executable,
        "main.py",
        "tests/fixtures/minimal.cob",
        "--parse-only",
    ]


def deterministic_commands() -> list[list[str]]:
    return [
        [
            sys.executable,
            "scripts/translate_skeleton.py",
            "--in",
            "tests/fixtures/minimal.cob",
            "--out",
            "output/check/Minismoke.java",
        ],
        [
            sys.executable,
            "main.py",
            "tests/fixtures/minimal.cob",
            "--no-llm",
            "--output",
            "output/check-main",
        ],
    ]


def filtered_unittest_command(patterns: list[str]) -> list[str]:
    command = [sys.executable, "-m", "unittest", "-v"]
    for pattern in patterns:
        command.extend(["-k", pattern])
    command.append("test_translation")
    return command


def suite_commands(suite: str) -> list[list[str]]:
    commands_by_suite = {
        "quick": [
            py_compile_command(),
            smoke_command(),
            minimal_parse_command(),
        ],
        "leaf": [
            filtered_unittest_command(
                [
                    "test_translation.TestLeaf*",
                    "test_translation.TestUnifiedLeafEntry.*",
                ]
            )
        ],
        "asg": [
            filtered_unittest_command(
                [
                    "test_translation.TestAsg*",
                    "test_translation.TestDiffAsgVsLegacy*",
                ]
            )
        ],
        "deterministic": deterministic_commands(),
    }
    commands_by_suite["all"] = [
        py_compile_command(),
        [sys.executable, "-m", "unittest", "-v"],
        minimal_parse_command(),
        *deterministic_commands(),
    ]
    return commands_by_suite[suite]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        choices=SUITES,
        default="all",
        help="Focused check suite to run. Defaults to all.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    for cmd in suite_commands(args.suite):
        code = run(cmd)
        if code:
            return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
