"""
ASG 结构吸收改写 pass（步骤25）。

用途：把旧 rules._rewrite_begn_loops Pass 1 的 BEGN+NEXTR 自跳循环识别迁到 ASG 侧，
产出显式 BegnForeachStmt 节点，不在 rewrite 阶段生成 Java。
对应设计：docs/详细设计/步骤25-BEGN-NEXTR结构吸收迁visitor设计.md。
"""
from __future__ import annotations

from dataclasses import replace

from asg import nodes


def rewrite_structures(paragraphs: list[nodes.Paragraph], ctx) -> list[nodes.Paragraph]:
    """结构吸收统一入口。顺序对齐旧 _rewrite_begn_loops：foreach 先于单次 BEGN。"""
    paragraphs = rewrite_begn_foreach(paragraphs, ctx)
    paragraphs = rewrite_begn_single(paragraphs, ctx)
    paragraphs = rewrite_readr_single(paragraphs, ctx)
    paragraphs = rewrite_write_single(paragraphs, ctx)
    return paragraphs


def rewrite_begn_foreach(paragraphs: list[nodes.Paragraph], ctx) -> list[nodes.Paragraph]:
    """识别 BEGN+NEXTR 自跳循环并改写为 BegnForeachStmt。

    复刻 rules._rewrite_begn_loops Pass 1：loop paragraph 命中后替换为结构节点，并剥除
    前序 paragraph 中同 pfx 的 setup 赋值。未命中返回原列表。
    """
    norm: list[tuple[str, nodes.Paragraph]] = [
        (p.label or f"__ENTRY_{i}", p) for i, p in enumerate(paragraphs)
    ]
    labels = [label for label, _p in norm]
    result = list(paragraphs)
    changed = False

    for i, (label, para) in enumerate(norm):
        info = _match_begn_loop(label, para.stmts, ctx)
        if not info:
            continue
        next_label = labels[i + 1] if i + 1 < len(labels) else None
        if info["exit_label"] != next_label:
            continue
        if not any(_setup_has_begn(prev.stmts, info["pfx"]) for _pl, prev in norm[:i]):
            continue

        stmt = nodes.BegnForeachStmt(
            pfx=info["pfx"],
            name=info["name"],
            keys=info["keys"],
            filters=info["filters"],
            body=info["body"],
            raw=para.label or label,
            lineno=para.lineno,
        )
        result[i] = replace(para, stmts=[stmt])
        for k in range(i):
            result[k] = replace(result[k], stmts=_strip_struct_setup_nodes(result[k].stmts, info["pfx"]))
        changed = True

    return result if changed else paragraphs


def rewrite_begn_single(paragraphs: list[nodes.Paragraph], ctx) -> list[nodes.Paragraph]:
    """识别单次 BEGN 等值定位并改写为 BegnSingleStmt。"""
    result = list(paragraphs)
    changed = False
    for i, para in enumerate(paragraphs):
        if para.stmts and isinstance(para.stmts[0], nodes.BegnForeachStmt):
            continue
        info = _match_begn_single_nodes(para.stmts, ctx)
        if not info:
            continue
        stmt = nodes.BegnSingleStmt(
            pfx=info["pfx"],
            name=info["name"],
            keys=info["keys"],
            then_body=info["then_body"],
            raw=para.label or "",
            lineno=para.lineno,
        )
        before = para.stmts[:info["setup_start"]]
        after = para.stmts[info["call_idx"] + 2:]
        result[i] = replace(para, stmts=before + [stmt] + after)
        changed = True
    return result if changed else paragraphs


def rewrite_readr_single(paragraphs: list[nodes.Paragraph], ctx) -> list[nodes.Paragraph]:
    """识别 READR/READS 单条读并改写为 IoReadSingleStmt。"""
    result = list(paragraphs)
    changed = False
    for i, para in enumerate(paragraphs):
        if para.stmts and isinstance(para.stmts[0], (nodes.BegnForeachStmt, nodes.BegnSingleStmt)):
            continue
        info = _match_readr_single_nodes(para.stmts, ctx)
        if not info:
            continue
        stmt = nodes.IoReadSingleStmt(
            pfx=info["pfx"],
            name=info["name"],
            func=info["func"],
            keys=info["keys"],
            mode=info["mode"],
            then_body=info["then_body"],
            else_body=info["else_body"],
            try_tail=info["try_tail"],
            raw=para.label or "",
            lineno=para.lineno,
        )
        before = para.stmts[:info["setup_start"]]
        after = para.stmts[info["consume_to"]:]
        result[i] = replace(para, stmts=before + [stmt] + after)
        changed = True
    return result if changed else paragraphs


