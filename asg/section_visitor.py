"""
相3 ASG 骨架装配 visitor（步骤24 草案落地）。

用途：旁路渲染 ASG Section/Paragraph，把 rules.build_section 的 paragraph 装配、
状态机壳、flow dispatch 与 PERFORM out-of-line 目标解析迁入 visitor 自证。
对应设计：docs/详细设计/步骤24-骨架装配迁visitor设计.md。

设计思路：
- 叶子/语句壳继续复用 LeafJavaVisitor 与 translator.leaf 公用译器。
- flow_label/flow_paragraphs 属骨架装配态，只保存在本 visitor 实例，不扩 LeafCtx。
- pending_range_methods 仍写旧契约 [(label, body_lines), ...]，让 body_context 现有 drain 逻辑零改复用。
"""
from __future__ import annotations

from config import grammar_loader, spec_loader
from asg import nodes
from asg.visitor import LeafJavaVisitor
from asg.structure_rewrite import rewrite_structures, tag_rebind_nodes
from translator.leaf import translate_perform_loop
from translator.leaf.call import resolve_io_info
from translator.leaf.cond import translate_condition
from translator.leaf.control import is_goto_depending
from translator.leaf.expr import _java, _operand, _pascal


def _ind(n: int) -> str:
    return "    " * n


def _indent_lines(lines: list[str], indent: int) -> list[str]:
    return [(_ind(indent) + line if line else line) for line in lines]


