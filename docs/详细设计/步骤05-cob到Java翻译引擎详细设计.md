# 步骤05 · cob → Java 翻译引擎详细设计（规范驱动）

状态：🟢 已实现（2026-06-03）
依据规范（正本）：`../../config/wsaa_translation_spec.yaml`（已认可）
配套配置：`../../config/type_mappings.yaml`（PIC→类型机器匹配）、`../../config/naming_conventions.yaml`（命名/COPY 角色）
概要索引：见 `../架构索引/项目总览.md`

> 三层职责定位：本文件属**代码实现层**——讲「如何根据规范把翻译代码写出来」（思路/方案/策略）。
> 规范本身（每种构造翻成什么）在 `wsaa_translation_spec.yaml`，不在此重述；知识在 `knowledge/`。

---

## 1. 背景与目标

规范正本已定稿。本步骤设计**翻译引擎的代码实现**：纯确定性、不调大模型，规范驱动
（加类型/构造尽量只改 config、不改引擎）。两条产线：

1. **骨架生成**：整个 cob → Java 调用骨架——主类 + 各 SECTION 方法签名 + `USING` 入参 +
   WS 容器引用 + COPY 依赖。**方法体内部逻辑本轮不译**（留后续步骤）。
2. **WS 容器翻译**：`WORKING-STORAGE` → `ZpoldwnmWsaa` 容器类（字段 + 视图 + 条件）。
   现有 `translator/wsaa/render_*` 已实现但**硬编码模板**，本轮**改造为读规范驱动**，
   并保证抽象化后产物与改造前一致（回归不变）。

## 2. 已确认的决定（固化，不再问）

1. 三层职责：config=规范模板正本、knowledge=模型知识库、详细设计=代码实现思路。
2. **全局变量策略**：WS → 普通容器类，**不静态全局、无单例**；每次调用 `new` 实例，
   作为上下文对象在各 SECTION 方法间**显式传参**；多线程每线程一实例（线程封闭）。
3. **SECTION 粒度**：主类 `Zpoldwnm` + 每个 SECTION 一个方法；`PERFORM` → 方法调用。
4. **COPY 角色**：`REC/SKM/KEY`→实体类、`VARCOM` 类→服务类、其余→常量。
5. **本轮范围**：骨架（方法空体）+ WS 容器完整翻译；SECTION 方法体翻译留后续。
6. **骨架引擎包名**：因同目录已有旧 `translator/skeleton.py`（graph 老链路 State/Facade，仍被
   main/graph/context/assemble/test 引用），Python 下 `skeleton.py` 与 `skeleton/` 包不可共存。
   故新骨架引擎包落为 **`translator/skeleton_gen/`**（文件职责仍按 §6.2），旧 `skeleton.py` 原样温存。
7. **SECTION 方法名**：复用既有 `translator/skeleton._section_to_method`（如 `1000-INITIALISE`→`initialise1000`），
   保留数字标号后缀以**避免重名/非法标识符**（规范 procedure_using 样例中的 `initialise` 为示意，
   实现以去重安全的既有规则为准，复用优先）。
8. **服务类命名**：规范未给 VARCOM 等服务拷贝簿的类名规则，约定 `class=PascalCase(名)+Service`、
   `field=camelCase(名)+Service`（如 VARCOM→`VarcomService varcomService`），写进产物可追溯。

## 3. 总体架构与数据流

```
拆解产物                    解析层(复用)              规范驱动渲染层              产物
─────────                  ──────────                ──────────────            ────
ZPOLDWNM.cob ──parse──► CobolProgram ─────────────► 骨架引擎 ───────────► Zpoldwnm.java
(主程序)                (program_id/using/             (skeleton/)            (主类骨架)
                         copy/sections/performs)
ZPOLDWNMWSAA.cob ─parse_ws─► WsNode 森林 ──────────► WS 渲染引擎 ────────► ZpoldwnmWsaa.java
(WS 块)                  (level/pic/occurs/            (wsaa/, 读 spec)       (容器类)
                          redefines/conditions)

config 规范三件套 ──spec_loader──► (两引擎共享，查询类型/初值/命名/COPY角色/视图样式)
```

**复用 vs 新增**：
- 复用：`parser/cobol_parser.parse()`（已提取全部骨架元数据）、`parser/ws`（WsNode 森林）、
  `translator/wsaa/render_*` + `storage.py`（改造，非重写）。
- 新增：`config/spec_loader.py`（规范访问层）、`translator/skeleton/`（骨架引擎包）、
  `scripts/translate_skeleton.py`（瘦入口）。

## 4. 输入与产物

**输入**
- 元数据：`cobol_parser.CobolProgram`（program_id、linkage_using、copy[]、sections[]+performs[]）。
- WS 细粒度：`parser/ws` 的 WsNode 森林（已 backfill 类型/宽度/维度）。
- 规范：`wsaa_translation_spec.yaml`（语义/目标类型/初值/视图签名）、`type_mappings.yaml`、`naming_conventions.yaml`。

