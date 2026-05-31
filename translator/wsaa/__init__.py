"""
translator.wsaa —— WORKING-STORAGE 树 → Java 类（确定性渲染，无 LLM）。

对应设计：docs/详细设计/步骤03-WSAA块翻译设计.md。
对外暴露 render_wsaa(roots, program) -> str。
内部分工：render_field（字段）/ render_view（重叠组+REDEFINES）/
render_condition（88）/ render_class（组装）。
"""
from __future__ import annotations

from translator.wsaa.render_class import render_wsaa

__all__ = ["render_wsaa"]
