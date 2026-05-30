"""
Java 骨架生成（确定性，不依赖 LLM）。

负责：程序级命名、按段号分模块、生成 State/模块/门面三类 Java 骨架。
从 graph.nodes 抽离，保证 graph → translator 单向依赖。
"""
from __future__ import annotations

import re

from translator import rules as _rules

PACKAGE = "com.example.cobol"

_VALUE_IMPORTS = [
    "import java.math.BigDecimal;",
    "import java.math.RoundingMode;",
    "import java.time.LocalTime;",
    "import java.time.format.DateTimeFormatter;",
    "import java.util.Arrays;",
    "import org.apache.commons.lang3.StringUtils;",
]


def _class_base(prog_id: str) -> str:
    """ZPOLDWNM → Zpoldwnm（不含 Service 后缀）。"""
    return "".join(w.capitalize() for w in prog_id.lower().replace("-", "_").split("_"))


def _module_class_name(base: str, prefix: str, part: int) -> str:
    if part <= 1:
        return f"{base}{prefix}Section"
    return f"{base}{prefix}SectionPart{part}"


def _facade_field(class_name: str) -> str:
    return class_name[0].lower() + class_name[1:]


def _assign_sections_to_modules(sections_meta: list[dict], base: str,
                                line_budget: int = 1800):
    """按段号千位前缀分桶 + 桶内贪心打包；返回 (module_assignment, modules)。"""
    # 1. 分桶
    buckets: dict[str, list[dict]] = {}
    order: list[str] = []
    for sec in sections_meta:
        m = re.match(r"^(\d+)", sec["name"])
        prefix = f"{int(m.group(1)) // 1000 * 1000}" if m else "Misc"
        if prefix not in buckets:
            buckets[prefix] = []
            order.append(prefix)
        buckets[prefix].append(sec)

    # 桶排序：数字升序，Misc 最后
    def _key(p: str):
        return (1, 0) if p == "Misc" else (0, int(p))
    order.sort(key=_key)

    module_assignment: dict[str, str] = {}
    modules: list[dict] = []
    for prefix in order:
        part = 1
        cur_sections: list[str] = []
        cur_lines = 0

        def _flush():
            nonlocal cur_sections, cur_lines, part
            if not cur_sections:
                return
            cls = _module_class_name(base, prefix, part)
            modules.append({"class_name": cls, "prefix": prefix, "sections": cur_sections[:]})
            for s in cur_sections:
                module_assignment[s] = cls
            part += 1
            cur_sections = []
            cur_lines = 0

        for sec in buckets[prefix]:
            est = len(sec.get("lines", [])) + 6
            if cur_sections and cur_lines + est > line_budget:
                _flush()
            cur_sections.append(sec["name"].upper())
            cur_lines += est
        _flush()
    return module_assignment, modules


def _calls_to_repos(calls, all_io: dict, io_cfg: dict):
    repos: dict[str, dict] = {}
    uses_date = False
    io_pattern = io_cfg.get("io_default_pattern", {})
    for c in calls:
        info = _rules.resolve_io_info(c, all_io, io_pattern)
        if info:
            repos[info["field_name"]] = info
        elif c in io_cfg.get("date_programs", {}):
            info = io_cfg["date_programs"][c]
            if "method" in info:
                uses_date = True
            else:
                repos[info["field_name"]] = info
    return repos, uses_date


def _build_state_class(base: str, prog_id: str, cobol_file: str, grouped_decls: str) -> str:
    imports = _VALUE_IMPORTS + ["import org.springframework.stereotype.Component;"]
    return f"""package {PACKAGE}.service;

{chr(10).join(imports)}

/**
 * COBOL 程序 {prog_id} 的全局状态（WORKING-STORAGE + LINKAGE）。
 * 单一共享实例：门面与各模块注入同一对象，保证变量身份唯一、跨段贯穿。
 * 原始文件: {cobol_file}
 */
@Component
public class {base}State {{

{grouped_decls}

}}
"""