def rewrite_write_single(paragraphs: list[nodes.Paragraph], ctx) -> list[nodes.Paragraph]:
    """Recognize UPDAT/WRITR/DELET single write IO as IoWriteSingleStmt."""
    result = list(paragraphs)
    changed = False
    for i, para in enumerate(paragraphs):
        if para.stmts and isinstance(para.stmts[0], (nodes.BegnForeachStmt, nodes.BegnSingleStmt, nodes.IoReadSingleStmt)):
            continue
        info = _match_write_single_nodes(para.stmts, ctx)
        if not info:
            continue
        stmt = nodes.IoWriteSingleStmt(
            pfx=info["pfx"],
            name=info["name"],
            func=info["func"],
            is_new=info["is_new"],
            is_delete=info["is_delete"],
            setters=info["setters"],
            mode=info["mode"],
            then_body=info["then_body"],
            try_tail=info["try_tail"],
            raw=para.label or "",
            lineno=para.lineno,
        )
        before = para.stmts[:info["setup_start"]]
        after = para.stmts[info["consume_to"]:]
        result[i] = replace(para, stmts=before + [stmt] + after)
        changed = True
    return result if changed else paragraphs


def tag_rebind_nodes(stmts: list, rebind: dict) -> None:
    """给节点及其嵌套子节点打 struct_rebind 标记，供 visitor 调 leaf 译器前临时改 ctx。"""
    for st in stmts:
        setattr(st, "struct_rebind", rebind)
        if isinstance(st, nodes.IfStmt):
            tag_rebind_nodes(st.then, rebind)
            tag_rebind_nodes(st.els, rebind)
        elif isinstance(st, nodes.EvaluateStmt):
            for _cond, body in st.whens:
                tag_rebind_nodes(body, rebind)
        elif isinstance(st, nodes.PerformStmt):
            tag_rebind_nodes(st.inline_body, rebind)
        elif isinstance(st, nodes.BegnForeachStmt):
            tag_rebind_nodes(st.filters, rebind)
            tag_rebind_nodes(st.body, rebind)
        elif isinstance(st, nodes.BegnSingleStmt):
            tag_rebind_nodes(st.then_body, rebind)
        elif isinstance(st, nodes.IoReadSingleStmt):
            tag_rebind_nodes(st.then_body, rebind)
            tag_rebind_nodes(st.else_body, rebind)
            tag_rebind_nodes(st.try_tail, rebind)
        elif isinstance(st, nodes.IoWriteSingleStmt):
            tag_rebind_nodes(st.setters, rebind)
            tag_rebind_nodes(st.then_body, rebind)
            tag_rebind_nodes(st.try_tail, rebind)


def _stmt_call_io(st, ctx):
    if not isinstance(st, nodes.CallStmt) or not st.tokens or len(st.tokens) < 2:
        return None
    name = (st.name or st.tokens[1].strip("'\"")).upper()
    toks = [t.upper() for t in st.tokens]
    if "USING" not in toks:
        return None
    idx = toks.index("USING")
    arg = st.tokens[idx + 1] if idx + 1 < len(st.tokens) else ""
    if not name.endswith("IO") or "-" not in arg:
        return None
    return name, arg.split("-", 1)[0].upper()


def _goto_target(st):
    if isinstance(st, nodes.GotoStmt):
        if st.target:
            return st.target.name
        for tok in st.tokens:
            if tok.upper() not in ("GO", "TO"):
                return tok.upper()
    return None


def _is_move_nextr(st, pfx: str) -> bool:
    if not isinstance(st, nodes.MoveStmt):
        return False
    toks = [t.upper() for t in st.tokens]
    return toks[:1] == ["MOVE"] and "NEXTR" in toks and f"{pfx}-FUNCTION" in toks


def _setup_has_begn(stmts: list, pfx: str) -> bool:
    for st in stmts:
        if isinstance(st, nodes.MoveStmt):
            toks = [t.upper() for t in st.tokens]
            if toks[:1] == ["MOVE"] and "BEGN" in toks and f"{pfx}-FUNCTION" in toks:
                return True
    return False


