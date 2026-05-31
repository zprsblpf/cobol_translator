"""
PIC 子句 → Java 类型 + 字符宽度 + 是否数字编辑。

对应设计：docs/详细设计/步骤03-WSAA块翻译设计.md。

设计思路（固化用户给的 WORKING-STORAGE 规范）：
- 普通类型判定复用 config/type_mappings.yaml 的 pic_rules（与翻译线一致）；
- 额外识别「数字编辑 PIC」（含 Z/*/插入字符 . , / B 0 - +）→ Java 用 String（显示串）；
- 计算「字符宽度」byte_len：供重叠组 / REDEFINES 派生视图做定宽切片。
  规则：X(n)/A(n)/9(n)/Z(n)/*(n) 各计 n 位；S、V 计 0 位；插入字符各计 1 位；
  COMP-3 计 ceil((数字位数+1)/2) 字节（打包，少用于视图）。
"""
from __future__ import annotations

import re
import math

_EDIT_CHARS = set("Z*.,/B+-$")            # 数字编辑标志字符
_LEN_TOKEN = re.compile(r"([A-Za-z9*])(?:\((\d+)\))?")  # 形如 X(07) / 9 / Z(14)


def is_edited(pic: str) -> bool:
    """含编辑字符且非纯 9/X/S/V/A → 数字编辑 PIC（显示格式串）。"""
    u = pic.upper()
    return any(c in _EDIT_CHARS for c in u) and not re.fullmatch(r"[SVX9A()0-9]+", u)


def char_width(pic: str, comp: str = "") -> int:
    """单次出现的字符宽度（COMP-3 返回打包字节数）。"""
    u = pic.upper().replace(" ", "")
    if not u:
        return 0
    if "COMP-3" in comp.upper() or "COMP" in comp.upper():
        digits = sum(int(n) if n else 1
                     for c, n in _LEN_TOKEN.findall(u) if c in "9")
        return math.ceil((digits + 1) / 2) if digits else 0
    width = 0
    for c, n in _LEN_TOKEN.findall(u):
        cnt = int(n) if n else 1
        if c in ("S", "V"):          # 符号、隐含小数点：display 不占位
            continue
        width += cnt                 # X/A/9/Z/* 及插入字符（各 1）
    return width


def _digits(text: str) -> int:
    """统计整数位数（9 的总个数）：9(n) 计 n，裸 9 各计 1。"""
    t = text.upper()
    total = sum(int(n) for n in re.findall(r"9\((\d+)\)", t))
    stripped = re.sub(r"[A-Za-z]?\(\d+\)", "", t)   # 去掉所有 X(07)/9(15) 等带括号项
    return total + stripped.count("9")


def _match_rule(text: str, rules: list[dict]) -> str | None:
    """按 config/type_mappings.yaml 的 pic_rules（首个命中）解析 java 类型。"""
    for r in rules:
        pat = r.get("pattern")
        if not pat or not re.search(pat, text, re.IGNORECASE):
            continue
        md = r.get("max_digits")
        if md and _digits(text) > md:   # 位数上限：超过则跳过（不算 int）
            continue
        return r.get("java_type")
    return None


def java_type(pic: str, comp: str, type_rules: list[dict]) -> tuple[str, bool]:
    """返回 (java_type, is_edited)。类型判定由 config/type_mappings.yaml 驱动。"""
    if pic.strip() == "1":            # INDICATOR PIC 1 → boolean
        return "boolean", False
    if is_edited(pic):                # 数字编辑 PIC → 显示串
        return "String", True
    # pic_rules 的部分模式含 COMP-3，需把 comp 文本拼上一起匹配
    text = f"{pic} {comp}".strip()
    jt = _match_rule(text, type_rules)
    return (jt or "String"), False
