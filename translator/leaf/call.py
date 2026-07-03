"""
相3 叶子翻译公用底座 —— CALL 散点兜底翻译 + IO 映射解析（rules 与 asg.visitor 共用）。

对应设计：docs/详细设计/步骤21-绞杀项3④CALL迁visitor设计.md §3。
设计思路：散点 CALL 的兜底翻译（translate_call）与其私有依赖 IO 映射解析（resolve_io_info /
derive_io_info）下沉为公用底座——rules 委托（别名 _t_call + 再导入 resolve/derive_io_info 保公开面）、
相3 visit_CallStmt 共调同一份 → 两路产物逐字符一致（绞杀项3 比对闸基础）。
范围：仅散点 CALL 兜底一层（_t_call）；setup+CALL+IF 结构吸收（②）与 struct_rebind（③）留后续刀。
复用 leaf.expr 的 _struct_obj；ctx 读 io_programs/io_default_pattern/date_programs/system_programs/
struct_function（均在 LeafCtx 契约，见 context.py）。
"""
from __future__ import annotations

import re

from translator.leaf.context import LeafCtx
from translator.leaf.expr import _struct_obj


def derive_io_info(name: str, pattern: dict | None) -> dict | None:
    """按 io_mappings.yaml 的 `io_default_pattern` 范式为 CALL 'xxxIO' 兜底派生 Repository 映射。

    所有映射关系（类/字段后缀、包名、参数结构体后缀、操作码→方法）都来自配置表 pattern，
    py 只负责套用命名范式（base → PascalCase/camelCase），不写死任何业务映射。
    例（pattern 后缀=Repository、包=com.example.repository）：
      SCF4CHRIO → Scf4chrRepository / scf4chrRepository / SCF4CHR-PARAMS。
    仅对 *IO 结尾的子程序生效；pattern 缺失或非 *IO → 返回 None（不派生）。
    """
    if not pattern:
        return None
    if not name or not name.upper().endswith("IO") or len(name) <= 2:
        return None
    base = name[:-2].upper()              # SCF4CHR
    cls_base = base.lower().capitalize()  # Scf4chr（PascalCase）
    field = cls_base[0].lower() + cls_base[1:]  # scf4chr（camelCase）
    cls = f"{cls_base}{pattern.get('class_suffix', '')}"
    return {
        "java_class": cls,
        "field_name": f"{field}{pattern.get('field_suffix', '')}",
        "param_struct": f"{base}{pattern.get('param_struct_suffix', '')}",
        "import": f"{pattern.get('import_package', '').rstrip('.')}.{cls}",
        "operations": dict(pattern.get("operations", {})),
        "_derived": True,
    }


def resolve_io_info(name: str, io_programs: dict, pattern: dict | None) -> dict | None:
    """统一解析 CALL 'xxxIO' 的映射：派生范式做基底，io_programs 显式条目按字段/操作码深合并覆盖。

    这样 io_mappings.yaml 的 io_programs 只需登记「非标准的增量」（如某表 READR 用
    findByPolicyNo），java_class/field_name/param_struct/import 与标准操作码全部由
    io_default_pattern 自动派生，无需逐表重复抄写。
    非 *IO 子程序（无法派生）→ 直接返回显式条目或 None。
    """
    base = derive_io_info(name, pattern)
    entry = io_programs.get(name)
    if not base:
        return entry            # 非 *IO：只认显式登记
    if not entry:
        return base             # 纯标准 *IO：全靠范式
    merged = {**base, **entry}  # 顶层字段：显式覆盖派生
    ops = dict(base.get("operations", {}))
    ops.update(entry.get("operations", {}))   # 操作码：逐码覆盖，未覆盖的保留标准派生
    merged["operations"] = ops
    return merged


def translate_call(toks: list[str], ctx: LeafCtx) -> tuple[list[str], bool]:
    """
    CALL 'xxxIO' USING xxx-PARAMS → 固化 Repository 调用（叶子级退路）。

    单条「读」(READR/READS) 的标准形态 setup+CALL+IF 由 _rewrite_begn_loops 的结构化吸收
    （_match_readr_single / _render_readr_single）整段改写为 `Rec r = repo.findBy…Readr(键)`，
    不会走到这里。本函数只兜底未被结构吸收的散点 CALL：
      · 功能码由前一句 MOVE … TO xxx-FUNCTION 设，记在 ctx.struct_function。
      · 功能码在 io_default_pattern.operations 有对应方法（如 UPDAT/WRITE→save）
        → 直出 obj = repo.method(obj);
      · 否则（含游标 BEGN/NEXTR、功能码不在 operations）→ matched=False，交 LLM 兜底。
        决策 D（步骤10）：功能码恒为 CALL 前显性字面量、静态恒可得，原 execute() 运行时分发
        是为不存在场景写的死代码，已移除。
      · 未映射的子程序 → matched=False，交 LLM 兜底。
    """
    if len(toks) < 2:
        return [], False
    name = toks[1].strip("'\"").upper()

    # 取 USING 后第一个实参作为参数结构体
    u = [t.upper() for t in toks]
    arg = None
    if "USING" in u:
        ui = u.index("USING")
        if ui + 1 < len(toks):
            arg = toks[ui + 1]

    # 表里有用表里的；没有但符合 *IO 查表范式 → 按命名规范兜底派生（固定化翻译）
    info = resolve_io_info(name, ctx.io_programs, ctx.io_default_pattern)
    if info:
        repo = info["field_name"]
        ops = info.get("operations", {})
        prefix = (arg.split("-", 1)[0].upper() if arg and "-" in arg
                  else info.get("param_struct", "").split("-", 1)[0].upper())
        obj = _struct_obj(prefix, ctx) if prefix else "params"
        func = ctx.struct_function.get(prefix)
        if func and func in ops:
            method = re.sub(r"\{[^}]*\}", obj, ops[func])
            return [f"{obj} = {repo}.{method};"], True
        # 无功能码或功能码不在 operations 时，用 READR 兜底（结构吸收未命中的散点 CALL）
        if "READR" in ops:
            method = re.sub(r"\{[^}]*\}", obj, ops["READR"])
            return [f"{obj} = {repo}.{method};  // default READR"], True
        return [], False    # 功能码不在 operations（游标/未知）→ 交 LLM（决策 D：移除 execute 死代码退路）

    # 日期子程序：dateConversionService.convertDateN(params)
    dinfo = ctx.date_programs.get(name)
    if dinfo and dinfo.get("method") and dinfo.get("field_name"):
        prefix = (arg.split("-", 1)[0].upper() if arg and "-" in arg else name)
        obj = _struct_obj(prefix, ctx)
        method = re.sub(r"\{[^}]*\}", obj, dinfo["method"])
        return [f"{dinfo['field_name']}.{method};"], True

    # 系统子程序（SYSERR 等）：直出 java_code，否则 service.method
    sinfo = ctx.system_programs.get(name)
    if sinfo:
        if sinfo.get("java_code"):
            code = sinfo["java_code"].strip()
            return [code if code.endswith(";") else code + ";"], True
        if sinfo.get("method") and sinfo.get("field_name"):
            prefix = (arg.split("-", 1)[0].upper() if arg and "-" in arg else name)
            obj = _struct_obj(prefix, ctx)
            method = re.sub(r"\{[^}]*\}", obj, sinfo["method"])
            return [f"{sinfo['field_name']}.{method};"], True

    return [], False    # 未映射 → LLM 兜底
