"""
相1 方言归一：把本 shop 源码方言归一为标准 COBOL（源码层文本归一，不改语义）。

对应设计：docs/详细设计/步骤16-相1方言归一吸收设计.md §3.3。
正本链：docs/翻译标准/流程结构.md（源头）→ config/specs/segmentation_spec.yaml `dialect_normalization`
        （机读模板）→ 本模块（只读应用）。**本文件不内嵌任何方言正则**——规则全来自 config，
        代码只负责「怎么安全套用」（遍历规则 + 引号保护这一 COBOL 语义）。
"""
from __future__ import annotations


def _segment_by_quotes(code: str) -> list[tuple[str, bool]]:
    """把行切成「引号外/引号内」交替段，返回 [(文本, 是否引号内), ...]。

    单/双引号皆为字符串定界；遇定界符开串、遇同字符闭串。未闭合的尾段按「引号内」处理（保守不改）。
    """
    segs: list[tuple[str, bool]] = []
    q: str | None = None
    start = 0
    for i, c in enumerate(code):
        if q is None:
            if c in ("'", '"'):
                segs.append((code[start:i], False))   # 引号外段
                q, start = c, i
        elif c == q:
            segs.append((code[start:i + 1], True))     # 含闭定界符的引号内段
            q, start = None, i + 1
    segs.append((code[start:], q is not None))         # 尾段：未闭合则视为引号内
    return segs


def _apply_outside_quotes(code: str, pat, repl: str) -> str:
    """仅对引号外文本段施加 pat→repl 替换，引号内原样保留。"""
    return "".join(
        (pat.sub(repl, text) if not quoted else text)
        for text, quoted in _segment_by_quotes(code)
    )


def normalize(code: str) -> str:
    """按 config 方言规则归一一行代码。

    规则源自 grammar_loader.dialect_rules()（正本 = segmentation_spec.dialect_normalization）；
    `quote_guard` 规则仅作用于引号外，余者整行替换。规则为空时原样返回（零行为变化）。
    """
    from config import grammar_loader   # 延迟导入，避免加载期环依赖（仿 columns.clean_line）
    for _name, pat, repl, quote_guard in grammar_loader.dialect_rules():
        code = _apply_outside_quotes(code, pat, repl) if quote_guard else pat.sub(repl, code)
    return code
