"""
写文件 + 清单（输出 A）。

职责：把各 Block 落盘为切片文件，并生成 manifest.json（入库数据源）与 manifest.md（人读清单）。
对应设计文档：步骤02 §4 Block B —— 切片写入 out_dir/拆解/，两个 manifest 写 out_dir 根。
依赖 decompose/blocks.py（slug_filename）；被 decompose/core.py 调用。
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .blocks import slug_filename

SLICE_SUBDIR = "拆解"   # 切片子目录名（manifest 留在程序目录根，切片下沉到此）


def _doc(block) -> dict:
    """Block → 入库/manifest 文档（展平 extra，去掉内部字段）。"""
    d = asdict(block)
    extra = d.pop("extra", {}) or {}
    d.update(extra)
    return d


def write_files(blocks: list, meta, ws, out_dir: Path) -> dict:
    """写各 SECTION 切片 + WSAA 切片到 out_dir/拆解/，manifest.json/md 写 out_dir 根。返回统计。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    slice_dir = out_dir / SLICE_SUBDIR
    slice_dir.mkdir(parents=True, exist_ok=True)
    used: set[str] = set()
    section_index: list[dict] = []

    # WORKING-STORAGE 切片
    ws_file = f"{ws.block_name}.cob"
    (slice_dir / ws_file).write_text(ws.raw_text + "\n", encoding="utf-8")

    # SECTION 切片
    for b in blocks:
        fname = slug_filename(b.block_name, used)
        (slice_dir / fname).write_text(b.raw_text + "\n", encoding="utf-8")
        section_index.append({
            "block_index": b.block_index,
            "block_name": b.block_name,
            "file": fname,
            "start_line": b.start_line,
            "end_line": b.end_line,
            "lines": b.raw_text.count("\n") + 1 if b.raw_text else 0,
        })

    # manifest.json：含全部入库字段（后补入库的数据源）
    all_docs = [_doc(meta), _doc(ws)] + [_doc(b) for b in blocks]
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "program": meta.program,
        "source_file": meta.source_file,
        "class_name": meta.extra["class_name"],
        "ws_block_name": meta.extra["ws_block_name"],
        "params_in": meta.extra["params_in"],
        "copies": meta.extra["copies"],
        "section_count": meta.extra["section_count"],
        "total_blocks": len(all_docs),
        "sections": section_index,
        "documents": all_docs,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # manifest.md：人读清单
    md = _render_manifest_md(manifest)
    (out_dir / "manifest.md").write_text(md, encoding="utf-8")

    return {
        "out_dir": str(out_dir),
        "slice_dir": str(slice_dir),
        "section_files": len(blocks),
        "ws_file": ws_file,
        "total_blocks": len(all_docs),
    }


def _render_manifest_md(m: dict) -> str:
    lines = [
        f"# {m['program']} 拆解清单",
        "",
        f"- 源文件：`{m['source_file']}`",
        f"- 类名：`{m['class_name']}`",
        f"- 参数块：`{m['ws_block_name']}`",
        f"- 入参：{m['params_in']}",
        f"- SECTION 数：{m['section_count']}",
        f"- 总块数（含 META + WS）：{m['total_blocks']}",
        "",
        "## COPY 分类",
        f"- rec_skm（实体类字段定义，{len(m['copies']['rec_skm'])}）：{', '.join(m['copies']['rec_skm'])}",
        f"- varcom（处理逻辑/方法，{len(m['copies']['varcom'])}）：{', '.join(m['copies']['varcom'])}",
        f"- other（{len(m['copies']['other'])}）：{', '.join(m['copies']['other'])}",
        "",
        "## SECTION 清单",
        "",
        "| # | SECTION | 文件 | 起 | 止 | 行数 |",
        "|---|---|---|---|---|---|",
    ]
    for s in m["sections"]:
        lines.append(
            f"| {s['block_index']} | {s['block_name']} | {s['file']} "
            f"| {s['start_line']} | {s['end_line']} | {s['lines']} |"
        )
    return "\n".join(lines) + "\n"