**产物**
- `Zpoldwnm.java`：主类骨架。
- `ZpoldwnmWsaa.java`：WS 容器类。
- COPY 实体类**仅引用**（用作字段/参数类型名），本轮不生成实体类本体。

## 5. 规范如何驱动渲染（关键设计）

规则分两类，引擎分别消费，**边界如实声明**：

| 规则类型 | 例子 | 引擎怎么消费 | 加新东西要不要改代码 |
|---|---|---|---|
| **查表型** | 标量 PIC→类型、初值、命名、COPY 角色 | 读 config 数据字段 + 通用渲染函数装配 | **加类型只改 config，引擎零改动** |
| **算法型** | 组偏移、定宽切片、REDEFINES 视图、`_toDigits/_fromDigits`、二维下标 | 引擎按 spec 描述的语义实现算法函数；spec 只定语义+方法签名样式 | 加新的 REDEFINES 子类才加一个算法分支 |

- Java 语句的**样式串**（如 `private {type} {name}{init};`）集中为少量格式常量，
  避免散落在各 render 函数里硬编码。
- **诚实边界**：算法型（如 REDEFINES 双向视图）无法纯数据化，不假装全 config 化；
  规范负责「定义语义与签名」，引擎负责「实现算法」，两者一一对应、可追溯。

## 6. 模块设计（职责 + 调用关系；单文件逻辑行 ≈100，超则拆）

### 6.1 `config/spec_loader.py`（新增·规范访问层）
集中加载三件套并对外提供查询，引擎**不直接读 yaml**：
- `java_type_of(pic, comp)`：查 `type_mappings` 首命中 → Java 标量类型。
- `init_of(node)`：按 spec 初值规则 → 初值表达式（VALUE/SPACES/ZEROS/类型默认）。
- `field_name(cobol)` / `class_name(program)`：命名转换（复用 `variable_resolver`）。
- `copy_role(name)` → entity/service/constant；`entity_class(name)` → Java 类型名。
- `view_style(id)`：取某视图/构造的样式串（getter/setter 模板）。

### 6.2 `translator/skeleton/`（新增·骨架引擎包）
- `program_model.py`：从 `CobolProgram` 抽取骨架要素（program_id、using[]、section[]+performs、copy[]）。
- `copy_resolver.py`：调 `spec_loader.copy_role` 把 COPY 分为 实体/服务/常量，产出 import 与依赖字段。
- `render_skeleton.py`：装配主类——`package` + import + 字段（WS 容器引用、服务依赖）+
  入口方法（`USING`→入参）+ 每 SECTION 一个方法（**空体** + `// TODO 方法体待译` + `PERFORM`→调用注释）。
- `__init__.py`：`render_skeleton(program) -> str`。

### 6.3 `translator/wsaa/`（改造现有·WS 容器渲染）
职责不变，**渲染来源改为规范**：
- `render_field/condition/view`：类型/初值/命名/视图样式改为经 `spec_loader` 取，删除硬编码字符串。
- `storage.py`：定宽串/`_toDigits/_fromDigits`/偏移**算法保留**（算法型，不入 config）。
- `render_class.render_wsaa`：输出 `ZpoldwnmWsaa`——普通类、字段 `private`、视图方法、条件方法；**非 static**。

### 6.4 入口与调用链
- `scripts/translate_skeleton.py`（瘦入口）：`--program/--in/--out` → `parse → render_skeleton → 写文件`。
- `scripts/translate_wsaa.py`（已有）：`parse_ws → render_wsaa(读 spec_loader) → 写文件`。
- 调用链（单向无环）：
  ```
  translate_skeleton → cobol_parser.parse → skeleton(program_model→copy_resolver→render_skeleton) → Zpoldwnm.java
  translate_wsaa     → parse_ws → wsaa.render_wsaa ──┐
  两引擎 ── 共享 ──► config/spec_loader ◄────────────┘
  ```

## 7. 各构造渲染实现思路（对应规范节）

- **〇 骨架**（见 6.2）：program_id→类名；WS→容器引用字段；COPY 按角色→import/依赖/常量；
  USING→入参；每 SECTION→方法签名（带 `ZpoldwnmWsaa wsaa` 参数）+ 空体；PERFORM→调用 TODO。
- **一 标量**：`spec_loader.java_type_of + init_of` → `scalar_field` 样式装配（查表型，零代码改动加类型）。
- **二 聚合**：
  - 组：子项平铺 + `// ── 组名 ──`；组↔子项双向同步 = `storage` 偏移切片视图（算法型）。
  - OCCURS：维度由 `parser/ws tree.backfill` 累计 → 一维 `T[]` / 二维 `T[][]`；下标 i-1。
  - 88：`cond_values`→布尔方法；INDICATOR→带下标 `indOn/indOff`。
  - FILLER：不建字段，仅计偏移。
