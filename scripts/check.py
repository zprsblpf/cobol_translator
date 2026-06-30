#!/usr/bin/env python3
"""Project verification entry point.

This script intentionally runs checks that do not require a local LLM,
LangGraph, Chroma, or MongoDB service. Install requirements.txt before using
the full translation pipeline.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def run(args: list[str]) -> int:
    print("$ " + " ".join(args), flush=True)
    return subprocess.call(args, cwd=ROOT)


def main() -> int:
    commands = [
        [sys.executable, "-m", "py_compile", "main.py", "test_smoke.py"],
        [sys.executable, "-m", "unittest", "-v"],
        [
            sys.executable,
            "main.py",
            "tests/fixtures/minimal.cob",
            "--parse-only",
        ],
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

    for cmd in commands:
        code = run(cmd)
        if code:
            return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
