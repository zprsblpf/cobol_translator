"""
相3 骨架装配公用底座 —— BEGN/READR/WRITE IO 形态识别 + struct_rebind 段级吸收。

来源：原 translator/rules.py 的 `_rewrite_begn_loops` 一族（rules.py:123–800，~600 行）**原样迁址**，
      逻辑零改；仅把「节点字段读取」抽成访问器协议（NodeAccess）、「段体渲染」抽成 render_body 回调、
      「raw 节点构造」抽成 make_raw 回调，三者由调用方按路径注入 → 旧 rules 与 asg.visitor 共调同一
      匹配/渲染逻辑 → IO 吸收体 Java 逐字符一致。
对应设计：docs/详细设计/步骤24C-绞杀项4骨架装配③BEGN-READR-WRITE-IO形态迁visitor设计.md §3.3 / §4.1。
设计思路：四类确定性 IO 形态（① BEGN+NEXTR 自跳循环、② 单次 BEGN 等值定位、③ 单条读 READR/READS、
      ④ 单条写 UPDAT/WRITE/DELET）在状态机降级**之前**对 paras=[(label,[node])] 做段级结构改写，
      把「裸 CALL 'xxxIO' + setup MOVE + IF STATUZ」吸收成高阶 Java（List+for-each / findBy…Begn /
      record!=null / repo.save），并对吸收体内字段做 struct_rebind（<pfx>-FIELD → 循环/记录变量）。
      依赖单向 rules→skel、asg.visitor→skel，skel 不反向 import rules，无环。

      rebind 两路差异（设计 §3.5）：旧路两趟（占位 + 延迟 translate_leaf 读 struct_rebind 回填），
      新路一趟（render_body 同步渲染时 ctx.struct_objects[pfx] 已置）；二者均经同一 leaf 译器 + 同一
      ctx.struct_objects 活动态 → 吸收体逐字符一致。_tag_rebind 仅旧路两趟回填需要，新路其标记不被读，
      但为递归口径一致仍经 acc 走读（在 ASG 节点上设置 struct_rebind 属性无害、不被消费）。

用法示例：
    from translator.skel import rewrite_io_paras, STMT_ACCESS
    paras = rewrite_io_paras(paras, ctx, acc=STMT_ACCESS,
                             render_body=lambda s, i: build_skeleton(s, ctx, i),
                             make_raw=lambda lines: _raw_stmt(lines))
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

# 表达式/命名/IO 查表底座（绞杀项3 已下沉 leaf）：派生 finder/repo 名、操作数翻译、IO 信息解析。
from translator.leaf.expr import _java, _pascal, _operand
from translator.leaf.cond import translate_condition as _try_condition
from translator.leaf.call import resolve_io_info


@dataclass(frozen=True)
class NodeAccess:
    """节点只读访问器协议（设计 §3.2）：把匹配器读取的 5 个节点字段抽成回调，
    旧路传 STMT_ACCESS（属性直读）、新路传 ASG_ACCESS（按类型派生 kind + then/els/cond/inline_body 映射）。
    - kind(node)->str：simple | if | evaluate | perform | raw
    - tokens(node)->list[str]：simple=全句；if=条件；evaluate=主语
    - children(node)->list：if-then / perform 内联体
    - else_children(node)->list：if-else
    - whens(node)->list：evaluate 的 [(cond_tokens, [node]), …]"""
    kind: Callable
    tokens: Callable
    children: Callable
    else_children: Callable
    whens: Callable


# 旧路（Stmt）访问器：属性直读。新路 ASG_ACCESS 定义在 asg/visitor.py（按节点类型派生）。
STMT_ACCESS = NodeAccess(
    kind=lambda s: s.kind,
    tokens=lambda s: s.tokens,
    children=lambda s: s.children,
    else_children=lambda s: s.else_children,
    whens=lambda s: s.whens,
)


@dataclass(frozen=True)
class _Env:
    """改写期注入物：节点访问器 + 翻译 ctx + 段体渲染回调 + raw 节点工厂（设计 §3.3）。
    四形态匹配器/渲染器统一吃 env，逻辑零改、仅通过 env 解耦节点类型与渲染路径。"""
    acc: NodeAccess
    ctx: object
    render_body: Callable     # (stmts, indent) -> list[str]
    make_raw: Callable        # (lines) -> node（旧 Stmt(kind=raw) / 新 nodes.Raw）


_STRUCT_CONV = {"FUNCTION", "FORMAT", "STATUZ", "PARAMS"}   # 调用约定字段（非真实数据字段）


# ── BEGN+NEXTR 段循环 → List + for-each 改写（确定性，先于状态机降级）──────────────

def _stmt_call_io(st, env: _Env):
    """CALL 'xxxIO' USING <PFX>-PARAMS → (子程序名, 前缀)，否则 None。"""
    acc = env.acc
    toks = acc.tokens(st)
    if acc.kind(st) != "simple" or not toks or toks[0].upper() != "CALL":
        return None
    if len(toks) < 2:
        return None
    name = toks[1].strip("'\"").upper()
    u = [t.upper() for t in toks]
    if "USING" not in u:
        return None
    arg = toks[u.index("USING") + 1] if u.index("USING") + 1 < len(toks) else ""
    if not name.endswith("IO") or "-" not in arg:
        return None
    return name, arg.split("-", 1)[0].upper()


def _goto_target(st, env: _Env):
    acc = env.acc
    toks = acc.tokens(st)
    if acc.kind(st) == "simple" and toks and toks[0].upper() == "GO":
        for t in toks[1:]:
            if t.upper() != "TO":
                return t.upper()
    return None


def _is_move_nextr(st, pfx: str, env: _Env) -> bool:
    acc = env.acc
    if acc.kind(st) != "simple":
        return False
    tu = [t.upper() for t in acc.tokens(st)]
    return tu[:1] == ["MOVE"] and "NEXTR" in tu and f"{pfx}-FUNCTION" in tu


def _setup_has_begn(stmts: list, pfx: str, env: _Env) -> bool:
    acc = env.acc
    for st in stmts:
        if acc.kind(st) == "simple":
            tu = [t.upper() for t in acc.tokens(st)]
            if tu[:1] == ["MOVE"] and "BEGN" in tu and f"{pfx}-FUNCTION" in tu:
                return True
    return False


def _then_single_goto(st, env: _Env):
    """IF 的 then 分支恰为单条 GO TO X（无 else）→ 返回 X。"""
    acc = env.acc
    if acc.kind(st) == "if" and not acc.else_children(st) and len(acc.children(st)) == 1:
        return _goto_target(acc.children(st)[0], env)
    return None


def _is_filter_if(st, pfx: str, loop_label: str, env: _Env) -> bool:
    """IF cond → [MOVE NEXTR TO pfx-FUNCTION, GO TO loop_label]（结果集过滤 → continue）。"""
    acc = env.acc
    if acc.kind(st) != "if" or acc.else_children(st) or len(acc.children(st)) != 2:
        return False
    ch = acc.children(st)
    return _is_move_nextr(ch[0], pfx, env) and _goto_target(ch[1], env) == loop_label


def _contains_goto(st, env: _Env) -> bool:
    acc = env.acc
    if _goto_target(st, env):
        return True
    for c in list(acc.children(st)) + list(acc.else_children(st)):
        if _contains_goto(c, env):
            return True
    for _cond, body in (acc.whens(st) or []):
        if any(_contains_goto(x, env) for x in body):
            return True
    return False


def _split_or(tokens: list[str]) -> list[list[str]]:
    """按顶层 OR 切分条件 token（本场景条件无括号）。"""
    out, cur = [], []
    for t in tokens:
        if t.upper() == "OR":
            out.append(cur); cur = []
        else:
            cur.append(t)
    out.append(cur)
    return out


def _begn_breakout_keys(cond_tokens: list[str], pfx: str):
    """跳出条件 → 等值键列表 [(键COBOL名, 值COBOL名)]。
    每个 OR 子项须为 <pfx>-STATUZ NOT = O-K（跳过）或 <pfx>-KEY NOT = VAL（取键）；
    含 AND / 非 pfx 字段 / 形状不符 → None（放弃改写）。
    """
    keys = []
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


def _match_begn_loop(loop_label: str, stmts: list, env: _Env):
    """识别 BEGN+NEXTR 自跳循环段，返回 {pfx,name,keys,exit_label,filters,body} 或 None。"""
    acc = env.acc
    if not stmts:
        return None
    ci = _stmt_call_io(stmts[0], env)
    if not ci:
        return None
    name, pfx = ci
    keys = exit_label = None
    filters: list = []
    body: list = []
    for st in stmts[1:]:
        tgt = _then_single_goto(st, env)
        if tgt and keys is None and tgt != loop_label:
            kk = _begn_breakout_keys(acc.tokens(st), pfx)
            if kk is None:
                return None
            keys, exit_label = kk, tgt
            continue
        if _is_filter_if(st, pfx, loop_label, env):
            filters.append(st)
            continue
        if _is_move_nextr(st, pfx, env) or _goto_target(st, env) == loop_label:
            continue                        # 尾部 MOVE NEXTR / GO TO 自身 → 吸收
        if _contains_goto(st, env):
            return None                     # 体内有未识别跳转 → 不安全，放弃
        body.append(st)
    if keys is None or exit_label is None:
        return None
    return {"pfx": pfx, "name": name, "keys": keys,
            "exit_label": exit_label, "filters": filters, "body": body}


def _strip_struct_setup(stmts: list, pfx: str, env: _Env) -> list:
    """移除对 <pfx>-* 的赋值/INITIALIZE（BEGN setup 已被 finder 吸收）。"""
    acc = env.acc
    out = []
    for st in stmts:
        toks = acc.tokens(st)
        if acc.kind(st) == "simple" and toks:
            tu = [t.upper() for t in toks]
            if tu[0] == "MOVE" and "TO" in tu and any(
                    t.startswith(f"{pfx}-") for t in tu[tu.index("TO") + 1:]):
                continue
            if tu[0] == "INITIALIZE" and any(t.upper().startswith(f"{pfx}-") for t in toks[1:]):
                continue
        out.append(st)
    return out


def _tag_rebind(stmts: list, rebind: dict, env: _Env) -> None:
    """给 for-each 体内所有节点（含嵌套）打结构体重绑定标记，供旧路延迟叶子翻译使用（设计 §3.5）。
    新路 render_body 一趟内联渲染、标记不被读，但仍按 acc 递归保口径一致（在 ASG 节点设属性无害）。"""
    acc = env.acc
    for st in stmts:
        st.struct_rebind = rebind
        _tag_rebind(list(acc.children(st)), rebind, env)
        _tag_rebind(list(acc.else_children(st)), rebind, env)
        for _c, body in (acc.whens(st) or []):
            _tag_rebind(body, rebind, env)


def _render_begn_foreach(info: dict, env: _Env) -> list[str]:
    """渲染 List + for-each（裸字段名，st. 前缀由 nodes 后处理统一添加）。"""
    ctx = env.ctx
    pfx, name = info["pfx"], info["name"]
    io = resolve_io_info(name, ctx.io_programs, ctx.io_default_pattern)
    repo = io["field_name"] if io else _java(pfx) + "Repository"
    rec_cls = _pascal(pfx) + "Record"
    loop_var = _java(pfx)
    list_var = loop_var + "List"
    finder = "findBy" + "And".join(_pascal(k) for k, _ in info["keys"]) + "Begn"
    vals = ", ".join(_operand(v, ctx) for _, v in info["keys"])
    lines = [f"List<{rec_cls}> {list_var} = {repo}.{finder}({vals});",
             f"for ({rec_cls} {loop_var} : {list_var}) {{"]
    rebind = {pfx: loop_var}
    _tag_rebind(info["filters"] + info["body"], rebind, env)   # 旧路延迟叶子用标记
    saved = ctx.struct_objects.get(pfx)
    ctx.struct_objects[pfx] = loop_var          # 渲染期条件/循环头 <pfx>-FIELD → loop_var.getField()
    for f in info["filters"]:
        cond = _try_condition(env.acc.tokens(f), ctx)
        lines.append(f"    if ({cond}) {{ continue; }}" if cond
                     else f"    // TODO 过滤条件: {' '.join(env.acc.tokens(f))}")
    lines.extend(env.render_body(info["body"], 1))
    if saved is None:
        ctx.struct_objects.pop(pfx, None)
    else:
        ctx.struct_objects[pfx] = saved
    lines.append("}")
    return lines


def _stmt_touches_pfx(st, pfx: str, env: _Env) -> bool:
    """检查语句 token 中是否包含 <pfx>- 前缀的标识符。"""
    acc = env.acc
    toks = acc.tokens(st)
    if acc.kind(st) != "simple" or not toks:
        return False
    for t in toks:
        if t.upper().startswith(f"{pfx}-"):
            return True
    return False


def _match_begn_single(stmts: list, env: _Env):
    """识别单次 BEGN 等值定位（无 NEXTR 回跳）：INITIALIZE → MOVE keys → MOVE BEGN → CALL → IF。
    返回 {pfx,name,keys,then_stmts,call_idx,setup_start} 或 None。"""
    acc = env.acc
    if not stmts:
        return None

    # 1. 定位 CALL 'xxxIO' USING pfx-PARAMS（前序须有 MOVE BEGN TO pfx-FUNCTION）
    call_idx = None
    call_info = None
    for i, st in enumerate(stmts):
        ci = _stmt_call_io(st, env)
        if ci:
            name, pfx = ci
            for s in stmts[:i]:
                if acc.kind(s) == "simple" and acc.tokens(s):
                    tu = [t.upper() for t in acc.tokens(s)]
                    if tu[:1] == ["MOVE"] and "BEGN" in tu and f"{pfx}-FUNCTION" in tu:
                        call_idx = i
                        call_info = ci
                        break
            if call_idx is not None:
                break
    if call_idx is None:
        return None

    name, pfx = call_info

    # 2. 紧随 CALL 后须有 IF（then 分支不含 GO TO 回跳）
    if call_idx + 1 >= len(stmts):
        return None
    if_stmt = stmts[call_idx + 1]
    if acc.kind(if_stmt) != "if":
        return None

    # then 分支含 GO TO 回跳 → 属于 loop pattern，不在 single-shot 处理
    if _contains_goto(if_stmt, env):
        return None

    # 从 IF 条件提取等值键（复用 loop 的 breakout keys 解析）
    keys = _begn_breakout_keys(acc.tokens(if_stmt), pfx)
    if not keys:
        return None

    # 3. 从 CALL 向前找 setup 起始（首个不涉及 pfx 的语句的下一位置）
    setup_start = call_idx
    for i in range(call_idx - 1, -1, -1):
        if _stmt_touches_pfx(stmts[i], pfx, env):
            setup_start = i
        else:
            break

    return {
        "pfx": pfx, "name": name, "keys": keys,
        "then_stmts": acc.children(if_stmt),
        "call_idx": call_idx, "setup_start": setup_start,
    }


def _render_begn_single(info: dict, env: _Env) -> list[str]:
    """渲染单次 BEGN → findBy...Begn() + List.isEmpty() 检查。"""
    ctx = env.ctx
    pfx, name = info["pfx"], info["name"]
    io = resolve_io_info(name, ctx.io_programs, ctx.io_default_pattern)
    repo = io["field_name"] if io else _java(pfx) + "Repository"
    rec_cls = _pascal(pfx) + "Record"
    list_var = _java(pfx) + "List"
    finder = "findBy" + "And".join(_pascal(k) for k, _ in info["keys"]) + "Begn"
    vals = ", ".join(_operand(v, ctx) for _, v in info["keys"])

    lines = [f"List<{rec_cls}> {list_var} = {repo}.{finder}({vals});"]
    then_lines = env.render_body(info["then_stmts"], 1)
    if then_lines:
        lines.append(f"if ({list_var}.isEmpty()) {{")
        lines.extend(then_lines)
        lines.append("}")
    return lines


# ── 单条「读」IO（READR/READS）→ findBy…Readr() + record!=null 吸收（步骤10）──────────
# 与 BEGN 单次同形（setup + CALL + IF STATUZ），但功能码=READR/READS、返回单条记录、
# STATUZ=O-K ⇔ record!=null。见 docs/详细设计/步骤10、docs/翻译标准/io查询.md。

def _read_io_ops(env: _Env) -> set:
    """单条「读」操作功能码集合：io_default_pattern.operations 中模板含 findBy 的（READR/READS）。
    写操作（save/delete）不返回记录、无 record!=null 语义，不走结构吸收，留给 _t_call。"""
    ops = (env.ctx.io_default_pattern or {}).get("operations", {})
    return {code.upper() for code, tmpl in ops.items() if "findBy" in str(tmpl)}


def _split_and(tokens: list[str]) -> list[list[str]]:
    """按顶层 AND 切分条件 token（本场景 STATUZ 条件无括号）。"""
    out, cur = [], []
    for t in tokens:
        if t.upper() == "AND":
            out.append(cur); cur = []
        else:
            cur.append(t)
    out.append(cur)
    return out


def _parse_statuz_term(term: list[str], pfx: str):
    """单个比较项 `pfx-STATUZ [NOT] = CODE` → (negate, CODE 大写)；非 STATUZ/形状不符 → None。"""
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
    """识别紧跟 READR CALL 的 IF STATUZ 形态 → 'ok'|'notok'|'error'|None（§3.3）。
      · 单项 = O-K          → ok    (record != null)；NOT = O-K → notok (== null)
      · 单项 = MRNF/ENDP    → notok；NOT = MRNF/ENDP → ok
      · 两项 AND：NOT=O-K AND NOT=MRNF/ENDP → error（决策 A：真 DB 错误，try/catch 调 580）
      · 其它（含掺入键字段）→ None（不半吸收，整体放弃）。
    """
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
        codes = {c for _, c in parsed}
        if all(neg for neg, _ in parsed) and "O-K" in codes and (codes & {"MRNF", "ENDP"}):
            return "error"
    return None


def _setup_func_code(stmts: list, pfx: str, codes: set, env: _Env):
    """前序 setup 里 MOVE <code> TO pfx-FUNCTION 的功能码（限 codes 集合），否则 None。"""
    acc = env.acc
    for st in stmts:
        if acc.kind(st) == "simple" and acc.tokens(st):
            tu = [t.upper() for t in acc.tokens(st)]
            if tu[:1] == ["MOVE"] and "TO" in tu and f"{pfx}-FUNCTION" in tu:
                for c in codes:
                    if c in tu:
                        return c
    return None


def _move_key_target(st, pfx: str, env: _Env):
    """MOVE src TO pfx-<字段>（排除 FUNCTION/FORMAT/STATUZ/PARAMS）→ (字段COBOL名, src token)。
    决策 B1：CALL 前这些 MOVE 目标即查询键，按出现顺序拼 finder 实参。"""
    acc = env.acc
    toks = acc.tokens(st)
    if acc.kind(st) != "simple" or not toks:
        return None
    tu = [t.upper() for t in toks]
    if tu[:1] != ["MOVE"] or "TO" not in tu:
        return None
    ti = tu.index("TO")
    src = toks[1:ti]
    dsts = toks[ti + 1:]
    if len(src) != 1 or len(dsts) != 1:
        return None
    d = dsts[0].upper()
    if "-" not in d or d.split("-", 1)[0] != pfx:
        return None
    field = d.split("-", 1)[1]
    if field in _STRUCT_CONV:
        return None
    return field, src[0]


def _is_statuz_if(st, pfx: str, env: _Env) -> bool:
    acc = env.acc
    return acc.kind(st) == "if" and any(t.upper() == f"{pfx}-STATUZ" for t in acc.tokens(st))


def _match_readr_single(stmts: list, env: _Env):
    """识别单条读：setup(MOVE 键/SPACES/FUNCTION/FORMAT) + CALL 'xxxIO' + [IF STATUZ]。
    返回 {pfx,name,func,keys,mode,then_stmts,else_stmts,try_tail,setup_start,consume_to} 或 None。"""
    acc = env.acc
    read_ops = _read_io_ops(env)
    if not read_ops or not stmts:
        return None

    # 1. 定位 CALL，且前序 setup 有 MOVE <readop> TO pfx-FUNCTION
    call_idx = call_info = func = None
    for i, st in enumerate(stmts):
        ci = _stmt_call_io(st, env)
        if not ci:
            continue
        f = _setup_func_code(stmts[:i], ci[1], read_ops, env)
        if f:
            call_idx, call_info, func = i, ci, f
            break
    if call_idx is None:
        return None
    name, pfx = call_info

    # 2. setup 起点：从 CALL 向前收集连续涉及 pfx 的语句
    setup_start = call_idx
    for i in range(call_idx - 1, -1, -1):
        if _stmt_touches_pfx(stmts[i], pfx, env):
            setup_start = i
        else:
            break

    # 3. 键备料（决策 B1）：setup 内 MOVE val TO pfx-<字段>，按序
    keys = []
    for st in stmts[setup_start:call_idx]:
        mk = _move_key_target(st, pfx, env)
        if mk:
            keys.append(mk)
    if not keys:
        return None

    # 4. 紧随 CALL 的 IF STATUZ（可选）
    mode, then_stmts, else_stmts, try_tail = "plain", [], [], []
    consume_to = call_idx + 1
    nxt = stmts[call_idx + 1] if call_idx + 1 < len(stmts) else None
    if nxt is not None and _is_statuz_if(nxt, pfx, env):
        form = _statuz_form(acc.tokens(nxt), pfx)
        if form is None:
            return None                                # STATUZ-IF 形态不认识 → 整体放弃
        if form == "error":
            mode, then_stmts = "error", acc.children(nxt)   # then(PERFORM 580) → catch
            try_tail, consume_to = stmts[call_idx + 2:], len(stmts)   # CALL+后续 全包进 try
        else:
            mode, then_stmts, else_stmts = form, acc.children(nxt), acc.else_children(nxt)
            consume_to = call_idx + 2
    return {"pfx": pfx, "name": name, "func": func, "keys": keys, "mode": mode,
            "then_stmts": then_stmts, "else_stmts": else_stmts, "try_tail": try_tail,
            "setup_start": setup_start, "consume_to": consume_to}


def _render_rebound(stmts: list, env: _Env, pfx: str, var: str, indent: int) -> list[str]:
    """渲染体内语句，临时把 pfx 重绑定到 record 变量：pfx-FIELD → var.getField()。"""
    ctx = env.ctx
    rebind = {pfx: var}
    _tag_rebind(stmts, rebind, env)
    saved = ctx.struct_objects.get(pfx)
    ctx.struct_objects[pfx] = var
    try:
        return env.render_body(stmts, indent)
    finally:
        if saved is None:
            ctx.struct_objects.pop(pfx, None)
        else:
            ctx.struct_objects[pfx] = saved


def _render_readr_single(info: dict, env: _Env) -> list[str]:
    """渲染单条读 → Rec r = repo.findBy…Readr(键); + STATUZ 改写（record!=null / try-catch）。"""
    ctx = env.ctx
    pfx, name, func = info["pfx"], info["name"], info["func"]
    io = resolve_io_info(name, ctx.io_programs, ctx.io_default_pattern)
    repo = io["field_name"] if io else _java(pfx) + "Repository"
    rec_cls = _pascal(pfx) + "Record"
    var = _java(pfx)
    # finder：按键派生 findBy<键…>Readr（同 BEGN，不取 io_default_pattern 的通用占位模板名）；
    #   仅当该表在 io_programs 有「显式」操作码覆盖（如 CHDRENQIO→findByPolicyNoReadr）才用其方法名。
    raw_op = (ctx.io_programs.get(name) or {}).get("operations", {}).get(func)
    finder = (raw_op.split("(", 1)[0] if raw_op
              else "findBy" + "And".join(_pascal(k) for k, _ in info["keys"]) + func.capitalize())
    vals = ", ".join(_operand(v, ctx) for _, v in info["keys"])
    call_line = f"{rec_cls} {var} = {repo}.{finder}({vals});"

    mode = info["mode"]
    if mode == "plain":
        return [call_line]
    if mode == "error":
        # 决策 A：finder + 后续 包进 try；原 580 分支移入 catch
        out = ["try {", "    " + call_line]
        out.extend(_render_rebound(info["try_tail"], env, pfx, var, 1))
        out.append("} catch (Exception e) {")
        out.extend(_render_rebound(info["then_stmts"], env, pfx, var, 1) or ["    // (空)"])
        out.append("}")
        return out
    # ok / notok：record != null / == null
    cmp = "!= null" if mode == "ok" else "== null"
    out = [call_line, f"if ({var} {cmp}) {{"]
    out.extend(_render_rebound(info["then_stmts"], env, pfx, var, 1) or ["    // (空)"])
    if info["else_stmts"]:
        out.append("} else {")
        out.extend(_render_rebound(info["else_stmts"], env, pfx, var, 1))
    out.append("}")
    return out


# ── 单条「写」IO（UPDAT/WRITE/WRITR/WRITS/REWRT/DELET）→ save()/delete() 吸收（步骤11）──
# 与单条读同形（setup + CALL + IF STATUZ），但功能码=写、不返回记录、save/delete 丢返回，
# STATUZ NOT=O-K 统一 try/catch 调错误段（决策 W-3 选项②，无 record!=null 语义）。
# 见 docs/详细设计/步骤11、knowledge/io_call_patterns.md「更新（UPDAT）」节。

def _write_io_ops(env: _Env) -> set:
    """单条「写」操作功能码集合：io_default_pattern.operations 中模板含 save/delete 的。
    与 _read_io_ops（findBy）互补；读写两路各自结构吸收。"""
    ops = (env.ctx.io_default_pattern or {}).get("operations", {})
    return {code.upper() for code, t in ops.items()
            if "save" in str(t).lower() or "delete" in str(t).lower()}


def _is_op_delete(func: str, env: _Env) -> bool:
    """该写功能码是否为删除类（模板含 delete）→ repo.delete(entity)；否则 save(entity)。"""
    tmpl = (env.ctx.io_default_pattern or {}).get("operations", {}).get(func, "")
    return "delete" in str(tmpl).lower()


def _is_init_params(st, pfx: str, env: _Env) -> bool:
    """识别 MOVE SPACES/低高值 TO pfx-PARAMS 或 INITIALIZE pfx-PARAMS（决策 W-1：插入新记录起手）。"""
    acc = env.acc
    toks = acc.tokens(st)
    if acc.kind(st) != "simple" or not toks:
        return False
    tu = [t.upper() for t in toks]
    if tu[:1] == ["INITIALIZE"] and f"{pfx}-PARAMS" in tu:
        return True
    if tu[:1] == ["MOVE"] and "TO" in tu and f"{pfx}-PARAMS" in tu:
        src = tu[1:tu.index("TO")]
        if len(src) == 1 and src[0] in ("SPACES", "SPACE", "ZEROS", "ZEROES",
                                        "ZERO", "LOW-VALUES", "HIGH-VALUES"):
            return True
    return False


def _write_statuz_form(cond_tokens: list[str], pfx: str):
    """写场景 STATUZ 形态（决策 W-3 选项②）：每项均为 pfx-STATUZ 比较且含 NOT=O-K
    → 'error'（try/catch 调错误段）；其它（掺键/非 O-K 形）→ None（不吸收，整体放弃）。"""
    parsed = []
    for term in _split_and(cond_tokens):
        p = _parse_statuz_term(term, pfx)
        if p is None:
            return None
        parsed.append(p)
    if any(neg and code == "O-K" for neg, code in parsed):
        return "error"
    return None


def _match_write_single(stmts: list, env: _Env):
    """识别单条写：setup(MOVE 字段/SPACES/FUNCTION/FORMAT) + CALL 'xxxIO' + [IF STATUZ]。
    返回 {pfx,name,func,is_new,is_delete,setters,mode,then_stmts,try_tail,setup_start,consume_to} 或 None。"""
    acc = env.acc
    write_ops = _write_io_ops(env)
    if not write_ops or not stmts:
        return None

    # 1. 定位 CALL，且前序 setup 有 MOVE <写功能码> TO pfx-FUNCTION
    call_idx = call_info = func = None
    for i, st in enumerate(stmts):
        ci = _stmt_call_io(st, env)
        if not ci:
            continue
        f = _setup_func_code(stmts[:i], ci[1], write_ops, env)
        if f:
            call_idx, call_info, func = i, ci, f
            break
    if call_idx is None:
        return None
    name, pfx = call_info

    # 2. setup 起点：从 CALL 向前收集连续涉及 pfx 的语句
    setup_start = call_idx
    for i in range(call_idx - 1, -1, -1):
        if _stmt_touches_pfx(stmts[i], pfx, env):
            setup_start = i
        else:
            break

    # 3. 实体来源（W-1）：setup 含 MOVE SPACES/INITIALIZE pfx-PARAMS → 插入(new)；否则复用上文实体
    is_new = any(_is_init_params(st, pfx, env) for st in stmts[setup_start:call_idx])
    # 4. setter（W-2）：CALL 前 MOVE val TO pfx-<字段>（排除 FUNCTION/FORMAT/STATUZ/PARAMS）
    setters = [st for st in stmts[setup_start:call_idx] if _move_key_target(st, pfx, env)]

    # 5. 紧随 CALL 的 IF STATUZ（可选）→ try/catch（W-3 选项②）
    mode, then_stmts, try_tail = "plain", [], []
    consume_to = call_idx + 1
    nxt = stmts[call_idx + 1] if call_idx + 1 < len(stmts) else None
    if nxt is not None and _is_statuz_if(nxt, pfx, env):
        if _write_statuz_form(acc.tokens(nxt), pfx) is None:
            return None                                    # STATUZ-IF 形态不认识 → 整体放弃
        mode, then_stmts = "error", acc.children(nxt)      # then(PERFORM 580/9999) → catch
        try_tail, consume_to = stmts[call_idx + 2:], len(stmts)   # CALL+后续 全包进 try
    return {"pfx": pfx, "name": name, "func": func, "is_new": is_new,
            "is_delete": _is_op_delete(func, env), "setters": setters, "mode": mode,
            "then_stmts": then_stmts, "try_tail": try_tail,
            "setup_start": setup_start, "consume_to": consume_to}


def _render_write_single(info: dict, env: _Env) -> list[str]:
    """渲染单条写 → [XxxRecord x = new XxxRecord();] + x.setField(...); + repo.save/delete(x);
    + STATUZ error 形 try/catch（错误段移入 catch）。实体一律 XxxRecord（W-2），丢 save 返回。"""
    ctx = env.ctx
    pfx, name = info["pfx"], info["name"]
    io = resolve_io_info(name, ctx.io_programs, ctx.io_default_pattern)
    repo = io["field_name"] if io else _java(pfx) + "Repository"
    rec_cls = _pascal(pfx) + "Record"
    var = _java(pfx)

    lines: list[str] = []
    if info["is_new"]:                                     # W-1 插入：声明并 new；复用场景沿用上文 var
        lines.append(f"{rec_cls} {var} = new {rec_cls}();")
    lines.extend(_render_rebound(info["setters"], env, pfx, var, 0))   # MOVE→setter（pfx 重绑定到实体）
    op_line = f"{repo}.delete({var});" if info["is_delete"] else f"{repo}.save({var});"  # 丢返回（W-4/save）

    if info["mode"] == "plain":
        lines.append(op_line)
        return lines
    # error（W-3 选项②）：save/delete + 后续 包进 try；原错误段移入 catch
    out = lines + ["try {", "    " + op_line]
    out.extend(_render_rebound(info["try_tail"], env, pfx, var, 1))
    out.append("} catch (Exception e) {")
    out.extend(_render_rebound(info["then_stmts"], env, pfx, var, 1) or ["    // (空)"])
    out.append("}")
    return out


def rewrite_io_paras(paras: list[tuple], ctx, *, acc: NodeAccess,
                     render_body: Callable, make_raw: Callable) -> list[tuple]:
    """把 BEGN+NEXTR 自跳循环 / 单次 BEGN 等值定位 / 单条读 / 单条写 改写为高阶 Java（= 旧 _rewrite_begn_loops，零改）。

    路径中立（设计 §3.3）：节点字段读取经 acc；段体渲染经 render_body(stmts, indent)；命中段换 make_raw(lines)。
    旧路 acc=STMT_ACCESS、render_body=build_skeleton、make_raw=Stmt(kind=raw)；
    新路 acc=ASG_ACCESS、render_body=visitor 段体渲染、make_raw=nodes.Raw。"""
    env = _Env(acc=acc, ctx=ctx, render_body=render_body, make_raw=make_raw)
    norm = [(lbl or f"__ENTRY_{i}", list(stmts)) for i, (lbl, stmts) in enumerate(paras)]
    labels = [l for l, _ in norm]
    result = [(paras[i][0], norm[i][1]) for i in range(len(paras))]   # (原标签, stmts副本)
    changed = False

    # ── Pass 1：BEGN + NEXTR 自跳循环 ──────────────────────────────────
    for i, (lbl, stmts) in enumerate(norm):
        info = _match_begn_loop(lbl, stmts, env)
        if not info:
            continue
        next_lbl = labels[i + 1] if i + 1 < len(labels) else None
        if info["exit_label"] != next_lbl:
            continue                                   # 跳出目标须为相邻下一段，才能自然 fall-through
        if not any(_setup_has_begn(s, info["pfx"], env) for _, s in norm[:i]):
            continue                                   # 前序段须有 MOVE BEGN（确认是 BEGN 读）
        result[i] = (paras[i][0], [make_raw(_render_begn_foreach(info, env))])
        for k in range(i):                             # 剥除前序段里该 pfx 的 setup
            result[k] = (result[k][0], _strip_struct_setup(result[k][1], info["pfx"], env))
        changed = True

    # ── Pass 2：单次 BEGN 等值定位（同段内 setup + CALL + IF，无回跳）──
    for i, (_lbl, _stmts) in enumerate(norm):
        if _is_raw_para(result[i][1], acc):
            continue   # 已被 Pass 1 处理为循环
        current = result[i][1]                              # Pass 1 可能已剥离本段其他 pfx 的 setup
        info = _match_begn_single(current, env)             # 在已修改的列表上检测，索引与切分自洽
        if info:
            raw = make_raw(_render_begn_single(info, env))
            before = current[:info["setup_start"]]
            after  = current[info["call_idx"] + 2:]   # 跳过 CALL + IF
            result[i] = (paras[i][0], before + [raw] + after)
            changed = True
            continue
        # ── Pass 2b：单条读 READR/READS 等值定位（步骤10：setup + CALL + IF STATUZ）──
        rinfo = _match_readr_single(current, env)
        if rinfo:
            raw = make_raw(_render_readr_single(rinfo, env))
            before = current[:rinfo["setup_start"]]
            after  = current[rinfo["consume_to"]:]    # error 形态 consume_to=末尾，后续已并入 try
            result[i] = (paras[i][0], before + [raw] + after)
            changed = True
            continue
        # ── Pass 2c：单条写 IO（UPDAT/WRITE/DELET 等，步骤11）──
        winfo = _match_write_single(current, env)
        if winfo:
            raw = make_raw(_render_write_single(winfo, env))
            before = current[:winfo["setup_start"]]
            after  = current[winfo["consume_to"]:]    # error 形态 consume_to=末尾，后续已并入 try
            result[i] = (paras[i][0], before + [raw] + after)
            changed = True

    return result if changed else paras


def _is_raw_para(stmts: list, acc: NodeAccess) -> bool:
    """段体首节点是否为 raw（Pass 1 已改写为循环）—— 经 acc.kind 判 'raw'，两路通用。"""
    return bool(stmts) and acc.kind(stmts[0]) == "raw"
