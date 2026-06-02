"""
translator.skeleton_gen —— cob → Java 主类骨架引擎（确定性渲染，无 LLM）。

对应设计：docs/详细设计/步骤05-cob到Java翻译引擎详细设计.md。
对外暴露 render_skeleton(program) -> str。
内部分工：program_model（CobolProgram→骨架要素）→ copy_resolver（COPY 角色分流）→
          render_skeleton（装配主类）。规范经 config.spec_loader 取，不直接读 yaml。

说明：包名为 skeleton_gen（非 skeleton），因同目录旧 translator/skeleton.py 仍被多处引用、
      与 skeleton/ 包不可共存（见设计 §2-6）。
"""
from __future__ import annotations

from translator.skeleton_gen.render_skeleton import render_skeleton

__all__ = ["render_skeleton"]
