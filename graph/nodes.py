"""
LangGraph 节点：COBOL → Java 翻译流水线。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:  # 大模型配置：url/key/模型名/温度等参数化（兼容不同运行方式）
    from cobol_translator.config.llm_config import (
        get_llm, get_llm_config, resolve_model, auth_headers,
    )
except ImportError:
    from config.llm_config import (
        get_llm, get_llm_config, resolve_model, auth_headers,
    )

from graph.state import TranslationState
from analyzer.dataflow import writers_context
from translator.segmenter import segment, split_paragraphs
from translator import rules as _rules
from translator.skeleton import _section_to_method
from translator.naming import build_struct_registry
from translator.postprocess import _postprocess_java_body
# 确定性翻译流水线（graph 节点仅做 state 适配，逻辑下沉到翻译侧）
from parser.pipeline import build_parse_result
from translator.context import build_context_and_skeleton
from translator.assemble import assemble_outputs
from config import spec_loader   # IO 映射访问层（步骤09：不再直读 io_mappings.yaml）
from log_utils import (
    get_flow_logger, log_llm_request, log_llm_response, log_llm_error,
)

log = get_flow_logger()

KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"


def _io_maps_from_spec() -> dict:
    """从访问层组装 io_maps 字典（单段调试路径就地用；与 context.py 形态一致）。"""
    return {
        "io_programs": spec_loader.io_programs(),
        "date_programs": spec_loader.date_programs(),
        "system_programs": spec_loader.system_programs(),
        "io_default_pattern": spec_loader.io_default_pattern(),
    }


# ── LLM（本地 vLLM，OpenAI 兼容）─────────────────────────────────────────────
_llm = None


def _get_llm():
    global _llm
    if _llm is None:
        _llm = get_llm()
        log.info("LLM 使用模型: %s（%s）", resolve_model(), get_llm_config()["base_url"])
    return _llm


# ── LLM 调用（DeepSeek-R1-Qwen3，vLLM 自动剥离 <think> 块）───────────────────

def _call_llm_no_think(system_prompt: str, user_prompt: str, scene: str = "") -> str:
    """
    调用本地 DeepSeek-R1-Qwen3 模型。
    vLLM 的 chat completions API 会自动剥离 <think>...</think>，
    message.content 只包含最终输出。关键：max_tokens 要足够大，
    让模型在思考完毕后仍有空间输出 Java 代码。

    入参（system/user prompt）与出参（response）走独立的 LLM 日志通道，
    便于与处理流程日志分开审查。`scene` 标注本次调用归属（如 SECTION 名）。
    """
    import requests as _req

    cfg = get_llm_config()
    model = _get_current_model()
    started = log_llm_request(scene, system_prompt, user_prompt, model)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "temperature": cfg["temperature"],
        "max_tokens": cfg["max_tokens"],
        "max_thinking_tokens": cfg["max_thinking_tokens"],
    }

    try:
        resp = _req.post(
            f"{cfg['base_url']}/chat/completions",
            json=payload,
            headers=auth_headers(cfg),
            timeout=cfg["timeout"],
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log_llm_error(scene, e, started)
        raise

    # 防御：若 vLLM 未剥离（旧版本），手动清除 thinking 块
    content = re.sub(r"<think>[\s\S]*?</think>", "", content)
    content = re.sub(r"<think>[\s\S]*", "", content)
    # 清理 markdown 代码块标记
    content = re.sub(r"```java\s*", "", content)
    content = re.sub(r"\s*```", "", content)
    content = content.strip()

    log_llm_response(scene, content, started)
    return content


def _get_current_model() -> str:
    """当前模型名：LLM_MODEL 配置优先，留空则从 {LLM_BASE_URL}/models 探测。"""
    return resolve_model()


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


# ── 节点 1：解析 COBOL（确定性逻辑在 parser.pipeline，此处仅 state 适配）──────────

def parse_cobol_node(state: TranslationState) -> dict:
    try:
        return build_parse_result(state["cobol_file"])
    except Exception as e:
        log.error("① 解析失败: %s", e)
        return {"errors": [f"解析失败: {e}"], "status": "error"}


# ── 节点 2：上下文+骨架（确定性逻辑在 translator.context，此处仅 state 适配）────────

def build_context_and_skeleton_node(state: TranslationState) -> dict:
    return build_context_and_skeleton(state)


# ── IO 调用模板生成器（确定性，但用途是注入 LLM prompt，故留在 graph 侧）──────────

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

    log.info("━━ ③ 翻译节点 ━━ SECTION [%s] (%d 行) → %s()",
             sec_name, len(sec_lines), method_name)

    field_type_map = state.get("field_type_map", {})
    module_assignment = state.get("module_assignment", {})
    sections_meta = state.get("sections_meta", [])
    known_sections = {s["name"].upper() for s in sections_meta}

    # 结构体（拷贝簿）命名范式：优先用上游 build_context 算好的注册表，缺失则就地构建。
    reg = state.get("struct_registry") or build_struct_registry(state)

    # IO 子程序映射：优先用上游算好的；单段调试路径（--section）缺失时就地加载。
    io_maps = state.get("io_mappings")
    if not io_maps:
        io_maps = _io_maps_from_spec()

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
        log.info("③ [%s] 第1遍骨架完成: %d 个 paragraph，%d 个待填叶子",
                 sec_name, len(paras), len(ctx.leaves))
    except Exception as e:
        # 切分/规则异常 → 整段退化为一个叶子交 LLM
        log.warning("③ [%s] 骨架构建异常，整段退化为 LLM 叶子: %s", sec_name, e)
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

    if skeleton_only:
        log.info("③ [%s] 第2遍叶子: 仅骨架模式，%d 条叶子保留原 COBOL 占位（不调 LLM）",
                 sec_name, len(leaf_fills))
    else:
        log.info("③ [%s] 第2遍叶子: 规则命中 %d 条，LLM 兜底 %d 条",
                 sec_name, len(leaf_fills), len(llm_pending))

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
    # IO 映射经访问层取（io_programs 已合并 io_programs2；_build_io_call_template 兼容该形态）
    io_cfg = {
        "io_programs": spec_loader.io_programs(),
        "date_programs": spec_loader.date_programs(),
        "io_default_pattern": spec_loader.io_default_pattern(),
    }

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

    log.info("③ [%s] 调用 LLM 兜底翻译 %d 条叶子（详见 LLM 通道日志）",
             sec_name, len(pending))
    try:
        resp = _call_llm_no_think(system_prompt, user_prompt, scene=f"SECTION {sec_name}")
    except Exception as e:
        log.error("③ [%s] LLM 兜底失败，%d 条叶子置 TODO: %s", sec_name, len(pending), e)
        return {lid: f"// TODO: 翻译失败({e}) 原COBOL: {raw}" for lid, raw in pending}

    fills: dict[int, str] = {}
    for m in re.finditer(r"\[(\d+)\]\s*(.*?)(?=\n\[\d+\]|\Z)", resp, re.DOTALL):
        fills[int(m.group(1))] = m.group(2).strip()
    # 缺失的编号兜底
    for lid, raw in pending:
        if lid not in fills:
            fills[lid] = f"// TODO: 人工翻译 原COBOL: {raw}"
    return fills


# ── 节点 4：组装输出（确定性逻辑在 translator.assemble，此处仅 state 适配）────────

def assemble_node(state: TranslationState) -> dict:
    return assemble_outputs(state)