def _then_single_goto(st):
    if isinstance(st, nodes.IfStmt) and not st.els and len(st.then) == 1:
        return _goto_target(st.then[0])
    return None


def _is_filter_if(st, pfx: str, loop_label: str) -> bool:
    if not isinstance(st, nodes.IfStmt) or st.els or len(st.then) != 2:
        return False
    return _is_move_nextr(st.then[0], pfx) and _goto_target(st.then[1]) == loop_label


def _contains_goto(st) -> bool:
    if _goto_target(st):
        return True
    if isinstance(st, nodes.IfStmt):
        return any(_contains_goto(c) for c in st.then + st.els)
    if isinstance(st, nodes.EvaluateStmt):
        return any(_contains_goto(c) for _cond, body in st.whens for c in body)
    if isinstance(st, nodes.PerformStmt):
        return any(_contains_goto(c) for c in st.inline_body)
    if isinstance(st, nodes.BegnForeachStmt):
        return any(_contains_goto(c) for c in st.filters + st.body)
    return False


def _split_or(tokens: list[str]) -> list[list[str]]:
    out, cur = [], []
    for tok in tokens:
        if tok.upper() == "OR":
            out.append(cur)
            cur = []
        else:
            cur.append(tok)
    out.append(cur)
    return out


def _begn_breakout_keys(cond_tokens: list[str], pfx: str):
    keys: list[tuple[str, str]] = []
    for term in _split_or(cond_tokens):
        tu = [t.upper() for t in term]
        if "AND" in tu or "NOT" not in tu or "=" not in tu:
            return None
        ni = tu.index("NOT")
        left = term[:ni]
        eqi = tu.index("=", ni)
        right = term[eqi + 1:]
        if len(left) != 1 or len(right) != 1:
            return None
        lf = left[0].upper()
        if "-" not in lf or lf.split("-", 1)[0] != pfx:
            return None
        key = lf.split("-", 1)[1]
        if key == "STATUZ":
            continue
        keys.append((key, right[0]))
    return keys or None


def _match_begn_loop(loop_label: str, stmts: list, ctx):
    if not stmts:
        return None
    call_info = _stmt_call_io(stmts[0], ctx)
    if not call_info:
        return None
    name, pfx = call_info
    keys = exit_label = None
    filters: list = []
    body: list = []
    for st in stmts[1:]:
        target = _then_single_goto(st)
        if target and keys is None and target != loop_label:
            parsed = _begn_breakout_keys(st.cond, pfx)
            if parsed is None:
                return None
            keys, exit_label = parsed, target
            continue
        if _is_filter_if(st, pfx, loop_label):
            filters.append(st)
            continue
        if _is_move_nextr(st, pfx) or _goto_target(st) == loop_label:
            continue
        if _contains_goto(st):
            return None
        body.append(st)
    if keys is None or exit_label is None:
        return None
    return {"pfx": pfx, "name": name, "keys": keys, "exit_label": exit_label,
            "filters": filters, "body": body}


def _match_begn_single_nodes(stmts: list, ctx):
    if not stmts:
        return None
    call_idx = None
    call_info = None
    for i, st in enumerate(stmts):
        ci = _stmt_call_io(st, ctx)
        if not ci:
            continue
        name, pfx = ci
        if _setup_has_begn(stmts[:i], pfx):
            call_idx = i
            call_info = ci
            break
    if call_idx is None:
        return None

    name, pfx = call_info
    if call_idx + 1 >= len(stmts):
        return None
    if_stmt = stmts[call_idx + 1]
    if not isinstance(if_stmt, nodes.IfStmt):
        return None
    if _contains_goto(if_stmt):
        return None
    keys = _begn_breakout_keys(if_stmt.cond, pfx)
    if not keys:
        return None

    setup_start = call_idx
    for i in range(call_idx - 1, -1, -1):
        if _stmt_touches_pfx_node(stmts[i], pfx):
            setup_start = i
        else:
            break
    return {
        "pfx": pfx,
        "name": name,
        "keys": keys,
        "then_body": if_stmt.then,
        "call_idx": call_idx,
        "setup_start": setup_start,
    }


_STRUCT_CONV = {"FUNCTION", "FORMAT", "STATUZ", "PARAMS"}


