#!/usr/bin/env python3
"""
config 配置层重构 —— 回归快照脚本（步骤09）。

用途：把所有"确定性、config 驱动"的函数对一组代表性输入的输出，序列化成稳定 JSON 快照。
      步骤09 重构是纯结构整理，**不得改变任何输出**，故重构前后两次运行本脚本，
      diff 必须为空（逐字节一致），作为回归依据。
对应设计：docs/详细设计/步骤09-config配置层重构设计.md §六-7。

用法：
    python scripts/regress_config_snapshot.py > /tmp/snap_before.json   # 重构前
    python scripts/regress_config_snapshot.py > /tmp/snap_after.json    # 重构后
    diff /tmp/snap_before.json /tmp/snap_after.json                      # 应无差异
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import spec_loader, grammar_loader  # noqa: E402

# 代表性 PIC 签名集（覆盖 type_mappings 各规则分支）
_PICS = [
    "X(04)", "A(10)", "9(06)", "9(09)", "9(15)", "S9(15)V9(2)", "9(7)V99",
    "S9(9) COMP-3", "S9(4) COMP", "ZZZ,ZZ9.99", "***9", "X", "9", "99",
    "S9(18)", "9(10)", "PIC 1", "V9(2)",
]
# 代表性 COBOL 名（命名转换）
_NAMES = ["WSAA-PROG", "WSAA-POLICY-NO", "ZPOLDWNM", "WSAA", "X-Y-Z-1"]
# 代表性 COPY 名（角色 / 实体类 / 服务类）
_COPIES = ["VARCOM", "COVRSKM", "ITEMKEY", "LETCMNTSKM", "DATCON1REC",
           "TW001REC", "UNKNOWN99", "ZSOSCLTSKM"]
# 代表性 CALL（IO 解析：范式派生 + 增量覆盖 + 非 *IO）
_CALLS = ["SCF4CHRIO", "CHDRENQIO", "CLNTIO", "AGNTIO", "DATCON1", "SYSERR", "FOO"]
# 代表性净化行（paragraph 标号判定）
_LINES = [" 2071-CALL-PS01.", "     MOVE A TO B.", " 1000-INIT.",
          "     EXIT.", " EXIT.", "        PERFORM 1000-INIT."]


def snapshot() -> dict:
    """收集所有确定性 config 函数的输出，返回可 JSON 序列化的 dict。"""
    snap: dict = {}

    # spec_loader：类型 / 命名 / COPY 角色与类名
    snap["java_type_of"] = {p: spec_loader.java_type_of(p) for p in _PICS}
    snap["field_name"] = {n: spec_loader.field_name(n) for n in _NAMES}
    snap["class_name"] = {n: spec_loader.class_name(n) for n in _NAMES}
    snap["copy_role"] = {c: spec_loader.copy_role(c) for c in _COPIES}
    snap["entity_class"] = {c: spec_loader.entity_class(c) for c in _COPIES}
    snap["service_class"] = {c: spec_loader.service_class(c) for c in _COPIES}
    snap["service_field"] = {c: spec_loader.service_field(c) for c in _COPIES}

    # grammar_loader：列模型 / 词法 / paragraph 判定 / 控制流
    snap["column_model"] = grammar_loader.column_model()
    snap["verbs"] = sorted(grammar_loader.verbs())
    snap["scope_terminators"] = sorted(grammar_loader.scope_terminators())
    snap["perform_keywords"] = sorted(grammar_loader.perform_keywords())
    snap["block_grammar"] = grammar_loader.block_grammar()
    snap["back_edge_state_machine"] = grammar_loader.back_edge_state_machine()
    snap["paragraph_label"] = {ln: grammar_loader.paragraph_label(ln) for ln in _LINES}

    # 下沉的纯函数（conversions）：经现引用点取，重构后仍须一致
    from parser.ws.value import java_init
    snap["java_init"] = {
        f"{v}|{t}": java_init(v, t)
        for v in ["SPACES", "ZEROS", "'ABC'", "X'0F'", "B'1'", "123", "12.5"]
        for t in ["String", "int", "BigDecimal"]
    }

    # IO 解析（范式派生 + 增量覆盖），经访问层取
    from translator.rules import resolve_io_info
    io_progs = spec_loader.io_programs()
    io_pat = spec_loader.io_default_pattern()
    snap["resolve_io_info"] = {c: resolve_io_info(c, io_progs, io_pat) for c in _CALLS}
    return snap


if __name__ == "__main__":
    json.dump(snapshot(), sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
