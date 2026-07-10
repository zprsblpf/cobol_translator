"""
轻量 Java 逻辑分析：从 Java Service 提取方法结构、调用链、IO 操作。

用法：
    python scripts/analyze_java_service.py \\
        --in "E:/code/project/db2-for-new-project/.../ZpoldwnmServiceImpl.java" \\
        --out output/java-logic
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── 行级模式（跳过注释行）─────────────────────────────────────────────────

_REPO_FIND = re.compile(r"(\w+)Repository\.(find|get|query|read)\w+\(")
_REPO_SAVE = re.compile(r"(\w+)Repository\.(save|insert|add)\w*\(")
_REPO_UPDATE = re.compile(r"(\w+)Repository\.(update|modify)\w*\(")
_REPO_DELETE = re.compile(r"(\w+)Repository\.(delete|remove)\w*\(")
_THIS_CALL = re.compile(r"this\.(\w+)\s*\(")
_SERVICE_CALL = re.compile(r"(\w+)Service\.(\w+)\s*\(")
_IF_PATTERN = re.compile(r"\bif\s*\(")
_SWITCH_PATTERN = re.compile(r"\bswitch\s*\(")
_RETURN_PATTERN = re.compile(r"\breturn\b")
_CATCH_PATTERN = re.compile(r"\bcatch\s*\(")
_SYSERR_PATTERN = re.compile(r"sysErrService|syserr|SysErr")


def _is_comment(line: str) -> bool:
    s = line.strip()
    return s.startswith("//") or s.startswith("*") or s.startswith("/*")


def extract_methods(lines: list[str]) -> list[dict]:
    """解析 Java 方法列表。"""
    methods: list[dict] = []
    depth = 0
    cur = None
    sig_re = re.compile(
        r"(public|private|protected)\s+"                            # 可见性
        r"(\S[\w<>\[\],\s]*?\s+)?"                                  # 返回类型（含泛型）
        r"(\w+)\s*\("                                               # 方法名
    )

    for i, line in enumerate(lines):
        s = line.strip()
        if _is_comment(line):
            if cur and cur["_body_started"]:
                pass  # 注释行不影响括号深度
            continue

        # 检测方法签名
        m = sig_re.search(s)
        if m and cur is None and m.group(3) not in ("class", "if", "while", "for"):
            name = m.group(3)
            if "{" in s:
                # 签名与 { 在同一行
                cur = {
                    "name": name, "start_line": i + 1, "end_line": i + 1,
                    "_body_started": True, "depth": 0,
                    "calls_this": [], "service_calls": [],
                    "repo_find": [], "repo_save": [], "repo_update": [], "repo_delete": [],
                    "if_count": 0, "switch_count": 0, "return_count": 0,
                    "catch_count": 0, "has_syserr": False,
                }
            else:
                # 签名跨多行，标记待 { 出现
                cur = {
                    "name": name, "start_line": i + 1, "end_line": i + 1,
                    "_body_started": False, "depth": 0,
                    "calls_this": [], "service_calls": [],
                    "repo_find": [], "repo_save": [], "repo_update": [], "repo_delete": [],
                    "if_count": 0, "switch_count": 0, "return_count": 0,
                    "catch_count": 0, "has_syserr": False,
                }
            depth = 0

        if cur is None:
            continue

        # 等待 { 开始方法体
        if not cur["_body_started"]:
            cur["end_line"] = i + 1
            if "{" in s:
                cur["_body_started"] = True
                depth = s.count("{") - s.count("}")
            continue

        # 花括号深度追踪
        depth += s.count("{") - s.count("}")
        cur["depth"] = depth
        cur["end_line"] = i + 1

        if depth <= 0:
            # 方法结束
            methods.append(cur)
            cur = None
            depth = 0
            continue

        # 行级模式匹配（只在方法体内）
        # Repository 调用
        m = _REPO_FIND.search(s)
        if m:
            cur["repo_find"].append(f"{m.group(1)}.{m.group(2)}")
        m = _REPO_SAVE.search(s)
        if m:
            cur["repo_save"].append(f"{m.group(1)}.{m.group(2)}")
        m = _REPO_UPDATE.search(s)
        if m:
            cur["repo_update"].append(f"{m.group(1)}.{m.group(2)}")
        m = _REPO_DELETE.search(s)
        if m:
            cur["repo_delete"].append(f"{m.group(1)}.{m.group(2)}")

        # 方法调用：this.xxx() 或直接 xxx()（无 this. 前缀）
        for m in _THIS_CALL.finditer(s):
            if m.group(1) not in ("set", "get"):
                cur["calls_this"].append(m.group(1))
        # 直接方法调用（无 this.）：匹配 section 命名风格的方法名
        bare_call = re.match(r"^\s*([a-z]\w*_\d+)\s*\(", s)
        if bare_call:
            callee = bare_call.group(1)
            if callee not in ("set", "get", "is", "has"):
                cur["calls_this"].append(callee)

        # xxxService.xxx() 调用
        for m in _SERVICE_CALL.finditer(s):
            cur["service_calls"].append(f"{m.group(1)}.{m.group(2)}")

        # 控制流
        if _IF_PATTERN.search(s):
            cur["if_count"] += 1
        if _SWITCH_PATTERN.search(s):
            cur["switch_count"] += 1
        if _RETURN_PATTERN.search(s):
            cur["return_count"] += 1
        if _CATCH_PATTERN.search(s):
            cur["catch_count"] += 1
        if _SYSERR_PATTERN.search(s):
            cur["has_syserr"] = True

        # 行级模式匹配（只在方法体内，depth > 0）
        if depth > 0:
            # Repository 调用
            m = _REPO_FIND.search(s)
            if m:
                cur["repo_find"].append(f"{m.group(1)}.{m.group(2)}")
            m = _REPO_SAVE.search(s)
            if m:
                cur["repo_save"].append(f"{m.group(1)}.{m.group(2)}")
            m = _REPO_UPDATE.search(s)
            if m:
                cur["repo_update"].append(f"{m.group(1)}.{m.group(2)}")
            m = _REPO_DELETE.search(s)
            if m:
                cur["repo_delete"].append(f"{m.group(1)}.{m.group(2)}")

            # this.xxx() 调用
            for m in _THIS_CALL.finditer(s):
                cur["calls_this"].append(m.group(1))

            # xxxService.xxx() 调用
            for m in _SERVICE_CALL.finditer(s):
                cur["service_calls"].append(f"{m.group(1)}.{m.group(2)}")

            # 控制流
            if _IF_PATTERN.search(s):
                cur["if_count"] += 1
            if _SWITCH_PATTERN.search(s):
                cur["switch_count"] += 1
            if _RETURN_PATTERN.search(s):
                cur["return_count"] += 1
            if _CATCH_PATTERN.search(s):
                cur["catch_count"] += 1
            if _SYSERR_PATTERN.search(s):
                cur["has_syserr"] = True

    return methods


def build_report(methods: list[dict]) -> dict:
    """构建分析报告。"""
    method_map = {m["name"]: m for m in methods}

    # 构建调用链
    call_graph: dict[str, list[str]] = {}
    for m in methods:
        calls = [c for c in m["calls_this"] if c in method_map]
        call_graph[m["name"]] = calls

    # 入口链追踪（从 main_100）
    entry = "main_100" if "main_100" in method_map else (methods[0]["name"] if methods else "")

    # 统计
    total_repo_find = sum(len(m["repo_find"]) for m in methods)
    total_repo_save = sum(len(m["repo_save"]) for m in methods)
    total_repo_update = sum(len(m["repo_update"]) for m in methods)
    total_repo_delete = sum(len(m["repo_delete"]) for m in methods)
    total_this_calls = sum(len(m["calls_this"]) for m in methods)
    total_if = sum(m["if_count"] for m in methods)
    total_switch = sum(m["switch_count"] for m in methods)
    total_return = sum(m["return_count"] for m in methods)
    total_syserr = sum(1 for m in methods if m["has_syserr"])

    # 方法分类
    section_methods = [m for m in methods if re.match(r'^[a-z]+\d+', m['name'])]
    utility_methods = [m for m in methods if not re.match(r'^[a-z]+\d+', m['name'])]

    return {
        "program": "ZPOLDWNM",
        "side": "Java",
        "file": "ZpoldwnmServiceImpl.java",
        "total_methods": len(methods),
        "section_methods": len(section_methods),
        "utility_methods": len(utility_methods),
        "entry_method": entry,
        "stats": {
            "repo_find": total_repo_find,
            "repo_save": total_repo_save,
            "repo_update": total_repo_update,
            "repo_delete": total_repo_delete,
            "total_io": total_repo_find + total_repo_save + total_repo_update + total_repo_delete,
            "this_calls": total_this_calls,
            "if_count": total_if,
            "switch_count": total_switch,
            "return_count": total_return,
            "syserr_count": total_syserr,
        },
        "methods": [
            {
                "name": m["name"],
                "lines": f"{m['start_line']}-{m['end_line']}",
                "calls": m["calls_this"],
                "repo_find": m["repo_find"],
                "repo_save": m["repo_save"],
                "repo_update": m["repo_update"],
                "repo_delete": m["repo_delete"],
                "if_count": m["if_count"],
                "return_count": m["return_count"],
            }
            for m in methods
        ],
        "call_graph": call_graph,
    }


def main():
    ap = argparse.ArgumentParser(description="Java Service 逻辑结构分析")
    ap.add_argument("--in", dest="infile", required=True, help="Java 源文件路径")
    ap.add_argument("--out", default="output/java-logic", help="输出目录")
    ap.add_argument("--json", action="store_true", help="仅输出 JSON")
    args = ap.parse_args()

    with open(args.infile, encoding="utf-8") as f:
        lines = f.readlines()

    methods = extract_methods(lines)
    report = build_report(methods)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # JSON 输出
    json_path = out_dir / "java_analysis.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"✅ JSON: {json_path}")

    if not args.json:
        print(f"\n{'='*50}")
        print(f"  ZPOLDWNM Java Service 分析报告")
        print(f"{'='*50}")
        print(f"  总方法数    : {report['total_methods']}")
        print(f"  业务段方法  : {report['section_methods']}")
        print(f"  工具方法    : {report['utility_methods']}")
        print(f"  入口        : {report['entry_method']}")
        print(f"\n  IO 操作统计:")
        print(f"    READR(finds) : {report['stats']['repo_find']}")
        print(f"    WRITR(saves) : {report['stats']['repo_save']}")
        print(f"    UPDAT(update): {report['stats']['repo_update']}")
        print(f"    DELET(delete): {report['stats']['repo_delete']}")
        print(f"    IO 总计      : {report['stats']['total_io']}")
        print(f"\n  控制流:")
        print(f"    this.xxx 调用: {report['stats']['this_calls']}")
        print(f"    if 条件分支  : {report['stats']['if_count']}")
        print(f"    switch 分支  : {report['stats']['switch_count']}")
        print(f"    return 语句  : {report['stats']['return_count']}")
        print(f"    sysErr 处理  : {report['stats']['syserr_count']}")
        print(f"\n  前 10 个方法（按调用链）:")
        entry = report['entry_method']
        visited = set()
        stack = [entry]
        while stack and len(visited) < 10:
            m = stack.pop(0)
            if m in visited:
                continue
            visited.add(m)
            for c in report['call_graph'].get(m, [])[:3]:
                if c not in visited:
                    stack.append(c)
        for m in visited:
            md = next((x for x in report['methods'] if x['name'] == m), None)
            if md:
                io = len(md['repo_find']) + len(md['repo_save']) + len(md['repo_update']) + len(md['repo_delete'])
                print(f"    {m:30s} 行{md['lines']:10s}  IO={io}")


if __name__ == "__main__":
    main()
