#!/usr/bin/env python3
"""Scan COBOL rule coverage by first verb.

The scanner is intentionally read-only: it parses COBOL, walks segmented
statements, and asks the shared leaf dispatcher whether leaf-shaped statements
are supported.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict

import yaml
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from parser.cobol_parser import parse
from translator.leaf import translate_leaf_stmt
from translator.segmenter import Stmt, segment, split_paragraphs
from translator.skeleton_gen.body_context import build_body_ctx


STRUCTURAL_KINDS = {"if": "IF", "evaluate": "EVALUATE", "perform": "PERFORM"}
RULES_DIR = ROOT / "config" / "rules"


def _normalize_rule(raw: dict, source: Path) -> dict | None:
    if not isinstance(raw, dict):
        return None
    rule_id = raw.get("rule_id") or raw.get("id")
    verb = raw.get("verb")
    if not rule_id or not verb:
        return None
    rule = {
        "source": str(source),
        "rule_id": str(rule_id),
        "verb": str(verb).upper(),
        "status": str(raw.get("status", "planned")),
    }
    for key in ("title", "description", "translator"):
        if key in raw:
            rule[key] = raw[key]
    return rule


def _load_rule_file(path: Path) -> list[dict]:
    """Load rule assets from YAML using PyYAML."""
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    candidates = data.get("rules") if isinstance(data, dict) and "rules" in data else data
    if isinstance(candidates, list):
        raw_rules = candidates
    else:
        raw_rules = [candidates]
    rules = [_normalize_rule(raw, path) for raw in raw_rules]
    return [rule for rule in rules if rule is not None]

def load_rule_assets(rules_dir: Path = RULES_DIR) -> dict:
    """Return rule assets grouped by COBOL verb."""
    by_verb: dict[str, list[dict]] = defaultdict(list)
    if rules_dir.exists():
        for path in sorted(rules_dir.glob("*.yaml")):
            for rule in _load_rule_file(path):
                by_verb[rule["verb"].upper()].append(rule)
    implemented_statuses = {"implemented", "supported", "deterministic", "deterministic_leaf"}
    return {
        verb: {
            "rules": rules,
            "implemented": sum(1 for r in rules if r.get("status") in implemented_statuses),
            "planned": sum(1 for r in rules if r.get("status") == "planned"),
            "unsupported": sum(1 for r in rules if r.get("status") == "unsupported"),
        }
        for verb, rules in sorted(by_verb.items())
    }


def _record(
    verbs: dict[str, Counter],
    status: str,
    verb: str,
    examples: dict[str, list[str]],
    raw: str,
) -> None:
    verb = verb.upper()
    verbs[verb][status] += 1
    if status == "unsupported" and raw and len(examples[verb]) < 3:
        examples[verb].append(raw)


def _walk_statements(
    statements: Iterable[Stmt],
    ctx,
    verbs: dict[str, Counter],
    examples: dict[str, list[str]],
) -> None:
    for stmt in statements:
        if stmt.kind == "simple":
            if not stmt.tokens:
                continue
            verb = stmt.tokens[0].upper()
            try:
                _lines, ok = translate_leaf_stmt(stmt.tokens, ctx)
            except Exception as exc:  # visible in the report; scanner must not hide failures.
                ok = False
                raw = (stmt.raw or " ".join(stmt.tokens)).strip()
                raw = f"{raw}  [translator_exception={type(exc).__name__}]"
            else:
                raw = (stmt.raw or " ".join(stmt.tokens)).strip()
            _record(verbs, "supported" if ok else "unsupported", verb, examples, raw)
            continue

        verb = STRUCTURAL_KINDS.get(stmt.kind)
        if verb:
            _record(verbs, "supported", verb, examples, stmt.raw)

        _walk_statements(stmt.children, ctx, verbs, examples)
        _walk_statements(stmt.else_children, ctx, verbs, examples)
        for _cond, body in stmt.whens:
            _walk_statements(body, ctx, verbs, examples)


def scan_file(cob_file: str | Path) -> dict:
    """Return a JSON-serializable verb coverage report for one COBOL file."""
    path = Path(cob_file)
    program = parse(path)
    ctx, _ws_field_names = build_body_ctx(program)
    rule_assets = load_rule_assets()
    verbs: dict[str, Counter] = defaultdict(Counter)
    examples: dict[str, list[str]] = defaultdict(list)

    for section in program.sections:
        for _label, body_lines in split_paragraphs(section.lines):
            _walk_statements(segment(body_lines), ctx, verbs, examples)

    verb_report = {}
    total_supported = 0
    total_unsupported = 0
    for verb in sorted(verbs):
        supported = int(verbs[verb]["supported"])
        unsupported = int(verbs[verb]["unsupported"])
        total_supported += supported
        total_unsupported += unsupported
        verb_report[verb] = {
            "supported": supported,
            "unsupported": unsupported,
            "total": supported + unsupported,
        }
        if verb in rule_assets:
            verb_report[verb]["rules"] = rule_assets[verb]["rules"]
            verb_report[verb]["rule_status"] = {
                "implemented": rule_assets[verb]["implemented"],
                "planned": rule_assets[verb]["planned"],
                "unsupported": rule_assets[verb]["unsupported"],
            }
        if examples.get(verb):
            verb_report[verb]["unsupported_examples"] = examples[verb]

    return {
        "source_file": str(path),
        "program_id": program.program_id,
        "sections": len(program.sections),
        "supported": total_supported,
        "unsupported": total_unsupported,
        "total": total_supported + total_unsupported,
        "rule_assets": rule_assets,
        "verbs": verb_report,
    }


def _summary(report: dict) -> str:
    lines = [
        f"Rule coverage for {report['source_file']} ({report['program_id']})",
        f"supported={report['supported']} unsupported={report['unsupported']} total={report['total']}",
    ]
    for verb, counts in report["verbs"].items():
        status = counts.get("rule_status")
        suffix = ""
        if status:
            suffix = (
                f" rules=implemented:{status['implemented']}"
                f"/planned:{status['planned']}/unsupported:{status['unsupported']}"
            )
        lines.append(
            f"{verb:<10} supported={counts['supported']} "
            f"unsupported={counts['unsupported']} total={counts['total']}{suffix}"
        )
    return "\n".join(lines)


def _markdown(report: dict) -> str:
    lines = [
        f"# Rule coverage: {report['program_id']}",
        "",
        f"- Source: `{report['source_file']}`",
        f"- Supported: {report['supported']}",
        f"- Unsupported: {report['unsupported']}",
        "",
        "| Verb | Supported | Unsupported | Total | Rule assets |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for verb, counts in report["verbs"].items():
        status = counts.get("rule_status") or {}
        rule_summary = (
            f"implemented={status.get('implemented', 0)}, "
            f"planned={status.get('planned', 0)}, "
            f"unsupported={status.get('unsupported', 0)}"
        )
        lines.append(
            f"| {verb} | {counts['supported']} | {counts['unsupported']} | "
            f"{counts['total']} | {rule_summary} |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan COBOL rule coverage by verb.")
    parser.add_argument("cob_file", help="COBOL source file to scan")
    parser.add_argument(
        "--format",
        choices=("text", "json", "markdown"),
        default="text",
        help="Output format. text prints a summary followed by JSON.",
    )
    args = parser.parse_args(argv)

    report = scan_file(args.cob_file)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.format == "markdown":
        print(_markdown(report))
    else:
        print(_summary(report))
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