def _read_io_ops(ctx) -> set:
    ops = (ctx.io_default_pattern or {}).get("operations", {})
    return {code.upper() for code, tmpl in ops.items() if "findBy" in str(tmpl)}


def _write_io_ops(ctx) -> set:
    ops = (ctx.io_default_pattern or {}).get("operations", {})
    return {code.upper() for code, tmpl in ops.items()
            if "save" in str(tmpl).lower() or "delete" in str(tmpl).lower()}


def _is_op_delete(func: str, ctx) -> bool:
    tmpl = (ctx.io_default_pattern or {}).get("operations", {}).get(func, "")
    return "delete" in str(tmpl).lower()


def _split_and(tokens: list[str]) -> list[list[str]]:
    out, cur = [], []
    for tok in tokens:
        if tok.upper() == "AND":
            out.append(cur)
            cur = []
        else:
            cur.append(tok)
    out.append(cur)
    return out


def _parse_statuz_term(term: list[str], pfx: str):
    tu = [t.upper() for t in term]
    if "=" not in tu:
        return None
    negate = "NOT" in tu
    eqi = tu.index("=")
    left = [t for t in tu[:eqi] if t != "NOT"]
    right = term[eqi + 1:]
    if len(left) != 1 or len(right) != 1 or left[0] != f"{pfx}-STATUZ":
        return None
    return negate, right[0].upper()


def _statuz_form(cond_tokens: list[str], pfx: str):
    parsed = []
    for term in _split_and(cond_tokens):
        p = _parse_statuz_term(term, pfx)
        if p is None:
            return None
        parsed.append(p)
    if len(parsed) == 1:
        neg, code = parsed[0]
        if code == "O-K":
            return "notok" if neg else "ok"
        if code in ("MRNF", "ENDP"):
            return "ok" if neg else "notok"
        return None
    if len(parsed) == 2:
        codes = {c for _neg, c in parsed}
        if all(neg for neg, _c in parsed) and "O-K" in codes and (codes & {"MRNF", "ENDP"}):
            return "error"
    return None


def _write_statuz_form(cond_tokens: list[str], pfx: str):
    parsed = []
    for term in _split_and(cond_tokens):
        p = _parse_statuz_term(term, pfx)
        if p is None:
            return None
        parsed.append(p)
    if any(neg and code == "O-K" for neg, code in parsed):
        return "error"
    return None


def _setup_func_code_nodes(stmts: list, pfx: str, codes: set):
    for st in stmts:
        toks = getattr(st, "tokens", None) or []
        tu = [t.upper() for t in toks]
        if tu[:1] == ["MOVE"] and "TO" in tu and f"{pfx}-FUNCTION" in tu:
            for code in codes:
                if code in tu:
                    return code
    return None


def _move_key_target_node(st, pfx: str):
    toks = getattr(st, "tokens", None) or []
    tu = [t.upper() for t in toks]
    if tu[:1] != ["MOVE"] or "TO" not in tu:
        return None
    ti = tu.index("TO")
    src = toks[1:ti]
    dsts = toks[ti + 1:]
    if len(src) != 1 or len(dsts) != 1:
        return None
    dst = dsts[0].upper()
    if "-" not in dst or dst.split("-", 1)[0] != pfx:
        return None
    field = dst.split("-", 1)[1]
    if field in _STRUCT_CONV:
        return None
    return field, src[0]


def _is_statuz_if_node(st, pfx: str) -> bool:
    return isinstance(st, nodes.IfStmt) and any(t.upper() == f"{pfx}-STATUZ" for t in st.cond)


def _is_init_params_node(st, pfx: str) -> bool:
    toks = getattr(st, "tokens", None) or []
    if not toks:
        return False
    tu = [t.upper() for t in toks]
    if tu[:1] == ["INITIALIZE"] and f"{pfx}-PARAMS" in tu:
        return True
    if tu[:1] == ["MOVE"] and "TO" in tu and f"{pfx}-PARAMS" in tu:
        src = tu[1:tu.index("TO")]
        return len(src) == 1 and src[0] in {
            "SPACES", "SPACE", "ZEROS", "ZEROES", "ZERO", "LOW-VALUES", "HIGH-VALUES"
        }
    return False


