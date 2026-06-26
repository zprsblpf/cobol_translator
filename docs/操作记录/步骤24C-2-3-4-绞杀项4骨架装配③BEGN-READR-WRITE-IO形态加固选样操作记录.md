# 步骤24C-2/3/4 操作记录　绞杀项4 骨架装配③：BEGN/READR/WRITE IO 形态加固选样验证

对应设计：`../详细设计/步骤24C-绞杀项4骨架装配③BEGN-READR-WRITE-IO形态迁visitor设计.md` §9（✅已认可，🟢已落地）。
日期：2026-06-26。范围：24C-2/3/4 合并执行 = 逐形态扩**边角样本**，两路（`STMT_ACCESS`/`ASG_ACCESS`）逐字符比对加固。
**纯加测试，无生产代码改动**。

## 1. 做了什么

承 24C-1（整族迁 `skel/io_rewrite.py` + 双路打通 + 四形态**基本形**比对全绿）。本步只验 24C-1 比对闸**未触达**的
已有分支（多键 finder `And`-join / error 形 try-catch / READS 变体 / UPDAT 复用 / DELET / 吸收体 body 内嵌套 IF
含 else），确认两路逐字符一致。

`test_translation.py::TestDiffAsgVsLegacyIo` 新增：
- `HEADER`/`ERRSEC` 公共夹具 + `_run_pair` 助手（跑 `_legacy_ios`/`_asg_ios` 两路，断言 `(吸收体, flow+struct 复位快照)`
  逐字符/逐项一致 + flow 复位；返回 `{section: lines}` 供逐段防退化）。
- `test_24c2_begn_single_multikey`（形态②多键）、`test_24c3_readr_error_reads_multikey_nested`（形态③ error/READS/多键/嵌套 IF）、
  `test_24c4_write_updat_reuse_delet_error`（形态④ UPDAT 复用/DELET/write error）。

## 2. 执行中两处定位

1. **夹具 bug（多键 IF 截断）**：长 IF 条件单行超 COBOL 固定格式第 72 列被解析器截断（tokens 停在 `'O'`）→ 多键匹配器
   收到截断条件返回 None。**修法**：拆续行（解析器拼接续行 → `[(CHDRCOY,…),(CHDRNUM,…)]`）。非代码 bug。
2. **错误断言**：初版 `_run_pair` 加 `snap[2]==()`（struct_objects 空）过严——收尾合法保留 `pfx→Params` 绑定，
   非泄漏。撤回，沿 24C-1 仅校验 `snap[0]/snap[1]` 复位；IO 临时 record/loop 重绑定复位由两路快照全等覆盖。

## 3. 校验（硬闸三项）

```bash
# ① 全量 unittest
python -m unittest test_translation                 # Ran 168 OK (skipped=2)  ← 基线 165 +3
# ② config 快照（生产路径零改动 → 零 diff 由构造保证）
python scripts/regress_config_snapshot.py | wc -l   # 377 行
# ③ inline 比对（unittest 内 TestDiffAsgVsLegacy* 全动词通过）+ CLI 全量回归
for v in MOVE CALL CONTROL PERFORMCALL; do
  python scripts/diff_asg_vs_legacy.py scripts/spike_proleap/cleaned_ZPOLDWNM.cob --verb $v
done                                                 # 全 [OK]（2953/247/357/271 条逐字符一致）
```

- ① `Ran 168 OK (skipped=2)`；3 新夹具 + 24C-1 `test_legacy_equals_asg_io` 全绿。
- ② 快照 377 行；本步零生产代码改动。
- ③ inline 全动词比对通过；CLI MOVE/CALL/CONTROL/PERFORMCALL 全量 `[OK]`。
- 防退化命中：`findByChdrcoyAndChdrnumBegn`/`findByItemkeyReadr`+`try{}/catch`/`findByChdrcoyAndChdrnumReads`/
  `elpo.getData()`（嵌套 IF rebind）/`tmlclstRepository.save` 无 `new`（UPDAT）/`tmlclstRepository.delete`/
  `new TmlclstRecord()`+`try{save}/catch`（write error）。

## 4. 两处发现（超 24C 守界，留 24D）

1. **体内嵌套未译复合语句两路 stub 文本分歧**：含 STRING 的 IF / 体内 EVALUATE / 数组下标等**无法翻译**的构造，
   旧路渲染 `// TODO-LEAF: …`、新路 `// TODO-IF/EVALUATE: …`。两路都未译，仅 stub 标记不同；根因 = 两种
   `render_body` 模型（旧两趟叶子占位 / 新一趟 visitor 递归）差异，非 ASG_ACCESS、非 IO 吸收、非 flow 逻辑错误。
2. **全量真实程序广度辅证**：CLI `--verb IO` 跑 `cleaned_ZPOLDWNM.cob` 112 段失败，`--verb FLOW` 同样 112 段失败，
   **失败段集合逐段完全相同** → **IO 吸收层零新增分歧**（IO 透明），112 处即发现①。为 24C-1 working-tree 既有状态
   （24C-1 仅跑 inline 样本），**非本步引入**。**留 24D**：cutover 前统一未译构造 TODO stub 口径，使全量 IO/FLOW 收敛。

**结论**：24C-2/3/4 目标达成——IO 吸收**边角形态**六类两路逐字符一致，真实程序 IO 吸收层零新增分歧。
剩余全量收敛属 flow/leaf 层未译构造 stub 统一，归 24D。

## Token 使用分析

- **主要消耗**：① 精读 `io_rewrite.py`（匹配器/渲染器 ~5 段，定位各边角触发分支，必读）；② 调试迭代 2 轮
  （夹具 72 列截断 + `snap[2]` 过严断言，各一次直接探查脚本定位）；③ 全量 ZPOLDWNM 比对产物一次较大（227KB 已转存
  文件、未全量回显，仅提取失败段集合/最小段行级 diff）。
- **量级**：中等。无大文件全文读（均 grep/精读定位）；真实程序大产物落盘不回显，控制了回显成本。
- **Context**：本会话从 24C 设计探查起，叠加 io_rewrite 精读 + 调试 + 回填，**context 已偏中高**；如继续叠 24D 大任务，
  建议先 `/clear` 再开新会话。
