"""
LangGraph 节点：COBOL → Java 翻译流水线。
"""
from __future__ import annotations

import re
import sys
import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from graph.state import TranslationState
from parser.cobol_parser import parse as parse_cobol, CobolSection
from parser.variable_resolver import (
    resolve, generate_field_declarations, generate_variable_context,
    generate_grouped_field_declarations, build_field_type_map,
)
from analyzer.callgraph import build_call_graph
from analyzer.dataflow import analyze_dataflow, writers_context
from translator.segmenter import segment, split_paragraphs
from translator import rules as _rules

CONFIG_DIR = Path(__file__).parent.parent / "config"
KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"


def _load_yaml(name: str) -> dict:
    try:
        with open(CONFIG_DIR / name, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def build_struct_registry(state: dict) -> dict:
    """
    按命名范式（config/naming_conventions.yaml）从 COPY 引用派生结构体注册表。

      COPY <名><后缀>  →  结构体前缀 <名>，字段 <名>-XXX 渲染为 对象.getXxx()。
      Java 类名优先取 config/copy_mappings.yaml 的显式映射，否则按 <名>+默认后缀。

    拷贝簿源在盘上时其字段进 field_type_map 并优先命中，此注册表仅作兜底，
    两种情况输出一致。返回 dict 便于存入 state 复用。
    """
    naming = _load_yaml("naming_conventions.yaml")
    suffixes = [s.upper() for s in naming.get("copybook_suffixes", ["SKM", "REC", "KEY"])]
    sa = naming.get("struct_access", {}) or {}
    getter = sa.get("getter_prefix", "get")
    setter = sa.get("setter_prefix", "set")
    default_suffix = sa.get("default_class_suffix", "Params")

    records = {k.upper(): v for k, v in (_load_yaml("copy_mappings.yaml").get("records", {}) or {}).items()}

    prefixes: set[str] = set()
    classes: dict[str, str] = {}

    # 1) COPY <base><suffix> → 结构体前缀 base（最可靠来源）
    for cp in state.get("copy_refs", []):
        cpu = cp.upper()
        for suf in suffixes:
            if cpu.endswith(suf) and len(cpu) > len(suf):
                base = cpu[:-len(suf)]
                prefixes.add(base)
                classes[base] = records.get(cpu) or (_rules._pascal(base) + default_suffix)
                break

    # 2) 兜底：LINKAGE USING 的 <prefix>-PARAMS、各段内出现的 <prefix>-PARAMS
    for using in state.get("linkage_using", []):
        prefixes.add(using.upper().split("-")[0])
    for sec in state.get("sections_meta", []):
        for ln in sec.get("lines", []):
            for m in re.finditer(r"\b([A-Z0-9]+)-PARAMS\b", ln.upper()):
                prefixes.add(m.group(1))

    # 3) 对象名：有类名映射则首字母小写，否则按前缀+默认后缀
    objects: dict[str, str] = {}
    for p in prefixes:
        cls = classes.get(p)
        if cls:
            objects[p] = cls[0].lower() + cls[1:]
        else:
            objects[p] = _rules._java(p) + default_suffix
            classes[p] = _rules._pascal(p) + default_suffix

    return {
        "prefixes": prefixes, "objects": objects, "classes": classes,
        "getter": getter, "setter": setter, "default_suffix": default_suffix,
    }

# ── LLM（本地 vLLM，OpenAI 兼容）─────────────────────────────────────────────
_llm = None


def _get_llm():
    global _llm
    if _llm is None:
        from langchain_openai import ChatOpenAI
        import subprocess, json as _json
        try:
            resp = subprocess.run(
                ["curl", "-s", "http://localhost:8000/v1/models"],
                capture_output=True, text=True, timeout=5
            )
            models = _json.loads(resp.stdout).get("data", [])
            model_id = models[0]["id"] if models else "qwen3-8b-GPTQ"
        except Exception:
            model_id = "qwen3-8b-GPTQ"
        print(f"[LLM] 使用本地模型: {model_id}")
        _llm = ChatOpenAI(
            model=model_id,
            base_url="http://localhost:8000/v1",
            api_key="dummy",
            temperature=0,
            max_tokens=4096,
        )
    return _llm


# ── LLM 调用（DeepSeek-R1-Qwen3，vLLM 自动剥离 <think> 块）───────────────────

def _call_llm_no_think(system_prompt: str, user_prompt: str) -> str:
    """
    调用本地 DeepSeek-R1-Qwen3 模型。
    vLLM 的 chat completions API 会自动剥离 <think>...</think>，
    message.content 只包含最终输出。关键：max_tokens 要足够大，
    让模型在思考完毕后仍有空间输出 Java 代码。
    """
    import requests as _req

    payload = {
        "model": _get_current_model(),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "temperature": 0,
        "max_tokens": 4096,
        "max_thinking_tokens": 2048,
    }

    resp = _req.post(
        "http://localhost:8000/v1/chat/completions",
        json=payload,
        headers={"Authorization": "Bearer dummy"},
        timeout=120,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]

    # 防御：若 vLLM 未剥离（旧版本），手动清除 thinking 块
    content = re.sub(r"<think>[\s\S]*?</think>", "", content)
    content = re.sub(r"<think>[\s\S]*", "", content)
    # 清理 markdown 代码块标记
    content = re.sub(r"```java\s*", "", content)
    content = re.sub(r"\s*```", "", content)
    return content.strip()


def _get_current_model() -> str:
    """从 vLLM 获取当前加载的模型名。"""
    import requests as _req
    try:
        resp = _req.get("http://localhost:8000/v1/models", timeout=5)
        models = resp.json().get("data", [])
        return models[0]["id"] if models else "qwen3-8b-GPTQ"
    except Exception:
        return "qwen3-8b-GPTQ"


# ── RAG 向量库（复用 Spring Boot 生成器的基础设施）───────────────────────────
_vs = None


def _get_vs():
    global _vs
    if _vs is None:
        import os
        os.environ.setdefault("HF_HOME", "/data/models/huggingface")
        os.environ.setdefault("CHROMA_DIR", str(Path(__file__).parent.parent / "chroma_db"))
        os.environ.setdefault("EMBED_MODEL",
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
        # 复用 rag 目录的 vectorstore，但指向本项目的 knowledge/
        from langchain_community.document_loaders import DirectoryLoader, TextLoader
        from langchain_text_splitters import MarkdownTextSplitter
        from langchain_chroma import Chroma
        from langchain_huggingface import HuggingFaceEmbeddings

        chroma_dir = str(Path(__file__).parent.parent / "chroma_db")
        embed_model = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        embeddings = HuggingFaceEmbeddings(
            model_name=embed_model,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        chroma_path = Path(chroma_dir)
        if chroma_path.exists() and any(chroma_path.iterdir()):
            _vs = Chroma(persist_directory=chroma_dir, embedding_function=embeddings)
        else:
            loader = DirectoryLoader(
                str(KNOWLEDGE_DIR), glob="**/*.md",
                loader_cls=TextLoader, loader_kwargs={"encoding": "utf-8"},
            )
            docs = loader.load()
            splitter = MarkdownTextSplitter(chunk_size=1000, chunk_overlap=100)
            chunks = splitter.split_documents(docs)
            _vs = Chroma.from_documents(
                documents=chunks, embedding=embeddings, persist_directory=chroma_dir
            )
    return _vs


def _rag_retrieve(query: str, k: int = 4) -> str:
    """从知识库检索相关翻译规范，返回拼接文本。"""
    try:
        vs = _get_vs()
        docs = vs.similarity_search(query, k=k)
        return "\n\n---\n\n".join(d.page_content for d in docs)
    except Exception as e:
        return f"[RAG 不可用: {e}]"


# ── 节点 1：解析 COBOL 文件 ───────────────────────────────────────────────────

def parse_cobol_node(state: TranslationState) -> dict:
    print(f"\n[节点1] 解析 COBOL 文件: {state['cobol_file']}")
    try:
        prog = parse_cobol(state["cobol_file"])
        s = prog.summary()
        print(f"[节点1] {s}")

        # 变量解析
        all_vars = prog.working_storage + prog.linkage_vars
        fields = resolve(all_vars)
        var_ctx = generate_variable_context(fields, max_chars=6000)
        field_decls = generate_field_declarations(fields)
        grouped_decls = generate_grouped_field_declarations(all_vars, visibility="public")
        field_type_map = build_field_type_map(fields)
        field_names = [f.java_name for f in fields]

        # SECTION 元数据
        sections_meta = [
            {
                "name": sec.name,
                "lines": sec.lines,
                "line_start": sec.line_start,
                "line_end": sec.line_end,
                "performs": sec.performs,
                "calls": sec.calls,
                "go_tos": sec.go_tos,
            }
            for sec in prog.sections
        ]

        # 高风险点
        review_items = []
        for sec in prog.sections:
            if sec.go_tos:
                review_items.append(
                    f"⚠️ GO TO: SECTION [{sec.name}] 行{sec.line_start} 含 GO TO → {sec.go_tos}"
                )
        for var in prog.working_storage:
            if var.redefines:
                review_items.append(
                    f"⚠️ REDEFINES: {var.name} REDEFINES {var.redefines}"
                )

        print(f"[节点1] {len(sections_meta)} 个 SECTION，{len(fields)} 个字段，{len(review_items)} 个高风险点")
        return {
            "program_id": prog.program_id,
            "sections_meta": sections_meta,
            "variable_context": var_ctx,
            "java_field_declarations": field_decls,
            "java_field_declarations_grouped": grouped_decls,
            "field_type_map": field_type_map,
            "java_field_names": field_names,
            "linkage_using": prog.linkage_using,
            "copy_refs": prog.copy_refs,
            "review_items": review_items,
            "status": "building",
            "errors": [],
        }
    except Exception as e:
        return {"errors": [f"解析失败: {e}"], "status": "error"}


# ── 节点 2：构建 IO/COPY 上下文 + 生成 Java 骨架 ─────────────────────────────

def build_context_and_skeleton_node(state: TranslationState) -> dict:
    print(f"\n[节点2] 构建上下文 + 生成 Java 骨架...")

    with open(CONFIG_DIR / "io_mappings.yaml", encoding="utf-8") as f:
        io_cfg = yaml.safe_load(f)
    with open(CONFIG_DIR / "copy_mappings.yaml", encoding="utf-8") as f:
        copy_cfg = yaml.safe_load(f)

    # 收集本程序实际用到的所有 IO 调用
    all_calls: set[str] = set()
    for sec in state["sections_meta"]:
        all_calls.update(sec.get("calls", []))

    # 构建 IO 上下文摘要
    io_lines = ["## IO 调用映射（COBOL CALL → Java Repository）"]
    repositories: dict[str, dict] = {}
    date_services: list[str] = []

    # 合并所有 IO 程序条目（io_programs + io_programs2 兼容旧 YAML 缩进 bug）
    all_io = {**io_cfg.get("io_programs", {}), **io_cfg.get("io_programs2", {})}
    io_pattern = io_cfg.get("io_default_pattern", {})

    for call_name in sorted(all_calls):
        # 派生范式做基底，io_programs 显式条目按增量覆盖（非 *IO 返回显式条目/None）
        info = _rules.resolve_io_info(call_name, all_io, io_pattern)
        if info:
            io_lines.append(
                f"CALL '{call_name}' → {info['java_class']}.method()"
                f"  (字段: {info['field_name']})"
            )
            repositories[info["field_name"]] = info
        elif call_name in io_cfg.get("date_programs", {}):
            info = io_cfg["date_programs"][call_name]
            if "method" in info:
                io_lines.append(f"CALL '{call_name}' → dateConversionService.{info['method']}")
                if "DateConversionService" not in date_services:
                    date_services.append("DateConversionService")
            else:
                # date_programs 中意外混入的 IO 程序
                io_lines.append(f"CALL '{call_name}' → {info['java_class']}.method()")
                repositories[info["field_name"]] = info
        elif call_name in io_cfg.get("system_programs", {}):
            info = io_cfg["system_programs"][call_name]
            io_lines.append(f"CALL '{call_name}' → {info.get('java_code', 'TODO')}")

    io_context = "\n".join(io_lines)

    prog_id = state["program_id"]
    base = _class_base(prog_id)
    sections_meta = state["sections_meta"]

    # ── 跨段分析（确定性）──────────────────────────────────────────────
    cg = build_call_graph(sections_meta)
    df = analyze_dataflow(sections_meta, state.get("field_type_map", {}))

    # ── 大框架：分模块 ────────────────────────────────────────────────
    module_assignment, modules = _assign_sections_to_modules(sections_meta, base)
    meta_by_name = {s["name"].upper(): s for s in sections_meta}
    all_io = {**io_cfg.get("io_programs", {}), **io_cfg.get("io_programs2", {})}

    # 每模块所需 Repository
    for mod in modules:
        repos, uses_date = _calls_to_repos(
            (c for s in mod["sections"] for c in meta_by_name[s].get("calls", [])),
            all_io, io_cfg,
        )
        mod["repos"] = repos
        mod["uses_date"] = uses_date

    # ── 生成 State / 模块 / 门面 ──────────────────────────────────────
    state_src = _build_state_class(base, prog_id, state["cobol_file"],
                                   state.get("java_field_declarations_grouped", ""))
    module_skeletons = {
        mod["class_name"]: _build_module_skeleton(mod, base, prog_id, meta_by_name)
        for mod in modules
    }
    facade_src = _build_facade_skeleton(
        base, prog_id, state["cobol_file"], modules,
        state.get("linkage_using", []), module_assignment,
        cg.get("entry_section", ""),
    )

    review_items = list(df.get("review_items", []))
    for c in cg.get("cycles", []):
        review_items.append(f"⚠️ 调用环: {c}（需人工确认控制流）")

    print(f"[节点2] 骨架生成完成：{len(modules)} 个模块类 + State + 门面；"
          f"调用链最大深度 {cg.get('max_depth', 0)}")
    return {
        "io_context": io_context,
        "module_assignment": module_assignment,
        "modules": modules,
        "module_skeletons": module_skeletons,
        "state_class_source": state_src,
        "facade_skeleton": facade_src,
        "call_graph": cg,
        "entry_sequence": cg.get("entry_sequence", []),
        "var_lifecycle": df.get("var_lifecycle", {}),
        "review_items": review_items,
        # 结构体命名注册表：程序级算一次，各 SECTION 复用
        "struct_registry": build_struct_registry(state),
        # IO 子程序映射：程序级算一次，供各 SECTION 的 _t_call 固化复用
        "io_mappings": {
            "io_programs": all_io,
            "date_programs": io_cfg.get("date_programs", {}),
            "system_programs": io_cfg.get("system_programs", {}),
            "io_default_pattern": io_cfg.get("io_default_pattern", {}),
        },
        "status": "translating",
    }


# ── 大框架：命名 / 分模块 / 骨架构建 ───────────────────────────────────────────

PACKAGE = "com.example.cobol"


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


_VALUE_IMPORTS = [
    "import java.math.BigDecimal;",
    "import java.math.RoundingMode;",
    "import java.time.LocalTime;",
    "import java.time.format.DateTimeFormatter;",
    "import java.util.Arrays;",
    "import org.apache.commons.lang3.StringUtils;",
]


def _build_state_class(base: str, prog_id: str, cobol_file: str, grouped_decls: str) -> str:
    imports = _VALUE_IMPORTS + ["import org.springframework.stereotype.Component;"]
    return f"""package {PACKAGE};

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

    return f"""package {PACKAGE};

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

    return f"""package {PACKAGE};

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
    """1000-INIT → init1000 / 0000-STARTUP → startup0000"""
    parts = section_name.lower().replace("-", "_").split("_")
    # 找第一个数字段和文字段
    num_parts = [p for p in parts if p.isdigit()]
    word_parts = [p for p in parts if not p.isdigit() and p not in ("exit", "section")]
    if word_parts and num_parts:
        return word_parts[0] + "".join(w.capitalize() for w in word_parts[1:]) + num_parts[0]
    return "".join(parts[0:1]) + "".join(p.capitalize() for p in parts[1:])


# ── IO 调用模板生成器（确定性，不依赖 LLM）─────────────────────────────────────

def _build_io_call_template(call_name: str, io_cfg: dict) -> str:
    """为特定 IO 子程序生成 Java 调用示例代码（注入到 LLM prompt）。"""
    all_io = {**io_cfg.get("io_programs", {}), **io_cfg.get("io_programs2", {})}
    info = _rules.resolve_io_info(
        call_name, all_io, io_cfg.get("io_default_pattern", {}))
    if info:
        repo = info["field_name"]
        cls = info["java_class"]
        param = info["param_struct"].lower().replace("-", "")
        return f"""// CALL '{call_name}' 正确翻译方式：
// ① READR → 随机读取单条（等值主键）
{cls}Record {param}Record = {repo}.findByKey(key);
if ({param}Record != null) {{
    // 读取成功：访问字段 {param}Record.getXxx()
}} else {{
    // STATUZ = MRNF（记录未找到）
}}
// ② BEGN + NEXTR → 定位读 + 顺序读：是「等值查询 + 遍历结果集」。
//    BEGN 后用 `键字段 NOT = 入参 → 跳出` 的判断 = WHERE 键字段 = 入参（等值条件）；
//    键判断之后的非键字段判断 = 对结果集的过滤（continue）。
//    例：CHDRCOY/CHDRNUM 为键，CHGSTS 为过滤字段：
List<{cls}Record> rows = {repo}.findByChdrcoyAndChdrnum(chdrcoy, chdrnum);
for ({cls}Record {param} : rows) {{
    if (!"60".equals({param}.getChgsts())) {{ continue; }}  // 非键过滤 → NEXTR 跳过
    // 命中：处理逻辑
}}
// 注意：STATUZ NOT = O-K 表示遍历结束，对应 rows 耗尽（不要翻译成字符串比较）。"""
    elif call_name in io_cfg.get("date_programs", {}):
        info = io_cfg["date_programs"][call_name]
        param_var = call_name.lower() + "Params"
        return f"""// CALL '{call_name}' 正确翻译方式：
{call_name}Params {param_var} = new {call_name}Params();
{param_var}.setIntDate(wsaaIntDate);  // 设置输入参数
dateConversionService.{info['method'].replace('{params}', param_var)};
// 读取结果：{param_var}.getExtDate()"""
    elif call_name == "SYSERR":
        return "// CALL 'SYSERR' → throw new SystemException(wsaaErrMsg);"
    else:
        return f"// CALL '{call_name}' → TODO: 映射未定义，需人工补充"


_JAVA_METHOD_PREFIXES = (
    "set", "get", "is", "has", "find", "save", "delete", "create", "update",
    "add", "put", "remove", "build", "make", "init", "load", "fetch",
    "read", "write", "call", "invoke", "execute", "run", "start", "stop",
    "new", "throw", "return", "if", "for", "while", "switch", "assert",
)

def _is_java_method_call(name: str) -> bool:
    """判断标识符是否是 Java 方法名（不应转为数组下标）。"""
    if name[0].isupper():
        return True
    return any(name.startswith(pfx) for pfx in _JAVA_METHOD_PREFIXES)


def _postprocess_java_body(java_body: str, current_module: str = "",
                           module_assignment: dict | None = None,
                           java_field_names: list | None = None,
                           method_to_section: dict | None = None) -> str:
    """
    统一后处理（对规则与 LLM 输出均生效），固定三遍顺序：
    (0) 清理 LLM 杂质（签名/setLength/多余尾括号）
    (1) 数组下标 name(idx) → name[idx-1]
    (2) PERFORM 路由：this.m() 若目标段不属当前模块 → facade.perform("SEC")
    (3) st. 前缀：已知字段名前加 st.
    """
    module_assignment = module_assignment or {}
    java_field_names = java_field_names or []
    method_to_section = method_to_section or {}

    # 去掉外层方法签名（如果 LLM 加了）
    java_body = re.sub(r"^(private|public|protected)\s+\w+\s+\w+\([^)]*\)\s*\{", "", java_body).strip()
    # 修正 .setLength(0) → = ""
    java_body = re.sub(r"(\w+)\.setLength\(0\);", r'\1 = "";', java_body)

    # (1) 数组下标
    def _fix_subscript(m: re.Match) -> str:
        full, name, idx = m.group(0), m.group(1), m.group(2)
        start = m.start()
        if start > 0 and java_body[start - 1] == ".":
            return full
        if _is_java_method_call(name):
            return full
        return f"{name}[{idx} - 1]"

    java_body = re.sub(r"(\w+)\((\w+)\)", _fix_subscript, java_body)

    # 修正多余尾部 }
    java_body = java_body.rstrip()
    if java_body.endswith("}") and java_body.count("{") < java_body.count("}"):
        java_body = java_body[:-1].rstrip()

    # (2) PERFORM 跨模块路由
    if module_assignment and method_to_section:
        def _route(m: re.Match) -> str:
            method = m.group(1)
            sec = method_to_section.get(method)
            if not sec:
                return m.group(0)
            target_module = module_assignment.get(sec)
            if target_module and target_module != current_module:
                return f'facade.perform("{sec}");'
            return m.group(0)
        java_body = re.sub(r"\bthis\.(\w+)\(\)\s*;", _route, java_body)

    # (3) st. 前缀
    if java_field_names:
        names_sorted = sorted(set(java_field_names), key=len, reverse=True)
        alt = "|".join(re.escape(n) for n in names_sorted)
        field_re = re.compile(rf"(?<![.\w])({alt})\b")
        java_body = _prefix_fields_outside_strings(java_body, field_re)

    return java_body


def _prefix_fields_outside_strings(text: str, field_re: re.Pattern) -> str:
    """对字符串字面量之外的字段名加 st. 前缀。"""
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in ("'", '"'):
            q = c
            j = i + 1
            while j < n and text[j] != q:
                if text[j] == "\\":
                    j += 1
                j += 1
            out.append(text[i:min(j + 1, n)])
            i = j + 1
            continue
        # 找到下一个引号或结尾，处理这一段
        j = i
        while j < n and text[j] not in ("'", '"'):
            j += 1
        segment = text[i:j]
        out.append(field_re.sub(lambda m: "st." + m.group(1), segment))
        i = j
    return "".join(out)


# ── 节点 3：翻译单个 SECTION（LLM）───────────────────────────────────────────

def _build_method_to_section(sections_meta: list[dict]) -> dict:
    return {_section_to_method(s["name"]): s["name"].upper() for s in sections_meta}


def translate_section_node(state: TranslationState) -> dict:
    """
    动态节点：由 Send API 调用，state 中含 current_section。
    两遍：先用固化规则搭骨架（确定性），再填叶子（规则优先 + LLM 兜底）。
    """
    sec = state.get("current_section", {})
    if not sec:
        return {}

    sec_name = sec["name"]
    sec_lines = sec.get("lines", [])
    method_name = _section_to_method(sec_name)

    print(f"  [翻译] {sec_name} ({len(sec_lines)} 行)...")

    field_type_map = state.get("field_type_map", {})
    module_assignment = state.get("module_assignment", {})
    sections_meta = state.get("sections_meta", [])
    known_sections = {s["name"].upper() for s in sections_meta}

    # 结构体（拷贝簿）命名范式：优先用上游 build_context 算好的注册表，缺失则就地构建。
    reg = state.get("struct_registry") or build_struct_registry(state)

    # IO 子程序映射：优先用上游算好的；单段调试路径（--section）缺失时就地加载。
    io_maps = state.get("io_mappings")
    if not io_maps:
        _io_cfg = _load_yaml("io_mappings.yaml")
        io_maps = {
            "io_programs": {**_io_cfg.get("io_programs", {}), **_io_cfg.get("io_programs2", {})},
            "date_programs": _io_cfg.get("date_programs", {}),
            "system_programs": _io_cfg.get("system_programs", {}),
            "io_default_pattern": _io_cfg.get("io_default_pattern", {}),
        }

    # ── 第 1 遍：骨架（确定性）────────────────────────────────────────
    ctx = _rules.Ctx(
        field_type_map=field_type_map,
        section_to_method=_section_to_method,
        known_sections=known_sections,
        io_struct_prefixes=reg["prefixes"],
        struct_objects=reg["objects"],
        struct_classes=reg["classes"],
        struct_getter=reg["getter"],
        struct_setter=reg["setter"],
        struct_default_suffix=reg["default_suffix"],
        io_programs=io_maps["io_programs"],
        date_programs=io_maps["date_programs"],
        system_programs=io_maps["system_programs"],
        io_default_pattern=io_maps.get("io_default_pattern", {}),
    )
    try:
        # 先按 paragraph 切分，再交段内控制流分析（回跳 GO TO → 状态机循环）
        paras = [(lbl, segment(body_lines))
                 for lbl, body_lines in split_paragraphs(sec_lines)]
        skel_lines = _rules.build_section(paras, ctx)
        body = "\n".join(skel_lines)
    except Exception as e:
        # 切分/规则异常 → 整段退化为一个叶子交 LLM
        body = "/*__LEAF_0__*/"
        ctx.leaves = [(0, _rules.Stmt(kind="simple", raw="\n".join(sec_lines)))]

    skeleton_only = bool(state.get("skeleton_only"))

    # ── 第 2 遍：填叶子（规则优先，LLM 兜底）──────────────────────────
    leaf_fills: dict[int, str] = {}
    llm_pending: list[tuple[int, str]] = []
    for lid, leaf in ctx.leaves:
        if skeleton_only:
            raw = (leaf.raw or " ".join(leaf.tokens)).strip()
            leaf_fills[lid] = f"// 原COBOL: {raw}"
            continue
        java_lines, matched = _rules.translate_leaf(leaf, ctx)
        if matched:
            leaf_fills[lid] = "\n".join(java_lines)
        else:
            raw = (leaf.raw or " ".join(leaf.tokens)).strip()
            llm_pending.append((lid, raw))

    if llm_pending:
        fills = _translate_leaves_llm(sec, llm_pending, state)
        leaf_fills.update(fills)

    # 回填占位
    for lid, fill in leaf_fills.items():
        body = body.replace(f"/*__LEAF_{lid}__*/", fill)
    # 未回填的占位（防御）
    body = re.sub(r"/\*__LEAF_\d+__\*/", "// TODO: 未翻译叶子", body)

    body = _postprocess_java_body(
        body,
        current_module=module_assignment.get(sec_name.upper(), ""),
        module_assignment=module_assignment,
        java_field_names=state.get("java_field_names", []),
        method_to_section=_build_method_to_section(sections_meta),
    )
    return {"translated_sections": {method_name: body}}


def _translate_leaves_llm(sec: dict, pending: list[tuple[int, str]],
                          state: TranslationState) -> dict[int, str]:
    """对未被规则命中的叶子做一次 LLM 调用，按编号回填。"""
    sec_name = sec["name"]
    try:
        with open(CONFIG_DIR / "io_mappings.yaml", encoding="utf-8") as f:
            io_cfg = yaml.safe_load(f)
    except Exception:
        io_cfg = {}

    calls = sec.get("calls", [])
    io_templates = [_build_io_call_template(c, io_cfg) for c in calls]
    io_template_str = "\n\n".join(io_templates) if io_templates else "（本 SECTION 无 IO 调用）"

    # 跨段数据流上下文
    flow_ctx = writers_context(
        sec_name, state.get("sections_meta", []),
        state.get("field_type_map", {}), state.get("var_lifecycle", {}),
    )

    numbered = "\n".join(f"[{lid}] {raw}" for lid, raw in pending)

    # 从知识库检索相关翻译规范（IO 模式 / BEGN 等值语义 / 状态码 等），注入 prompt
    rag_query = " ".join(calls + [raw for _lid, raw in pending[:8]])
    kb = _rag_retrieve(rag_query, k=4)
    kb_block = ""
    if kb and not kb.startswith("[RAG 不可用"):
        kb_block = f"## 翻译规范（知识库，务必遵循）\n{kb}\n"

    system_prompt = """你是 COBOL → Java 翻译专家。只翻译给定的叶子语句片段。

【输出格式】严格逐条输出，每条形如：
[编号] <Java 语句>
不要输出方法签名、花括号、解释文字。一个编号一行 Java（可多语句用分号分隔）。

【MOVE】MOVE A TO B → b = a;；MOVE SPACES TO X → x = "";；MOVE ZEROES TO X → x = 0; 或 BigDecimal.ZERO;
【数组】COBOL 下标从1开始：wsaaName(ix) → wsaaName[ix - 1]
【IO 调用】严格用下方 IO 模板，不要自创方法。
字段名用驼峰裸名（系统会自动加 st. 前缀）。"""

    user_prompt = f"""SECTION [{sec_name}] 的待翻译叶子语句（按编号翻译）：

{kb_block}
## IO 调用模板
{io_template_str}

## 变量名映射
{state.get('variable_context', '')}

{flow_ctx}

## 待翻译片段
{numbered}

输出：逐条 [编号] Java 语句"""

    try:
        resp = _call_llm_no_think(system_prompt, user_prompt)
    except Exception as e:
        return {lid: f"// TODO: 翻译失败({e}) 原COBOL: {raw}" for lid, raw in pending}

    fills: dict[int, str] = {}
    for m in re.finditer(r"\[(\d+)\]\s*(.*?)(?=\n\[\d+\]|\Z)", resp, re.DOTALL):
        fills[int(m.group(1))] = m.group(2).strip()
    # 缺失的编号兜底
    for lid, raw in pending:
        if lid not in fills:
            fills[lid] = f"// TODO: 人工翻译 原COBOL: {raw}"
    return fills


# ── 节点 4：组装最终 Java 文件 ────────────────────────────────────────────────

def _fill_stubs(skeleton: str, sections: list[str], translated: dict,
                meta_by_name: dict) -> tuple[str, int]:
    """把模块骨架中各 SECTION 的 TODO 占位替换为翻译后的方法体。"""
    filled = skeleton
    count = 0
    for sec_name in sections:
        sec = meta_by_name[sec_name]
        method_name = _section_to_method(sec["name"])
        body = translated.get(method_name, "")
        if not body:
            continue
        old_body = (
            f"        // COBOL SECTION: {sec['name']}"
            f"  (行 {sec['line_start']}-{sec['line_end']})\n"
            f"        // TODO: 等待 LLM 翻译"
        )
        indented = "\n".join("        " + line for line in body.split("\n"))
        new_body = (
            f"        // COBOL SECTION: {sec['name']}"
            f"  (行 {sec['line_start']}-{sec['line_end']})\n"
            f"{indented}"
        )
        if old_body in filled:
            filled = filled.replace(old_body, new_body, 1)
            count += 1
    return filled, count


def assemble_node(state: TranslationState) -> dict:
    print(f"\n[节点4] 组装多文件 Java 输出...")
    import os

    translated = state.get("translated_sections", {})
    sections_meta = state["sections_meta"]
    meta_by_name = {s["name"].upper(): s for s in sections_meta}
    prog_id = state["program_id"]
    base = _class_base(prog_id)
    output_dir = state.get("output_dir", "./output")
    os.makedirs(output_dir, exist_ok=True)

    written: list[tuple[str, int]] = []   # (filename, line_count)
    size_warnings: list[str] = []

    def _write(filename: str, content: str):
        path = os.path.join(output_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        n = content.count("\n") + 1
        written.append((filename, n))
        if n >= 2000:
            size_warnings.append(f"⚠️ {filename} 达 {n} 行（≥2000），建议进一步拆分")

    # State + 门面
    _write(f"{base}State.java", state.get("state_class_source", ""))
    _write(f"{base}Service.java", state.get("facade_skeleton", ""))

    # 各模块
    total_replaced = 0
    module_summary: list[str] = []
    for mod in state.get("modules", []):
        skel = state.get("module_skeletons", {}).get(mod["class_name"], "")
        filled, cnt = _fill_stubs(skel, mod["sections"], translated, meta_by_name)
        total_replaced += cnt
        _write(f"{mod['class_name']}.java", filled)
        secs_desc = ", ".join(
            f"{s}(行{meta_by_name[s]['line_start']}-{meta_by_name[s]['line_end']})"
            for s in mod["sections"]
        )
        module_summary.append(
            f"- **{mod['class_name']}.java**（桶 {mod['prefix']}，{len(mod['sections'])} 段）: {secs_desc}"
        )

    print(f"[节点4] 写出 {len(written)} 个文件；填充 {total_replaced}/{len(sections_meta)} 个方法")

    # 调用链产物
    cg = state.get("call_graph", {})
    if cg.get("markdown"):
        with open(os.path.join(output_dir, "call_graph.md"), "w", encoding="utf-8") as f:
            f.write(cg["markdown"])

    # 审查清单
    review_items = list(state.get("review_items", [])) + size_warnings
    review_path = os.path.join(output_dir, "review_checklist.md")
    with open(review_path, "w", encoding="utf-8") as f:
        f.write(f"# {prog_id} 翻译审查清单\n\n")
        f.write("## 高风险点（需人工验证）\n\n")
        for item in review_items:
            f.write(f"- {item}\n")
        f.write("\n## 模块拆分汇总\n\n")
        f.write(f"- {base}State.java（共享全局状态）\n")
        f.write(f"- {base}Service.java（门面 + perform 分发，入口段 {cg.get('entry_section', '?')}）\n")
        for line in module_summary:
            f.write(line + "\n")
        f.write("\n## 文件行数\n\n")
        for fn, n in written:
            f.write(f"- {fn}: {n} 行\n")
        f.write("\n## 翻译统计\n")
        f.write(f"- 总 SECTION 数: {len(sections_meta)}\n")
        f.write(f"- 已填充方法: {total_replaced}\n")
        f.write(f"- 调用链最大深度: {cg.get('max_depth', 0)}\n")

    print(f"[节点4] 输出目录: {output_dir}；审查清单: {review_path}")
    return {"final_java": state.get("facade_skeleton", ""), "status": "done"}