def _match_readr_single_nodes(stmts: list, ctx):
    read_ops = _read_io_ops(ctx)
    if not read_ops or not stmts:
        return None

    call_idx = None
    call_info = None
    func = None
    for i, st in enumerate(stmts):
        ci = _stmt_call_io(st, ctx)
        if not ci:
            continue
        f = _setup_func_code_nodes(stmts[:i], ci[1], read_ops)
        if f:
            call_idx, call_info, func = i, ci, f
            break
    if call_idx is None:
        return None
    name, pfx = call_info

    setup_start = call_idx
    for i in range(call_idx - 1, -1, -1):
        if _stmt_touches_pfx_node(stmts[i], pfx):
            setup_start = i
        else:
            break

    keys = []
    for st in stmts[setup_start:call_idx]:
        mk = _move_key_target_node(st, pfx)
        if mk:
            keys.append(mk)
    if not keys:
        return None

    mode, then_body, else_body, try_tail = "plain", [], [], []
    consume_to = call_idx + 1
    nxt = stmts[call_idx + 1] if call_idx + 1 < len(stmts) else None
    if nxt is not None and _is_statuz_if_node(nxt, pfx):
        form = _statuz_form(nxt.cond, pfx)
        if form is None:
            return None
        if form == "error":
            mode, then_body = "error", nxt.then
            try_tail, consume_to = stmts[call_idx + 2:], len(stmts)
        else:
            mode, then_body, else_body = form, nxt.then, nxt.els
            consume_to = call_idx + 2
    return {
        "pfx": pfx,
        "name": name,
        "func": func,
        "keys": keys,
        "mode": mode,
        "then_body": then_body,
        "else_body": else_body,
        "try_tail": try_tail,
        "setup_start": setup_start,
        "consume_to": consume_to,
    }


def _match_write_single_nodes(stmts: list, ctx):
    write_ops = _write_io_ops(ctx)
    if not write_ops or not stmts:
        return None

    call_idx = None
    call_info = None
    func = None
    for i, st in enumerate(stmts):
        ci = _stmt_call_io(st, ctx)
        if not ci:
            continue
        f = _setup_func_code_nodes(stmts[:i], ci[1], write_ops)
        if f:
            call_idx, call_info, func = i, ci, f
            break
    if call_idx is None:
        return None
    name, pfx = call_info

    setup_start = call_idx
    for i in range(call_idx - 1, -1, -1):
        if _stmt_touches_pfx_node(stmts[i], pfx):
            setup_start = i
        else:
            break

    is_new = any(_is_init_params_node(st, pfx) for st in stmts[setup_start:call_idx])
    setters = [st for st in stmts[setup_start:call_idx] if _move_key_target_node(st, pfx)]

    mode, then_body, try_tail = "plain", [], []
    consume_to = call_idx + 1
    nxt = stmts[call_idx + 1] if call_idx + 1 < len(stmts) else None
    if nxt is not None and _is_statuz_if_node(nxt, pfx):
        if _write_statuz_form(nxt.cond, pfx) is None:
            return None
        mode, then_body = "error", nxt.then
        try_tail, consume_to = stmts[call_idx + 2:], len(stmts)

    return {
        "pfx": pfx,
        "name": name,
        "func": func,
        "is_new": is_new,
        "is_delete": _is_op_delete(func, ctx),
        "setters": setters,
        "mode": mode,
        "then_body": then_body,
        "try_tail": try_tail,
        "setup_start": setup_start,
        "consume_to": consume_to,
    }


def _strip_struct_setup_nodes(stmts: list, pfx: str) -> list:
    out: list = []
    for st in stmts:
        if isinstance(st, nodes.MoveStmt):
            toks = [t.upper() for t in st.tokens]
            if toks[:1] == ["MOVE"] and "TO" in toks:
                dests = toks[toks.index("TO") + 1:]
                if any(t.startswith(f"{pfx}-") for t in dests):
                    continue
        if isinstance(st, nodes.Leaf):
            toks = [t.upper() for t in st.tokens]
            if toks[:1] == ["INITIALIZE"] and any(t.startswith(f"{pfx}-") for t in toks[1:]):
                continue
        out.append(st)
    return out


def _stmt_touches_pfx_node(st, pfx: str) -> bool:
    toks = getattr(st, "tokens", None) or []
    return any(t.upper().startswith(f"{pfx}-") for t in toks)
