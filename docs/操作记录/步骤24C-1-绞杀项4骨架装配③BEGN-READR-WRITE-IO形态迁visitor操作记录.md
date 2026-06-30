# 步骤24C-1 操作记录　绞杀项4 骨架装配③：BEGN/READR/WRITE IO 形态识别 + struct_rebind 迁 visitor

对应设计：`../详细设计/步骤24C-绞杀项4骨架装配③BEGN-READR-WRITE-IO形态迁visitor设计.md`（✅已认可，🟢24C-1 落地）。
日期：2026-06-26。范围：24C-1＝整族迁移 + 双路打通 + ASG `Raw`/`visit_Raw` + `--verb IO` 闸（比对先验四形态）。

---

## 1. 做了什么（按设计 §4 执行，零越界）

1. **新建 `translator/skel/io_rewrite.py`**（34 函数 / ~600 逻辑行）：把 rules `_rewrite_begn_loops` 一族
   （四形态匹配器 + 五渲染器 + 编排器 + 公共骨架）**原样迁址**，仅三处参数化使其路径中立：
   - 节点字段读取 → `NodeAccess` 5 访问器协议（`kind/tokens/children/else_children/whens`）+ `STMT_ACCESS`（旧路属性直读）；
   - 段体渲染 → `render_body(stmts, indent)` 回调；
   - raw 节点构造 → `make_raw(lines)` 回调。
   匹配/渲染逻辑零改；新增 `_Env` 把 acc/ctx/render_body/make_raw 打包单参穿过各函数。
2. **`translator/skel/__init__.py`** 门面导出 `rewrite_io_paras`/`NodeAccess`/`STMT_ACCESS`。
3. **`translator/rules.py`** 删 begn 族 ~680 行（行 123–800），`_rewrite_begn_loops` 改薄委托
   （注入 `STMT_ACCESS` / `build_skeleton` / `_raw_stmt`），`build_section` 调用点零改。rules 1103→337 行。
4. **`asg/nodes.py`** 新增 `Raw(lines)` 节点（纯叶子）。
5. **`asg/visitor.py`** 新增模块级 `_asg_kind/_asg_tokens/_asg_children/_asg_else/_asg_whens` + `ASG_ACCESS`；
   `visit_Section` 在 `render_flow_dispatch` **前**插入 `rewrite_io_paras`（ASG_ACCESS / `_render_para_body` / `nodes.Raw`）；
   新增 `visit_Raw`（吐 `.lines`）。
6. **`scripts/diff_asg_vs_legacy.py`** 扩 `--verb IO`：`_legacy_ios`/`_asg_ios`/`_io_snapshot`（复用 `_fill_legacy_leaves`，
   快照含 flow + struct_objects 复位，fresh ctx 隔离）。
7. **`test_translation.py`** 新增 `TestSkelIoRewrite`（3 条）+ `TestDiffAsgVsLegacyIo`（1 条）。
8. 回填设计 §7/§8、同步架构索引 `docs/架构索引/项目总览.md`（绞杀项4③ 条目 + skel/io_rewrite 行 +
   visitor 行 + asg/nodes Raw + 历史表 24C-1 行）。

---

## 2. 关键命令与校验（硬闸①②③全绿）

```bash
# ① 旧路径零回归
python -m unittest test_translation            # Ran 165 OK (skipped=2)   （迁前 161，+4 新测）

# ② config 快照零 diff（snapshot 仅含 config 层，与本刀解耦；before/after 经 git stash 取证）
python scripts/regress_config_snapshot.py > after.json
git stash push -- translator/rules.py asg/...; python scripts/regress_config_snapshot.py > before.json; git stash pop
diff before.json after.json                     # [ZERO-DIFF OK]  377 行

# ③ 比对闸（IO 样例：READR/WRITE/BEGN-foreach/单次 BEGN/扁平 5 段）
python scripts/diff_asg_vs_legacy.py <io_sample.cob> --verb IO    # [OK] 5 条 两路逐字符一致
# 回归其余 verb 仍 [OK]：
for v in MOVE IF FLOW CALL PERFORMCALL CONTROL ARITH; do diff_asg_vs_legacy ... --verb $v; done
```

**四形态确认吸收（防退化）**：
- ① BEGN+NEXTR → `List<SublRecord> sublList = sublRepository.findByChdrcoyBegn(wsaaCompany); for (SublRecord subl : sublList) { wsaaData = subl.getData(); }`
- ② 单次 BEGN → `List<SubsRecord> subsList = subsRepository.findByChdrcoyBegn(wsaaCompany); if (subsList.isEmpty()) {…}`
- ③ READR → `ElpoRecord elpo = elpoRepository.findByChdrcoyReadr(wsaaCompany); if (elpo != null) { wsaaData = elpo.getData(); }`
- ④ WRITR → `TmlcRecord tmlc = new TmlcRecord(); tmlc.setField(wsaaVal); tmlcRepository.save(tmlc);`

**rebind 一致性自证**：foreach/readr 体内 `subl.getData()`/`elpo.getData()`、write 体内 `tmlc.setField(wsaaVal)`
两路（旧两趟 `struct_rebind` 回填 / 新一趟 `ctx.struct_objects` 内联）逐字符一致；收尾 struct_objects 复位（快照不残留）。
→ 设计 §3.5 一致性论证成立。

---

## 3. 守界与未做（留 24C-2/3/4 与 24D）

- 24C-1 功能上四形态已全打通；24C-2/3/4 为逐形态**扩选样加固**（嵌套 IF/EVALUATE 体内 IO、STATUZ error 形
  try-catch、多键 finder、含过滤 IF 的 foreach），非补能力。
- ④ 程序级装配 + `body_context` 改吃 visitor + cutover 删旧 token 路径/rules 委托壳 → 24D（真·下线）。

---

## 4. Token 使用分析

- **主要消耗**：① 一次性精读 rules.py begn 族 ~680 行（123–800，分 3–4 段读）——本刀核心，迁址必读；
  ② `io_rewrite.py` 新文件整文件写出 ~600 行（单次 Write，不复读）；③ 比对调试 2–3 轮（dump 吸收体核对）。
- **量级**：中等偏上。大头是 begn 族源码精读 + 新文件写出，均为一次性、未反复全文重读（按设计先定位再迁）。
- **节流措施**：删除区间用 Python 一次性 splice（不逐行 Edit）；比对用脚本 dump 关键行（不全量回显）；
  config 快照只看 diff 结论行。
- **Context 状态**：本会话从设计 → 落地 → 校验 → 回填全程单会话，context 已偏多。**建议**：24C-2 起
  可 `/clear` 或新开会话，仅带「设计24C + 本操作记录」入场，避免 begn 族源码在后续轮次反复计费。
