"""
config.spec_loader —— 规范访问层（步骤05 §6.1）。

用途：集中加载翻译规范三件套并对外提供查询，骨架引擎与 WS 渲染引擎**都经本层取规范**，
      不直接读 yaml（加类型/构造尽量只改 config、不改引擎）。
对应设计：docs/详细设计/步骤05-cob到Java翻译引擎详细设计.md。
规范正本：config/wsaa_translation_spec.yaml；配套：type_mappings.yaml / naming_conventions.yaml / copy_mappings.yaml。

用法：
  from config import spec_loader
  spec_loader.java_type_of("S9(15)V9(2)")      # -> "BigDecimal"
  spec_loader.init_of(node)                    # -> '"ZPOLDWN"' / "BigDecimal.ZERO" ...
  spec_loader.field_name("WSAA-PROG")          # -> "wsaaProg"
  spec_loader.class_name("ZPOLDWNM")           # -> "Zpoldwnm"
  spec_loader.copy_role("VARCOM")              # -> "service" / "entity" / "constant"
  spec_loader.entity_class("LETCMNTSKM")       # -> "LetcmntParams"
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

from parser.variable_resolver import _cobol_to_java_name   # 复用命名（§6.1）
from parser.ws.value import java_init                       # 复用 VALUE→Java 初值

_CONFIG_DIR = Path(__file__).parent

# 无 VALUE 时按 java_type 的初值（查表型，与步骤03 render_field 原 _DEFAULTS 一致，保证回归不变）
_DEFAULTS = {"String": '""', "int": "0", "long": "0",
             "BigDecimal": "BigDecimal.ZERO", "boolean": "false"}

# Java 语句样式串集中为格式常量（§5：避免散落在各 render 函数硬编码）
FIELD_DECL = "    private {type} {name} = {init};{comment}"


@lru_cache(maxsize=None)
def _load(name: str) -> dict:
    """加载并缓存一个 config yaml。"""
    with open(_CONFIG_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ── 标量类型 / 初值（查表型）────────────────────────────────────────────────

def _count_digits(pic: str) -> int:
    """统计 PIC 中数字位数（9(n) 展开 + 裸 9），供 type_mappings 的 max_digits 判定。"""
    u = pic.upper()
    n = sum(int(x) for x in re.findall(r"9\((\d+)\)", u))
    return n + re.sub(r"9\(\d+\)", "", u).count("9")


def java_type_of(pic: str, comp: str = "") -> str:
    """查 type_mappings.yaml 首命中规则 → Java 标量类型（匹配文本 = "<PIC> <COMP>"）。"""
    text = f"{pic} {comp}".upper()
    digits = _count_digits(pic)
    for rule in _load("type_mappings.yaml").get("pic_rules", []):
        if not re.search(rule["pattern"], text):
            continue
        md = rule.get("max_digits")
        if md is not None and digits > md:
            continue
        return rule["java_type"]
    return "String"


def init_of(node) -> str:
    """按 spec 初值规则 → 初值表达式：有 VALUE 走 java_init，否则取 java_type 默认值。"""
    jt = node.java_type
    if node.has_value and node.value_raw:
        return java_init(node.value_raw, jt)
    return _DEFAULTS.get(jt, '""')


# ── 命名（复用 variable_resolver）──────────────────────────────────────────

def field_name(cobol: str) -> str:
    """COBOL 名 → Java 小驼峰字段名（WSAA-PROG → wsaaProg）。"""
    return _cobol_to_java_name(cobol)


def class_name(program: str) -> str:
    """程序/记录名 → Java 类名首段（ZPOLDWNM → Zpoldwnm）。"""
    return "".join(w.capitalize() for w in program.lower().replace("-", "_").split("_"))


# ── COPY 角色与类名 ─────────────────────────────────────────────────────────

def copy_role(name: str) -> str:
    """COPY 名 → 角色：service（处理逻辑）/ entity（记录定义）/ constant（其余）。"""
    nc = _load("naming_conventions.yaml")
    u = name.upper()
    if u in {s.upper() for s in nc.get("service_copybooks", [])}:
        return "service"
    for suf in nc.get("copybook_suffixes", []):
        if u.endswith(suf.upper()):
            return "entity"
    return "constant"


def entity_class(name: str) -> str:
    """实体 COPY → Java 类名：先查 copy_mappings；缺失则剥实体后缀 + 默认类后缀。"""
    recs = _load("copy_mappings.yaml").get("records", {})
    if name.upper() in recs:
        return recs[name.upper()]
    nc = _load("naming_conventions.yaml")
    base = name
    for suf in nc.get("copybook_suffixes", []):
        if base.upper().endswith(suf.upper()):
            base = base[: -len(suf)]
            break
    suffix = nc.get("struct_access", {}).get("default_class_suffix", "Params")
    return class_name(base) + suffix


def service_class(name: str) -> str:
    """服务 COPY → 服务类名（约定 PascalCase(名)+Service，见步骤05 §2-8）。"""
    return class_name(name) + "Service"


def service_field(name: str) -> str:
    """服务 COPY → 服务字段名（约定 camelCase(名)+Service）。"""
    return field_name(name) + "Service"
