"""
COBOL 语句切分（确定性）。把一个 SECTION 的代码行解析为语句/语句块树。

不追求完美解析（罕见/切不准的结构最终由规则引擎走 LLM 兜底），但能可靠识别
控制流骨架：IF/ELSE/END-IF、EVALUATE/WHEN/END-EVALUATE、PERFORM…END-PERFORM、
GO TO，以及叶子语句（MOVE/COMPUTE/ADD/CALL…）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Stmt:
    kind: str                                  # simple | if | evaluate | perform
    tokens: list[str] = field(default_factory=list)   # simple: 全句; if: 条件; perform: 头部; evaluate: 主语
    children: list["Stmt"] = field(default_factory=list)     # if-then 分支 / perform 内联体
    else_children: list["Stmt"] = field(default_factory=list)  # if-else 分支
    whens: list = field(default_factory=list)  # evaluate: [(cond_tokens, [Stmt]), ...]
    raw: str = ""                              # 原始 COBOL 文本（注释 / LLM 兜底用）


# 语句起始动词（用于切分相邻无句点语句、判定条件结束）
VERBS = {
    "MOVE", "COMPUTE", "ADD", "SUBTRACT", "MULTIPLY", "DIVIDE", "PERFORM", "GO",
    "IF", "EVALUATE", "CALL", "SET", "INITIALIZE", "STRING", "UNSTRING", "ACCEPT",
    "DISPLAY", "OPEN", "CLOSE", "READ", "WRITE", "REWRITE", "DELETE", "START",
    "CONTINUE", "NEXT", "EXIT", "STOP", "GOBACK", "RETURN", "SEARCH", "INSPECT",
}

# 块作用域关键字
_TERMINATORS = {"END-IF", "END-PERFORM", "END-EVALUATE", "ELSE", "WHEN", "THEN"}

# PERFORM 头部允许的内联循环关键字（这些不算"过程名"）
_PERFORM_KW = {"VARYING", "UNTIL", "WITH", "TEST", "BEFORE", "AFTER", "TIMES", "THRU", "THROUGH", "FROM", "BY"}

_DECIMAL_RE = re.compile(r"^[+-]?\d+\.\d+$")


def _tokenize(lines: list[str]) -> list[str]:
    text = " ".join(lines)
    tokens: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c in ("'", '"'):
            q = c
            j = i + 1
            while j < n and text[j] != q:
                j += 1
            tokens.append(text[i:min(j + 1, n)])
            i = j + 1
            continue
        j = i
        while j < n and not text[j].isspace():
            j += 1
        word = text[i:j]
        i = j
        if word == ".":
            tokens.append(".")
        elif word.endswith(".") and not _DECIMAL_RE.match(word):
            core = word[:-1]
            if core:
                tokens.append(core)
            tokens.append(".")
        else:
            tokens.append(word)
    return tokens


def _is_verb(tok: str) -> bool:
    return tok.upper() in VERBS


class _Parser:
    def __init__(self, tokens: list[str]):
        self.t = tokens
        self.n = len(tokens)
        self.i = 0

    def _up(self, k: int = 0) -> str:
        j = self.i + k
        return self.t[j].upper() if 0 <= j < self.n else ""

    def parse_statements(self, stop: set[str]) -> list[Stmt]:
        stmts: list[Stmt] = []
        while self.i < self.n:
            u = self._up()
            if u == ".":
                # 句点：结束当前块（由顶层消费）
                break
            if u in stop:
                break
            stmt = self._parse_one(stop)
            if stmt is not None:
                stmts.append(stmt)
            else:
                self.i += 1  # 防御：跳过无法处理的孤立 token
        return stmts

    def _parse_one(self, stop: set[str]) -> Stmt | None:
        u = self._up()
        if u == "IF":
            return self._parse_if(stop)
        if u == "EVALUATE":
            return self._parse_evaluate(stop)
        if u == "PERFORM":
            return self._parse_perform(stop)
        return self._parse_simple(stop)

    def _parse_simple(self, stop: set[str]) -> Stmt:
        start = self.i
        toks = [self.t[self.i]]
        self.i += 1
        # 收集到下一个动词 / 句点 / 终止符
        while self.i < self.n:
            u = self._up()
            if u == "." or u in stop or u in _TERMINATORS or _is_verb(u):
                break
            toks.append(self.t[self.i])
            self.i += 1
        return Stmt(kind="simple", tokens=toks, raw=" ".join(self.t[start:self.i]))

    def _collect_condition(self) -> list[str]:
        """收集条件 token：到 THEN / 动词 / 句点 / 终止符为止。"""
        cond: list[str] = []
        while self.i < self.n:
            u = self._up()
            if u == "THEN":
                self.i += 1
                break
            if u == "." or u in _TERMINATORS or _is_verb(u):
                break
            cond.append(self.t[self.i])
            self.i += 1
        return cond

    def _parse_if(self, stop: set[str]) -> Stmt:
        start = self.i
        self.i += 1  # IF
        cond = self._collect_condition()
        then_branch = self.parse_statements(stop | {"ELSE", "END-IF"})
        else_branch: list[Stmt] = []
        if self._up() == "ELSE":
            self.i += 1
            else_branch = self.parse_statements(stop | {"END-IF"})
        if self._up() == "END-IF":
            self.i += 1
        return Stmt(kind="if", tokens=cond, children=then_branch,
                    else_children=else_branch, raw=" ".join(self.t[start:self.i]))

    def _parse_evaluate(self, stop: set[str]) -> Stmt:
        start = self.i
        self.i += 1  # EVALUATE
        subject: list[str] = []
        while self.i < self.n and self._up() not in ("WHEN", "END-EVALUATE", "."):
            subject.append(self.t[self.i])
            self.i += 1
        whens = []
        while self._up() == "WHEN":
            self.i += 1
            cond: list[str] = []
            while self.i < self.n:
                u = self._up()
                if u in ("WHEN", "END-EVALUATE", ".") or _is_verb(u):
                    break
                cond.append(self.t[self.i])
                self.i += 1
            body = self.parse_statements(stop | {"WHEN", "END-EVALUATE"})
            whens.append((cond, body))
        if self._up() == "END-EVALUATE":
            self.i += 1
        return Stmt(kind="evaluate", tokens=subject, whens=whens,
                    raw=" ".join(self.t[start:self.i]))

    def _parse_perform(self, stop: set[str]) -> Stmt:
        start = self.i
        self.i += 1  # PERFORM
        header: list[str] = []
        # 收集头部：到动词（内联体起始）/ 句点 / 终止符 / END-PERFORM
        while self.i < self.n:
            u = self._up()
            if u in ("END-PERFORM", ".") or u in stop:
                break
            if _is_verb(u):
                break
            header.append(self.t[self.i])
            self.i += 1
        children: list[Stmt] = []
        # 内联体：下一个是动词或显式 END-PERFORM 前的语句
        if self.i < self.n and (_is_verb(self._up()) or self._up() not in ("END-PERFORM", ".")):
            if _is_verb(self._up()):
                children = self.parse_statements(stop | {"END-PERFORM"})
        if self._up() == "END-PERFORM":
            self.i += 1
        return Stmt(kind="perform", tokens=header, children=children,
                    raw=" ".join(self.t[start:self.i]))


# paragraph 标签：Area A（行首无缩进）的单 token + 句点，如 "2071-CALL-PS01."
_LABEL_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9-]*)\.\s*$")


def split_paragraphs(lines: list[str]) -> list[tuple[str | None, list[str]]]:
    """
    按 paragraph 标签把 SECTION 行切成 [(label_or_None, body_lines), ...]。
    COBOL paragraph 名写在 Area A（行首无缩进），语句在 Area B（有缩进），据此区分。
    首块若无前导标签则 label=None。动词/块终止符不视为标签（如 EXIT. / CONTINUE.）。
    """
    paras: list[tuple[str | None, list[str]]] = []
    cur_label: str | None = None
    cur_body: list[str] = []
    started = False
    for raw in lines:
        stripped = raw.strip()
        if stripped and raw[:1] not in (" ", "\t"):
            m = _LABEL_RE.match(stripped)
            if m and not _is_verb(m.group(1)) and m.group(1).upper() not in _TERMINATORS:
                if started:
                    paras.append((cur_label, cur_body))
                cur_label = m.group(1).upper()
                cur_body = []
                started = True
                continue
        cur_body.append(raw)
        started = True
    if started:
        paras.append((cur_label, cur_body))
    return paras


def segment(lines: list[str]) -> list[Stmt]:
    """把 SECTION 代码行解析为顶层语句列表。"""
    tokens = _tokenize(lines)
    p = _Parser(tokens)
    stmts: list[Stmt] = []
    while p.i < p.n:
        if p._up() == ".":
            p.i += 1  # 顶层消费句点
            continue
        before = p.i
        stmts.extend(p.parse_statements(set()))
        if p.i == before:
            p.i += 1  # 防御性推进，避免死循环
    return stmts
