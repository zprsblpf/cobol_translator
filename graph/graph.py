"""
LangGraph 工作流：COBOL → Java 翻译。

节点流：
  parse_cobol
      ↓
  build_context_and_skeleton
      ↓
  [Send: translate_section × N sections]（并行，最多 4 路，受 vLLM max-num-seqs 限制）
      ↓ (join: 所有 translate_section 完成后)
  assemble
"""
from __future__ import annotations

import asyncio
from langgraph.graph import StateGraph, END, START
from langgraph.types import Send

from graph.state import TranslationState
from graph.nodes import (
    parse_cobol_node,
    build_context_and_skeleton_node,
    translate_section_node,
    assemble_node,
)

# vLLM 并发限制（max-num-seqs=4）
MAX_PARALLEL = 4


def _route_after_parse(state: TranslationState) -> str:
    if state.get("status") == "error":
        return "abort"
    return "continue"


def _send_sections(state: TranslationState) -> list[Send]:
    """为每个 SECTION 发送一个并行翻译任务（通过 Send API）。"""
    sections = state.get("sections_meta", [])
    # 翻译用不到的大字段从子状态剔除，减小并行消息体积
    # （module_assignment / java_field_names / field_type_map / var_lifecycle / call_graph 需保留）
    base = dict(state)
    for k in ("module_skeletons", "state_class_source", "facade_skeleton", "java_skeleton"):
        base.pop(k, None)
    sends = []
    for sec in sections:
        child_state = dict(base)
        child_state["current_section"] = sec
        sends.append(Send("translate_section", child_state))
    return sends


def build_graph():
    workflow = StateGraph(TranslationState)

    workflow.add_node("parse_cobol", parse_cobol_node)
    workflow.add_node("build_context", build_context_and_skeleton_node)
    workflow.add_node("translate_section", translate_section_node)
    workflow.add_node("assemble", assemble_node)

    workflow.add_edge(START, "parse_cobol")
    workflow.add_conditional_edges(
        "parse_cobol",
        _route_after_parse,
        {"continue": "build_context", "abort": END},
    )
    # 构建骨架后，用 Send API 并行派发所有 SECTION 翻译
    workflow.add_conditional_edges(
        "build_context",
        _send_sections,
        ["translate_section"],
    )
    # 所有 translate_section 完成后汇聚到 assemble
    workflow.add_edge("translate_section", "assemble")
    workflow.add_edge("assemble", END)

    return workflow.compile()


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
