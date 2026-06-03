"""
config.grammar_loader —— COBOL 文法访问层（步骤08）。

用途：集中加载「切分文法」两正本并对外提供查询；segmenter / cobol_columns / rules 经本层取规范，
      不直接读 yaml（补 COBOL 语法只改 config + 实现跟随，不散落硬编码）。
对应设计：docs/详细设计/步骤08-文法驱动骨架构建设计.md §3.2。
正本：config/specs/segmentation_spec.yaml（物理切分：列模型 / 词法 / paragraph 模型）、
      config/specs/skeleton_spec.yaml（骨架文法：block_grammar / control_flow）。
      （步骤09：yaml 加载统一经 config.yaml_cache，按裸文件名自动解析子目录。）
与 config.spec_loader（翻译规范访问层）并列、互不耦合。

用法：
  from config import grammar_loader
  grammar_loader.column_model()             # -> {indicator_col, area_a, area_b, clean_slice}
  grammar_loader.verbs()                     # -> frozenset({'MOVE', ...})
  grammar_loader.paragraph_label(" 1510-START.")  # -> '1510-START' / None
  grammar_loader.block_grammar()             # -> [ {id: 'if', ...}, ... ]
  grammar_loader.back_edge_state_machine()   # -> True
"""
from __future__ import annotations

import re
from functools import lru_cache

from config.yaml_cache import load as _load   # 唯一 YAML 加载入口（步骤09）


def _seg() -> dict:
    return _load("segmentation_spec.yaml")


def _skel() -> dict:
    return _load("skeleton_spec.yaml")


# ── 列模型 / 词法字典 ────────────────────────────────────────────────────────

def column_model() -> dict:
    """列模型：indicator_col / area_a / area_b / clean_slice（1-based 列号）。"""
    return _seg()["column_model"]


@lru_cache(maxsize=None)
def verbs() -> frozenset:
    """语句起始动词集（大写）。"""
    return frozenset(v.upper() for v in _seg()["lexicon"]["verbs"])


@lru_cache(maxsize=None)
def scope_terminators() -> frozenset:
    """块作用域关键字集（大写）。"""
    return frozenset(v.upper() for v in _seg()["lexicon"]["scope_terminators"])


@lru_cache(maxsize=None)
def perform_keywords() -> frozenset:
    """PERFORM 内联循环关键字集（大写）。"""
    return frozenset(v.upper() for v in _seg()["lexicon"]["perform_keywords"])


# ── paragraph 标号判定（Bug 1 核心：列模型驱动，非魔数）──────────────────────

@lru_cache(maxsize=None)
def _label_re():
    return re.compile(_seg()["paragraph_model"]["pattern"])


def paragraph_label(clean_line: str) -> str | None:
    """净化行若为 Area A paragraph 标号→返回大写名，否则 None。

    判定（列模型驱动）：净化行前导空格数 < Area B 起始索引(area_b.start - indicator_col)
    ⟺ 名字落在 Area A（标号区）；落在 Area B 即语句。再过 paragraph 正则 + 排除动词/终止符
    （EXIT./CONTINUE. 等不是标号）。兼容真实管线(clean_line 带指示列空格, lead≥1)与
    理想化输入(lead=0)。
    """
    s = clean_line
    stripped = s.strip()
    if not stripped:
        return None
    cm = column_model()
    b0 = cm["area_b"]["start"] - cm["indicator_col"]   # Area B 在净化行的起始索引
    if (len(s) - len(s.lstrip())) >= b0:               # 落在 Area B → 语句，非标号
        return None
    m = _label_re().match(stripped)
    if not m:
        return None
    name = m.group(1).upper()
    if name in verbs() or name in scope_terminators():
        return None
    return name


# ── 骨架文法 / 控制流策略 ────────────────────────────────────────────────────

def block_grammar() -> list:
    """段内块构造表（if/evaluate/perform；_Parser 实现对照与取参）。"""
    return _skel()["block_grammar"]


def back_edge_state_machine() -> bool:
    """控制流降级开关：存在回跳 GO TO 是否降级为 while+switch 状态机。"""
    return bool(_skel()["control_flow"].get("back_edge_to_state_machine", True))