class SectionJavaVisitor(LeafJavaVisitor):
    """ASG Section/Paragraph 渲染器。

    它补齐 LeafJavaVisitor 不负责的骨架装配：paragraph 顺序、状态机、PERFORM 目标调用。
    旧主线仍由 rules.build_section 负责；本类用于旁路比对和后续切主线的基座。
    """

    def __init__(self, ctx, force_sm: bool = False):
        super().__init__(ctx)
        self.force_sm = force_sm
        self.flow_label: str | None = None
        self.flow_paragraphs: set[str] = set()

    def render_section(self, section: nodes.Section, indent: int = 0) -> list[str]:
        """渲染单个 Section 节点，对齐 rules.build_section 的输出层级。"""
        return self.render_paragraphs(section.paragraphs, indent=indent)

    def render_paragraphs(self, paragraphs: list[nodes.Paragraph], indent: int = 0) -> list[str]:
        """渲染 [(label, stmts)]，按内部 GO TO 决定扁平拼接或状态机降级。"""
        paragraphs = rewrite_structures(paragraphs, self.ctx)
        norm: list[tuple[str, nodes.Paragraph]] = [
            (p.label or f"__ENTRY_{i}", p) for i, p in enumerate(paragraphs)
        ]
        labels = [label for label, _p in norm]
        label_index = {label: i for i, label in enumerate(labels)}

        has_jump = False
        for i, (_label, para) in enumerate(norm):
            for target in self._collect_gotos(para.stmts):
                j = label_index.get(target)
                if j is not None and (self.force_sm or j <= i):
                    has_jump = True
                    break
            if has_jump:
                break

        if not has_jump or not grammar_loader.back_edge_state_machine():
            saved = self._push_flow(None, set())
            try:
                out: list[str] = []
                for label, para in norm:
                    if not label.startswith("__ENTRY_"):
                        out.append(f"{_ind(indent)}// paragraph {label}")
                    out.extend(_indent_lines(self._render_stmts(para.stmts), indent))
                return out
            finally:
                self._pop_flow(saved)

        saved = self._push_flow("FLOW", set(labels))
        try:
            out = [
                f'{_ind(indent)}String __pc = "{labels[0]}";   // 段内 GO TO 回跳 → 状态机',
                f"{_ind(indent)}FLOW: while (true) {{",
                f"{_ind(indent + 1)}switch (__pc) {{",
            ]
            for i, (label, para) in enumerate(norm):
                out.append(f'{_ind(indent + 1)}case "{label}": {{')
                out.extend(_indent_lines(self._render_stmts(para.stmts), indent + 2))
                if not self._ends_with_transfer(para.stmts):
                    if i + 1 < len(norm):
                        out.append(f'{_ind(indent + 2)}__pc = "{labels[i + 1]}"; continue FLOW;  // fall-through')
                    else:
                        out.append(f"{_ind(indent + 2)}break FLOW;")
                out.append(f"{_ind(indent + 1)}}}")
            out.append(f"{_ind(indent + 1)}default: break FLOW;")
            out.append(f"{_ind(indent + 1)}}}")
            out.append(f"{_ind(indent)}}}")
            return out
        finally:
            self._pop_flow(saved)

    def _render_stmts(self, stmts: list) -> list[str]:
        out: list[str] = []
        for stmt in stmts:
            out.extend(self.visit(stmt))
        return out

    def _push_flow(self, label: str | None, paragraphs: set[str]):
        saved = (self.flow_label, set(self.flow_paragraphs))
        self.flow_label = label
        self.flow_paragraphs = set(paragraphs)
        return saved

    def _pop_flow(self, saved) -> None:
        self.flow_label, self.flow_paragraphs = saved

    def visit_GotoStmt(self, node) -> list[str]:
        """flow 模式内的 GO TO 内部 paragraph 走状态机；其它复用步骤23 控制叶子译器。"""
        target = self._goto_target(node)
        if target and self.flow_label and target in self.flow_paragraphs:
            return [f'__pc = "{target}"; continue {self.flow_label};  // GO TO {target}']
        return super().visit_GotoStmt(node)

    def visit_Leaf(self, node) -> list[str]:
        """flow 模式内 EXIT 退出状态机；其它叶子仍走已迁 leaf 译器。"""
        first = node.tokens[0].upper() if node.tokens else ""
        if first == "EXIT" and self.flow_label:
            return [f"break {self.flow_label};  // EXIT"]
        return super().visit_Leaf(node)

    def visit_PerformStmt(self, node) -> list[str]:
        """PERFORM 渲染：循环壳复用 leaf.loop，out-of-line 目标解析迁入本骨架 visitor。"""
        loop = translate_perform_loop(node.header, self.ctx, 0)
        if loop is None:
            return [f"// TODO-PERFORM: {node.raw}"]
        open_lines, close_lines = loop
        if node.inline_body:
            body = _indent_lines(self._render_stmts(node.inline_body), len(open_lines))
        elif node.target:
            body = self._perform_target(node, len(open_lines))
        else:
            return [f"// TODO-PERFORM: {node.raw}"]
        return (open_lines + body + close_lines) if open_lines else body

    def visit_BegnForeachStmt(self, node) -> list[str]:
        """渲染 BEGN+NEXTR 结构吸收节点，对齐旧 _render_begn_foreach。"""
        pfx, name = node.pfx, node.name
        io = resolve_io_info(name, self.ctx.io_programs, self.ctx.io_default_pattern)
        repo = io["field_name"] if io else _java(pfx) + "Repository"
        rec_cls = _pascal(pfx) + "Record"
        loop_var = _java(pfx)
        list_var = loop_var + "List"
        finder = "findBy" + "And".join(_pascal(k) for k, _ in node.keys) + "Begn"
        vals = ", ".join(_operand(v, self.ctx) for _k, v in node.keys)
        lines = [
            f"List<{rec_cls}> {list_var} = {repo}.{finder}({vals});",
            f"for ({rec_cls} {loop_var} : {list_var}) {{",
        ]

        rebind = {pfx: loop_var}
        tag_rebind_nodes(node.filters + node.body, rebind)
        saved = self.ctx.struct_objects.get(pfx)
        self.ctx.struct_objects[pfx] = loop_var
        try:
            for filt in node.filters:
                cond = translate_condition(filt.cond, self.ctx)
                lines.append(f"    if ({cond}) {{ continue; }}" if cond
                             else f"    // TODO 过滤条件: {' '.join(filt.cond)}")
            for stmt in node.body:
                for line in self.visit(stmt):
                    lines.append("    " + line)
        finally:
            if saved is None:
                self.ctx.struct_objects.pop(pfx, None)
            else:
                self.ctx.struct_objects[pfx] = saved
        lines.append("}")
        return lines

    def visit_BegnSingleStmt(self, node) -> list[str]:
        """渲染单次 BEGN 等值定位，对齐旧 _render_begn_single。"""
        pfx, name = node.pfx, node.name
        io = resolve_io_info(name, self.ctx.io_programs, self.ctx.io_default_pattern)
        repo = io["field_name"] if io else _java(pfx) + "Repository"
        rec_cls = _pascal(pfx) + "Record"
        list_var = _java(pfx) + "List"
        finder = "findBy" + "And".join(_pascal(k) for k, _ in node.keys) + "Begn"
        vals = ", ".join(_operand(v, self.ctx) for _k, v in node.keys)

        lines = [f"List<{rec_cls}> {list_var} = {repo}.{finder}({vals});"]
        then_lines: list[str] = []
        for stmt in node.then_body:
            for line in self.visit(stmt):
                then_lines.append("    " + line)
        if then_lines:
            lines.append(f"if ({list_var}.isEmpty()) {{")
            lines.extend(then_lines)
            lines.append("}")
        return lines

    def visit_IoReadSingleStmt(self, node) -> list[str]:
        """渲染 READR/READS 单条读，对齐旧 _render_readr_single。"""
        pfx, name, func = node.pfx, node.name, node.func
        io = resolve_io_info(name, self.ctx.io_programs, self.ctx.io_default_pattern)
        repo = io["field_name"] if io else _java(pfx) + "Repository"
        rec_cls = _pascal(pfx) + "Record"
        var = _java(pfx)
        raw_op = (self.ctx.io_programs.get(name) or {}).get("operations", {}).get(func)
        finder = (raw_op.split("(", 1)[0] if raw_op
                  else "findBy" + "And".join(_pascal(k) for k, _ in node.keys) + func.capitalize())
        vals = ", ".join(_operand(v, self.ctx) for _k, v in node.keys)
        call_line = f"{rec_cls} {var} = {repo}.{finder}({vals});"

        if node.mode == "plain":
            return [call_line]
        rebind = {pfx: var}
        if node.mode == "error":
            out = ["try {", "    " + call_line]
            out.extend(self._render_rebound_body(node.try_tail, rebind, 1))
            out.append("} catch (Exception e) {")
            out.extend(self._render_rebound_body(node.then_body, rebind, 1) or ["    // (空)"])
            out.append("}")
            return out

        cmp = "!= null" if node.mode == "ok" else "== null"
        out = [call_line, f"if ({var} {cmp}) {{"]
        out.extend(self._render_rebound_body(node.then_body, rebind, 1) or ["    // (空)"])
        if node.else_body:
            out.append("} else {")
            out.extend(self._render_rebound_body(node.else_body, rebind, 1))
        out.append("}")
        return out

    def visit_IoWriteSingleStmt(self, node) -> list[str]:
        """Render UPDAT/WRITR/DELET single write IO absorbed by structure_rewrite."""
        pfx, name = node.pfx, node.name
        io = resolve_io_info(name, self.ctx.io_programs, self.ctx.io_default_pattern)
        repo = io["field_name"] if io else _java(pfx) + "Repository"
        rec_cls = _pascal(pfx) + "Record"
        var = _java(pfx)
        rebind = {pfx: var}

        lines: list[str] = []
        if node.is_new:
            lines.append(f"{rec_cls} {var} = new {rec_cls}();")
        lines.extend(self._render_rebound_body(node.setters, rebind, 0))
        op_line = f"{repo}.delete({var});" if node.is_delete else f"{repo}.save({var});"

        if node.mode == "plain":
            lines.append(op_line)
            return lines

        out = lines + ["try {", "    " + op_line]
        out.extend(self._render_rebound_body(node.try_tail, rebind, 1))
        out.append("} catch (Exception e) {")
        out.extend(self._render_rebound_body(node.then_body, rebind, 1) or ["    // (空)"])
        out.append("}")
        return out

    def _render_rebound_body(self, stmts: list, rebind: dict, indent: int) -> list[str]:
        tag_rebind_nodes(stmts, rebind)
        saved = {pfx: self.ctx.struct_objects.get(pfx) for pfx in rebind}
        self.ctx.struct_objects.update(rebind)
        out: list[str] = []
        try:
            for stmt in stmts:
                for line in self.visit(stmt):
                    out.append(_ind(indent) + line)
            return out
        finally:
            for pfx, old in saved.items():
                if old is None:
                    self.ctx.struct_objects.pop(pfx, None)
                else:
                    self.ctx.struct_objects[pfx] = old

    def _perform_target(self, node: nodes.PerformStmt, indent: int) -> list[str]:
        target = node.target.name if node.target else ""
        header = list(node.header)
        hu = [h.upper() for h in header]
        ti = next((i for i, t in enumerate(hu) if t in ("THRU", "THROUGH")), -1)
        if ti < 0 or ti + 1 >= len(header):
            return self._perform_single(target, indent)

        a, b = target, header[ti + 1].upper()
        order = self.ctx.section_order
        if a in order and b in order and order.index(b) >= order.index(a):
            rng = order[order.index(a): order.index(b) + 1]
            if len(rng) == 1:
                return [_ind(indent) + self._proc_call(a)]
            out = [f"{_ind(indent)}// PERFORM {a} THRU {b}（步骤12 §2：THRU 跨段，按段顺序展开 {len(rng)} 段）"]
            out.extend(_ind(indent) + self._proc_call(s) for s in rng)
            return out

        pr = self._perform_range_paragraph(a, b, indent)
        if pr is not None:
            return pr
        return [f"{_ind(indent)}// TODO PERFORM {a} THRU {b}：THRU 端点非已知过程单元或区间无法确定，"
                f"中间段/B 段可能漏翻，需人工核对（步骤12 §2 P-1③ / 步骤13 §2.2）",
                _ind(indent) + self._proc_call(a)]

    def _perform_single(self, target: str, indent: int) -> list[str]:
        call = _ind(indent) + self._proc_call(target)
        if target in self.ctx.known_sections:
            return [call]
        order = getattr(self.ctx, "proc_order", None) or []
        units = [u for u in order if u[0] == target and u[1] == "paragraph"]
        mname = self.ctx.section_to_method(target)
        section_methods = {self.ctx.section_to_method(s) for s in self.ctx.known_sections}
        if len(units) == 1 and mname not in section_methods:
            if mname not in self.ctx.pending_range_methods:
                self.ctx.pending_range_methods[mname] = [(target, units[0][3])]
            return [call]
        return [f"{_ind(indent)}// TODO 单条 PERFORM {target}：未解析到唯一过程单元（不在 proc_order/重名/撞 SECTION 方法名），"
                f"调用目标可能不存在，需人工核对（步骤15 §2.1 兜不住保守，不臆造）", call]

    def _perform_range_paragraph(self, a: str, b: str, indent: int) -> list[str] | None:
        order = getattr(self.ctx, "proc_order", None) or []
        if not order:
            return None
        names = [u[0] for u in order]
        if names.count(a) != 1 or names.count(b) != 1:
            return None
        ia, ib = names.index(a), names.index(b)
        if ib <= ia:
            return None
        rng = order[ia: ib + 1]
        if any(not u[0] for u in rng):
            return None
        mname = spec_loader.perform_range_method(self.ctx.section_to_method(a), self.ctx.section_to_method(b))
        if mname not in self.ctx.pending_range_methods:
            self.ctx.pending_range_methods[mname] = [(u[0], u[3]) for u in rng]
        return [f"{_ind(indent)}// PERFORM {a} THRU {b}（步骤13 §2.3 路线b：合成区间方法，{len(rng)} 单元）",
                f"{_ind(indent)}this.{mname}();"]

    def _proc_call(self, target: str) -> str:
        return f"this.{self.ctx.section_to_method(target)}();"

    def _goto_target(self, node) -> str | None:
        if is_goto_depending(getattr(node, "tokens", None) or []):
            return None
        if isinstance(node, nodes.GotoStmt) and node.target:
            return node.target.name
        toks = getattr(node, "tokens", None) or []
        for tok in toks:
            if tok.upper() not in ("GO", "TO"):
                return tok.upper()
        return None

    def _collect_gotos(self, stmts: list) -> list[str]:
        out: list[str] = []
        for stmt in stmts:
            target = self._goto_target(stmt)
            if target:
                out.append(target)
            if isinstance(stmt, nodes.IfStmt):
                out.extend(self._collect_gotos(stmt.then))
                out.extend(self._collect_gotos(stmt.els))
            elif isinstance(stmt, nodes.EvaluateStmt):
                for _cond, body in stmt.whens:
                    out.extend(self._collect_gotos(body))
            elif isinstance(stmt, nodes.PerformStmt):
                out.extend(self._collect_gotos(stmt.inline_body))
            elif isinstance(stmt, nodes.BegnForeachStmt):
                out.extend(self._collect_gotos(stmt.filters))
                out.extend(self._collect_gotos(stmt.body))
            elif isinstance(stmt, nodes.BegnSingleStmt):
                out.extend(self._collect_gotos(stmt.then_body))
            elif isinstance(stmt, nodes.IoReadSingleStmt):
                out.extend(self._collect_gotos(stmt.then_body))
                out.extend(self._collect_gotos(stmt.else_body))
                out.extend(self._collect_gotos(stmt.try_tail))
            elif isinstance(stmt, nodes.IoWriteSingleStmt):
                out.extend(self._collect_gotos(stmt.setters))
                out.extend(self._collect_gotos(stmt.then_body))
                out.extend(self._collect_gotos(stmt.try_tail))
        return out

    def _ends_with_transfer(self, stmts: list) -> bool:
        if not stmts:
            return False
        last = stmts[-1]
        if isinstance(last, nodes.GotoStmt):
            return True
        toks = getattr(last, "tokens", None) or []
        return bool(toks and toks[0].upper() in {"GO", "EXIT", "GOBACK", "STOP"})
