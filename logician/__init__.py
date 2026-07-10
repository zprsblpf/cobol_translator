"""
逻辑文档生成器 — 门面模块。

用法：
    from logician import generate, save, generate_and_save

    # 从 parser 解析结果生成
    doc = generate(program)

    # 保存
    save(doc, "output/logic-doc/program.logic.json", fmt="json")
    save(doc, "output/logic-doc/program.logic.md", fmt="md")

    # 一键生成双输出
    generate_and_save(program, "output/logic-doc/")
"""
from __future__ import annotations

import os

from logician.builder import generate as _build
from logician.output import save_json, render_md


def generate(program, ws_tree=None) -> "LogicDoc":
    """从 CobolProgram 生成逻辑文档。

    Args:
        program: parser.cobol_parser.CobolProgram 对象
        ws_tree: 可选，parser.ws 解析的 WsNode 森林，用于 88 条件名展开

    Returns:
        LogicDoc 实例
    """
    from logician.models import LogicDoc
    return _build(program, ws_tree=ws_tree)


def save(doc, path: str, fmt: str = "json"):
    """保存逻辑文档到文件。

    Args:
        doc: LogicDoc 实例
        path: 输出文件路径
        fmt: "json" 或 "md"
    """
    if fmt == "json":
        save_json(doc, path)
    elif fmt == "md":
        md = render_md(doc)
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
    else:
        raise ValueError(f"unsupported format: {fmt}")


def generate_and_save(program, out_dir: str, base_name: str | None = None, ws_tree=None):
    """生成逻辑文档并保存 JSON + Markdown。

    Args:
        program: CobolProgram 对象
        out_dir: 输出目录
        base_name: 文件名前缀（默认用 program_id）
        ws_tree: 可选，parser.ws 解析的 WsNode 森林
    """
    doc = generate(program, ws_tree=ws_tree)
    name = base_name or doc.program_id or "program"
    os.makedirs(out_dir, exist_ok=True)

    json_path = os.path.join(out_dir, f"{name}.logic.json")
    save(doc, json_path, fmt="json")

    md_path = os.path.join(out_dir, f"{name}.logic.md")
    save(doc, md_path, fmt="md")

    return doc, json_path, md_path
