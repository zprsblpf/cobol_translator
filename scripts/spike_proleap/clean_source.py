#!/usr/bin/env python3
"""
clean_source.py —— ProLeap 解析前的源清理（spike 用，处理本 shop 方言）

用途：
  本 shop 的定宽 COBOL 源带两类标准解析器不认的方言，会让 ProLeap 解析失败：
    1. 行尾变更标记 ``<A36415>`` 等：本应在 73-80 列；含中文(双宽)行上 ProLeap
       按字符列截断会把标记算进 7-72 代码区 → 语法错误；
    2. ``!!!!!!`` 停用行（1-6 列全 ``!``）：本 shop 用它注释失效整行，而 ProLeap
       把 1-6 列当序号区忽略 → 误把停用行当有效代码。
  本脚本把这两类清掉，输出 ProLeap 可吃的干净源。仅 spike 验证用，不改原文件。

对应设计文档：docs/调研/ProLeap解析器评估调研.md（亦呼应步骤06 列对齐与停用行修复）

设计思路：
  - 全程参数化（输入源 / 输出源），逐行处理、保持行号不变（停用行清空而非删除，
    使 ProLeap 报错行号仍可对回原文件）；
  - 变更标记用保守正则只匹配「空白 + <字母数字> + 行尾」，不误伤 COBOL 的 ``<`` 比较符；
  - CRLF 归一为 LF。

用法：
  python3 clean_source.py <输入源.cob> <输出源.cob>
"""
import re
import sys
from pathlib import Path

# 行尾变更标记：至少 1 个前导空白 + <字母数字 3~10 位> + 行尾。
# 长度与字符集限制避免误伤 `IF A < B` 这类比较符（其 < 两侧是单空格、无闭合 >）。
_CHANGE_TAG = re.compile(r"\s+<[A-Za-z0-9]{3,10}>\s*$")

# 方言 `GO <段名>`（省略 TO）→ 标准 `GO TO <段名>`。ProLeap 文法只认 GO TO。
# 仅匹配 GO + 空白 + 非 TO 的段名首字符，避免误伤 GOBACK / GO TO。
_GO_NO_TO = re.compile(r"\bGO\s+(?!TO\b)(?=[0-9A-Za-z])")


def clean_line(raw: str) -> str:
    """清理单行：停用行→空行；去行尾变更标记；GO→GO TO 归一。"""
    line = raw.rstrip("\r\n")
    if line[:6] and set(line[:6]) == {"!"}:  # 1-6 列全 ! → 停用行，整行清空
        return ""
    line = _CHANGE_TAG.sub("", line)
    return _GO_NO_TO.sub("GO TO ", line)


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("用法: clean_source.py <输入源.cob> <输出源.cob>", file=sys.stderr)
        return 2
    src = Path(argv[1])
    out = Path(argv[2])

    lines = src.read_text(encoding="utf-8", errors="replace").splitlines()
    cleaned = [clean_line(l) for l in lines]
    deact = sum(1 for l, c in zip(lines, cleaned) if c == "" and l.strip())
    tagged = sum(1 for l, c in zip(lines, cleaned)
                 if c != "" and _CHANGE_TAG.search(l.rstrip("\r\n")))

    out.write_text("\n".join(cleaned) + "\n", encoding="utf-8")
    print(f"总行={len(lines)} 停用行清空={deact} 去标记行={tagged} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