def _build_module_skeleton(mod: dict, base: str, prog_id: str, meta_by_name: dict) -> str:
    class_name = mod["class_name"]
    repos: dict[str, dict] = mod.get("repos", {})
    uses_date = mod.get("uses_date", False)

    imports = list(_VALUE_IMPORTS) + [
        "import org.springframework.stereotype.Service;",
        "import org.springframework.beans.factory.annotation.Autowired;",
    ]
    for info in repos.values():
        imports.append(f"import {PACKAGE}.repository.{info['java_class']};")

    inject = [f"    private final {base}State st;",
              f"    private final {base}Service facade;"]
    params = [f"{base}State st", f"{base}Service facade"]
    assigns = ["        this.st = st;", "        this.facade = facade;"]
    if uses_date:
        inject.append("    private final DateConversionService dateConversionService;")
        params.append("DateConversionService dateConversionService")
        assigns.append("        this.dateConversionService = dateConversionService;")
    for field_name, info in repos.items():
        inject.append(f"    private final {info['java_class']} {field_name};")
        params.append(f"{info['java_class']} {field_name}")
        assigns.append(f"        this.{field_name} = {field_name};")

    method_stubs = []
    for sec_name in mod["sections"]:
        sec = meta_by_name[sec_name]
        mname = _section_to_method(sec["name"])
        comment = "    // TODO-GOTO: 含 GO TO 语句，需人工验证控制流\n" if sec.get("go_tos") else ""
        method_stubs.append(
            f"{comment}"
            f"    void {mname}() {{\n"
            f"        // COBOL SECTION: {sec['name']}"
            f"  (行 {sec['line_start']}-{sec['line_end']})\n"
            f"        // TODO: 等待 LLM 翻译\n"
            f"    }}"
        )

    return f"""package {PACKAGE}.service;

{chr(10).join(sorted(set(imports)))}

/**
 * COBOL 程序 {prog_id} 模块 [{mod['prefix']}] —— 段号桶 {mod['prefix']} 的 SECTION 方法。
 * 共享状态见 {base}State；跨模块调用经 facade.perform(...)。
 */
@Service
public class {class_name} {{

{chr(10).join(inject)}

    @Autowired
    public {class_name}({', '.join(params)}) {{
{chr(10).join(assigns)}
    }}

{chr(10).join(method_stubs)}

}}
"""


def _build_facade_skeleton(base, prog_id, cobol_file, modules, linkage_using,
                           module_assignment, entry_section) -> str:
    class_name = f"{base}Service"
    imports = [
        "import org.springframework.stereotype.Service;",
        "import org.springframework.beans.factory.annotation.Autowired;",
        "import org.springframework.transaction.annotation.Transactional;",
    ]
    inject = [f"    private final {base}State st;"]
    params = [f"{base}State st"]
    assigns = ["        this.st = st;"]
    for mod in modules:
        cls = mod["class_name"]
        fld = _facade_field(cls)
        inject.append(f"    private final {cls} {fld};")
        params.append(f"{cls} {fld}")
        assigns.append(f"        this.{fld} = {fld};")

    # perform 分发器
    cases = []
    for sec, cls in module_assignment.items():
        fld = _facade_field(cls)
        method = _section_to_method(sec)
        cases.append(f'            case "{sec}": {fld}.{method}(); return;')
    cases_str = "\n".join(cases)

    params_sig = ", ".join(
        f"Object {p.lower().replace('-', '_')}"
        for p in (linkage_using or ["params"])
    )
    entry_call = f'        perform("{entry_section}");' if entry_section else "        // TODO: 无入口段"

    return f"""package {PACKAGE}.service;

{chr(10).join(imports)}

/**
 * COBOL 程序 {prog_id} 门面：持有共享 State，注入各模块 bean，集中分发跨模块调用。
 * 原始文件: {cobol_file}
 */
@Service
@Transactional
public class {class_name} {{

{chr(10).join(inject)}

    @Autowired
    public {class_name}({', '.join(params)}) {{
{chr(10).join(assigns)}
    }}

    /**
     * 主入口：对应 COBOL PROCEDURE DIVISION USING {' '.join(linkage_using or [])}
     */
    public void execute({params_sig}) {{
        // TODO: 将入参写入 st，对应 LINKAGE SECTION
{entry_call}
    }}

    /** 跨模块 PERFORM 分发：按 SECTION 名转给拥有它的模块。 */
    public void perform(String section) {{
        switch (section) {{
{cases_str}
            default:
                throw new IllegalArgumentException("未知 SECTION: " + section);
        }}
    }}
}}
"""


def _section_to_method(section_name: str) -> str:
    """1000-INIT → init1000 / 8040A-ACMV-INF → acmvInf8040a / 0000-STARTUP → startup0000"""
    parts = section_name.lower().replace("-", "_").split("_")
    # 数字标号段：纯数字或"数字+字母后缀"（如 8040a、2090b），统一作为方法名后缀，
    # 避免出现以数字开头的非法 Java 标识符（如 8040A-... 旧实现会得到 8040aAcmvInf）。
    def _is_label(p: str) -> bool:
        return bool(re.match(r"^\d+[a-z]*$", p))

    num_parts = [p for p in parts if _is_label(p)]
    word_parts = [p for p in parts if not _is_label(p) and p not in ("exit", "section")]
    if word_parts and num_parts:
        name = word_parts[0] + "".join(w.capitalize() for w in word_parts[1:]) + num_parts[0]
    else:
        name = "".join(parts[0:1]) + "".join(p.capitalize() for p in parts[1:])
    # 兜底：Java 标识符不能以数字开头
    if name and name[0].isdigit():
        name = "sec" + name
    return name
