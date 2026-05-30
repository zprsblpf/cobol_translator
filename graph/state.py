from typing import TypedDict, Annotated
import operator


def _merge_dicts(a: dict, b: dict) -> dict:
    """并行节点累积字典（LangGraph reducer）。"""
    merged = dict(a)
    merged.update(b)
    return merged


class TranslationState(TypedDict):
    # ── 输入 ─────────────────────────────────────────────
    cobol_file: str                  # .cob 文件路径
    output_dir: str                  # 输出目录
    skeleton_only: bool              # 仅生成骨架（不调 LLM 填叶子）

    # ── 解析结果（JSON 序列化的 CobolProgram）─────────────
    program_id: str
    sections_meta: list[dict]        # [{name, line_start, line_end, calls, go_tos}]
    variable_context: str            # 变量名映射摘要（注入 LLM）
    io_context: str                  # IO 映射摘要（注入 LLM）
    java_field_declarations: str     # Java 字段声明代码块（旧版单类用，保留）
    java_field_declarations_grouped: str  # 按 01 组分块的字段声明（State 类用）
    java_field_names: list[str]      # 全部 Java 字段名（供 st. 前缀重写）
    field_type_map: dict             # {java_name: {type, is_array, array_size}}（固化规则判型）
    linkage_using: list[str]         # PROCEDURE DIVISION USING 参数
    copy_refs: list[str]             # COPY 引用名（驱动结构体命名范式）
    struct_registry: dict            # 拷贝簿结构体注册表（prefixes/objects/classes/...）
    io_mappings: dict                # IO 子程序映射（io_programs 合并/date_programs/system_programs），供 _t_call 固化

    # ── 大框架：多文件拆分 ───────────────────────────────
    module_assignment: dict          # {SECTION大写: 模块类名}
    modules: list[dict]              # 有序 [{class_name, prefix, sections, repos}]
    module_skeletons: dict           # {模块类名: 带 TODO 的模块骨架}
    state_class_source: str          # XxxState.java 完整源码
    facade_skeleton: str             # XxxService.java 门面骨架

    # ── 跨段分析（确定性，无 LLM）───────────────────────
    call_graph: dict                 # {SECTION: [被调 SECTION...]}
    entry_sequence: list             # 入口段及其顶层 PERFORM 序列
    var_lifecycle: dict              # {java_name: {written_in:[...], read_in:[...]}}

    # ── 生成的骨架（旧版单类，保留兼容）─────────────────
    java_skeleton: str               # 带 TODO 的 Java 类骨架

    # ── 并行翻译结果（section_name → java_method_body）─
    translated_sections: Annotated[dict, _merge_dicts]

    # ── 最终组装 ─────────────────────────────────────────
    final_java: str                  # 完整 Java 文件内容
    review_items: Annotated[list, operator.add]  # 高风险点清单
    validation_errors: list[str]

    # ── 状态 ────────────────────────────────────────────
    errors: list[str]
    status: str                      # parsing | building | translating | assembling | done | error