- **三 REDEFINES**：按子类分流到 `storage_accessor` + 视图方法（char_over_char / chars_over_numeric /
  numeric_over_char / target_missing→按主定义渲染）；in_occurs / malformed / comp3_backing → 保留 TODO。
- **四 TODO**：保留并带「原因」注释（不臆测）。
- **五 假设**：`signed_display_abs` / `cobol_move_align` 写进产物注释。

## 8. 全局变量策略的代码实现

- `ZpoldwnmWsaa`：普通类，无 `static`、无单例。
- 主类 `Zpoldwnm` 在入口方法内 `new ZpoldwnmWsaa()`，作为参数传入各 SECTION 方法：
  `void initialise(ZpoldwnmWsaa wsaa, AParams a, ...)`。
- 多线程：每次调用各自 `new`，线程封闭、无共享可变全局。
- 本轮骨架只生成「方法签名带 `wsaa` 参数 + 空体」，体内逻辑后续步骤翻译。

## 9. 自检 / 验证计划（实现后执行，结果回填 §10）

1. **规范加载**：`spec_loader` 能解析三件套；各查询接口返回正确（抽样 char/decimal/comp3/copy_role）。
2. **骨架产物** `Zpoldwnm.java`：主类名正确；每 SECTION 一个方法；`USING`→入参齐全；
   含 WS 容器字段 + 服务依赖；`PERFORM`→调用 TODO；花括号配平。
3. **WS 产物** `ZpoldwnmWsaa.java`：**与改造前回归一致**（抽象化不得改变产物）；
   抽样核对类型/视图/条件；`// TODO` 仍为 10（D13×4 + D14×6）。
4. 无 `javac` 环境则做结构 lint（括号配平、字段/方法去重、类型-初值匹配）。

## 10. 实现结果（已回填）

状态：🟢 已实现（2026-06-03）。

### 10.1 落地文件
- `config/spec_loader.py`：规范访问层。`java_type_of` / `init_of` / `field_name` / `class_name` /
  `copy_role` / `entity_class` / `service_class` / `service_field` + 样式常量 `FIELD_DECL`。
  命名复用 `parser.variable_resolver._cobol_to_java_name`、初值复用 `parser.ws.value.java_init`。
- `config/naming_conventions.yaml`：新增 `service_copybooks: [VARCOM]`（copy_role 判 service 的数据源）。
- `translator/skeleton_gen/`（包名见 §2-6）：`program_model.py`（CobolProgram→SkeletonModel）、
  `copy_resolver.py`（COPY 角色分流）、`render_skeleton.py`（主类装配）、`__init__.py`（暴露 render_skeleton）。
- `translator/wsaa/render_field.py`：类型/初值/命名/样式串改经 spec_loader（删除硬编码 `_DEFAULTS` 与格式串）。
- `translator/wsaa/render_class.py`：`_class_base` → `spec_loader.class_name`，解耦旧 skeleton.py。
- `scripts/translate_skeleton.py`：瘦入口（`--in/--out`）。

### 10.2 自检结果（§9）
1. ✅ 规范加载：spec_loader 三件套查询正确（char/decimal/comp3 类型、VARCOM→service、LETCMNTSKM→LetcmntParams）。
2. ✅ 骨架产物 `Zpoldwnm.java`：主类名正确；151 个 SECTION 方法（名唯一、无数字开头非法标识符）；
   `USING LETCMNT-PARAMS`→入参；入口方法内 `new ZpoldwnmWsaa()`；299 条 `PERFORM`→调用注释；
   花括号配平 153/153；重复段（`!!!!!!` 停用的 `B320-INCSUM-INF`）去重为注释。
3. ✅ WS 产物 `ZpoldwnmWsaa.java`：与改造前 **逐字节回归一致**（`diff` 为空）；`// TODO` 仍为 10。
4. ✅ 结构 lint（无 javac 环境）：括号配平、方法去重、字段类型-初值匹配均通过。

### 10.3 已知事项（上游，非本引擎缺陷）
- `parser/cobol_parser._strip_cobol_line` 按标准固定格式取 `raw[7:]`（列8起为代码区）。本源文件
  存在首列布局偏移行，如 `  100-MAIN SECTION.` 的段名 `MAIN` 起于第 7 列（指示符列），首字母被吞 → `AIN`，
  约 11 个段名受影响。该 parser 被 graph(`pipeline.py`)/`variable_resolver` 共用，修复超出本步骤范围，
  列为独立后续；本步骤骨架引擎对「解析器给定的段名」忠实渲染，逻辑无误。
  > 更新（2026-06-03）：已由**步骤06**修复（`parser/cobol_columns.py` 列处理单一正本）；
  > 修复后骨架段数 151→133、`AIN`→`main`、停用段消失。详见 `步骤06-COBOL解析器列对齐与停用行修复设计.md`。
