# 详细设计 · 步骤二：补 `db/mongo_client.py` 入库实现 + 调整拆解输出目录

> 状态：🟢已实现（2026-05-31；操作记录见 `docs/操作记录/步骤02-入库实现与包化拆分操作记录.md`）
> 对应上游：`docs/详细设计/步骤01-拆解与存库设计.md`（✅已认可，§6 已定 MongoDB 写入设计）
> 触发：步骤一操作记录把 `db/mongo_client.py` 列为已保留脚本，但实际从未创建；
> `scripts/decompose.py:import_mongo()` 调用的 `from db.mongo_client import MongoStore` 因此会失败。
> 同时用户要求调整拆解输出的目录布局。

---

## 1. 目标（本步只做这三件，不翻译、不改拆解规则）

1. **补 `db/mongo_client.py`（+ `db/__init__.py`）**：实现 `decompose.py` 已经在调用、
   但当前缺失的 `MongoStore` 封装，使「`--mongo-uri` 入库 / `--import-only` 补入库」真正可用。
2. **调整拆解输出目录布局**：切片放进 `拆解/` 子目录，两个 manifest 提到 `拆解/` 外面。
3. **按全局约定 §17 把超大的 `scripts/decompose.py`（494 行）拆成功能包 `decompose/` + 瘦入口**，
   每个 `.py` 逻辑行 ≈100 以内、各司一职。**拆分只搬运、不改逻辑**（同一函数原样迁移）。

## 2. 已确认的决定（来自用户）

### 2.1 新输出布局
程序名提到外层，`拆解/` 仅放切片，汇总文件在 `拆解/` 外：
```
/home/zp/Documents/cob/<PROGRAM>/        ← --out 指向这里（程序目录）
├── 拆解/                                  ← 仅放拆解后的切片 .cob
│   ├── 001-1000-INITIALISE.cob
│   ├── …（133 个 SECTION 切片）
│   └── ZPOLDWNMWSAA.cob                   ← WORKING-STORAGE 参数块
├── manifest.json                          ← 汇总（入库数据源），在 拆解/ 外
└── manifest.md                            ← 汇总（人读清单），在 拆解/ 外
```
对比旧布局（全部平铺在 `/home/zp/Documents/cob/拆解/ZPOLDWNM/`）：程序目录上移、切片下沉到 `拆解/`、manifest 留在程序目录根。

### 2.2 其它固化决定
- manifest 结构**不变**：`sections[].file` 仍存**裸文件名**（如 `1000-INITIALISE.cob`），不引入绝对路径。
  切片实际落在 `拆解/` 子目录，由读取方（verify）用「程序目录 + `拆解/` + file」拼接定位。
- 切片子目录名固定为 `拆解`，在 `decompose.py` 与 `verify_decompose.py` 各定义常量 `SLICE_SUBDIR = "拆解"`，避免硬编码散落。
- MongoDB：库 `cobol`，集合按程序名（如 `ZPOLDWNM`），唯一键 `(program, block_name)` —— 沿用步骤一 §6。
- **不内置连接串**（规范 §8）：`--mongo-uri` 缺省时不入库；入库须由用户显式提供连接串。
- 重跑拆解只刷新结构字段，**不覆盖** `params_in/params_out/calls/logic/java_code` 等步骤二+回填的分析字段。

## 2b. 包结构与文件关系（全局约定 §17）

把 `scripts/decompose.py` 的逻辑按职责下沉到项目根的新包 `decompose/`（与现有 `parser/ translator/ graph/` 同级），
`scripts/decompose.py` 退化为**瘦入口**（只解析参数 + 调用，不含业务逻辑）。`db/` 为数据访问层，独立包。

### 2b.1 目录与每个文件的职责

```
decompose/                       ← 新建：拆解功能包（纯逻辑，无 argparse）
├── __init__.py                  包标识 + docstring；可重导出 decompose、import_mongo 方便外部调用
├── models.py        (~20 行)    @dataclass Block —— 唯一数据结构
├── lines.py         (~50 行)    行级处理：is_deactivated/is_comment/indicator/clean_line/clean_block/_effective + _CHANGE_TAG_RE
├── structure.py     (~70 行)    结构定位：read_raw_lines/locate_divisions/extract_copies/classify_copies + _COPY_RE
├── blocks.py        (~70 行)    构块：extract_sections/build_ws_block/build_meta_block/slug_filename + _SECTION_RE/_NON_PROC_SECTIONS
├── manifest.py      (~70 行)    写文件+清单：write_files/_render_manifest_md/_doc（含 SLICE_SUBDIR="拆解"）
├── importer.py      (~25 行)    入库编排：import_mongo（调用 db.mongo_client.MongoStore）
└── core.py          (~25 行)    顶层编排：decompose()（串起 structure→blocks→manifest）

db/                              ← 新建：数据访问层（Block A）
├── __init__.py                  包标识 + docstring
└── mongo_client.py  (~60 行)    class MongoStore（pymongo 惰性导入）

scripts/decompose.py (~35 行)    ← 瘦入口：argparse + 调用 decompose.core / decompose.importer
scripts/verify_decompose.py      ← 校验脚本（Block C，仅改切片读取路径 + docstring）
```

### 2b.2 调用关系（数据流）

```
scripts/decompose.py (main, argparse)
   │  拆解模式
   ├─→ decompose.core.decompose(cob_path, program, out_dir)
   │        ├─→ structure.read_raw_lines / locate_divisions / extract_copies / classify_copies
   │        │        └─(用)→ lines.*           （行级清洗/有效行判定）
   │        ├─→ blocks.extract_sections / build_ws_block / build_meta_block
   │        │        └─(用)→ lines.clean_block / models.Block
   │        └─→ manifest.write_files(blocks, meta, ws, out_dir)
   │                 └─ 写 out_dir/拆解/*.cob + out_dir/manifest.json + manifest.md
   │  入库模式(--mongo-uri)
   └─→ decompose.importer.import_mongo(manifest_path, uri, db, coll)
            └─→ db.mongo_client.MongoStore(...)  → ensure_unique_index / upsert / count / close
```

依赖方向单向、无环：`models ← lines ← {structure, blocks} ← {manifest, core}`；`importer → db.mongo_client`；入口只依赖 `core`/`importer`。

### 2b.3 函数 → 文件归属对照（来自现 `scripts/decompose.py`，逐一搬运不改逻辑）

| 现位置(行) | 函数/常量 | 迁往 |
|---|---|---|
| 41-59 | `Block` | `decompose/models.py` |
| 64 / 74-116,129-136 | `_CHANGE_TAG_RE`, `is_deactivated/is_comment/indicator/clean_line/clean_block/_effective` | `decompose/lines.py` |
| 65-66,69-71 | `_SECTION_RE`,`_NON_PROC_SECTIONS` | `decompose/blocks.py` |
| 66 | `_COPY_RE` | `decompose/structure.py` |
| 121-124,139-214 | `read_raw_lines/locate_divisions/extract_copies/classify_copies` | `decompose/structure.py` |
| 217-305 | `extract_sections/build_ws_block/build_meta_block/slug_filename` | `decompose/blocks.py` |
| 308-396 | `_doc/write_files/_render_manifest_md` | `decompose/manifest.py` |
| 401-428 | `import_mongo` | `decompose/importer.py` |
| 433-457 | `decompose` | `decompose/core.py` |
| 460-494 | `main` | `scripts/decompose.py`（瘦入口） |

> 入口与脚本跨包导入：沿用现有模式 `sys.path.insert(0, <项目根>)` 后 `from decompose.core import decompose`、
> `from decompose.importer import import_mongo`（`importer` 内部再 `from db.mongo_client import MongoStore`）。

---

## 3. Block A：`db/mongo_client.py`（新建）

### 3.1 `db/__init__.py`
包标识文件，仅写模块用途 docstring（标明这是 MongoDB 访问层）。

### 3.2 `class MongoStore`
对 MongoDB 的薄封装，**严格按 `decompose.py:import_mongo()` 既有调用点实现 5 个方法**（复用优先，不多造接口；签名/返回值与调用点逐一核对过真实源码）。
pymongo **惰性导入**：仅在构造 `MongoStore` 时 `import pymongo`，纯文件模式（不入库）零依赖。

调用点（真实源码，`scripts/decompose.py` 401-428）：
```python
store = MongoStore(uri=uri, db_name=db)
store.ensure_unique_index(coll, ["program", "block_name"])
res = store.upsert(coll, core, key=("program", "block_name"), set_on_insert=set_on_insert)  # res ∈ {"inserted","updated","unchanged"}
stats[res] += 1
total = store.count(coll, {"program": manifest["program"]})
store.close()
```

| 方法 | 签名 | 做什么 | 设计思路 |
|---|---|---|---|
| `__init__` | `(self, uri: str, db_name: str)` | `import pymongo` → `MongoClient(uri)` → `client.admin.command("ping")` 验证连通 → 存 `self.client/self.db = client[db_name]` | 连接失败立即抛异常（由调用方 `import_mongo` 包成 `RuntimeError`）；不内置隐藏默认连接串。 |
| `ensure_unique_index` | `(self, coll, keys: list[str]) -> None` | 对 `keys` 建**复合唯一索引**（升序） | 幂等：`create_index` 同结构重复调用无副作用，保证 `(program, block_name)` 不重复。 |
| `upsert` | `(self, coll, doc: dict, key: tuple[str,...], set_on_insert: dict) -> str` | 按 `key` 幂等 upsert，返回 `"inserted"/"updated"/"unchanged"` | 见 3.3。 |
| `count` | `(self, coll, filt: dict) -> int` | `count_documents(filt)` | 入库后打印「该程序共 N 块」。 |
| `close` | `(self) -> None` | `self.client.close()` | 用完释放连接（调用点 426 行已调用）。 |

### 3.3 `upsert` 幂等写入规则（关键，按真实调用点）
`import_mongo` 已在外层完成拆分：先剔除 `created_at/updated_at`，再
`set_on_insert = {k: d.get(k) for k in reserved}`（reserved=`params_in/params_out/calls/logic/java_code`），
`core = d 去掉 reserved`。故 `upsert` 收到的 `doc`(=core) 只含结构字段，`set_on_insert` 只含预留分析字段。

`upsert` 内部：
- `filter = {k: doc[k] for k in key}`，即 `{"program":…, "block_name":…}`。
- `now = datetime.now(timezone.utc)`。
- `update = {"$set": {**doc, "updated_at": now}, "$setOnInsert": {**set_on_insert, "created_at": now}}`。
  - `$set`：结构字段每次重跑都刷新。
  - `$setOnInsert`：预留分析字段 + created_at **仅首次插入**写，重跑不覆盖 → 保护后续步骤回填的 `logic/java_code`。
- `res = self.db[coll].update_one(filter, update, upsert=True)`。
- 返回：`"inserted"` 若 `res.upserted_id`；否则 `"updated"` 若 `res.modified_count`；否则 `"unchanged"`。
  （三态与 `import_mongo` 的 `stats={"inserted","updated","unchanged"}` 累加键一一对应。）

## 4. Block B：输出目录调整（落在 `decompose/manifest.py`）

`--out` 语义从「平铺输出目录」改为「**程序目录**」（如 `…/cob/ZPOLDWNM`）。唯一实质改动在迁入 `manifest.py` 的 `write_files`：

- `manifest.py` 顶部新增模块常量 `SLICE_SUBDIR = "拆解"`。
- `write_files` 内派生 `slice_dir = out_dir / SLICE_SUBDIR`，对它 `mkdir(parents=True, exist_ok=True)`。
- WS 切片与 SECTION 切片的写入目标 `out_dir` 改为 `slice_dir`。
- `section_index` 里的 `"file"` **保持裸文件名**（不加前缀），manifest 结构不变。
- `manifest.json`、`manifest.md` 写入位置**保持 `out_dir`**（程序目录根）。
- 返回的 `stats` 增加 `"slice_dir": str(slice_dir)`，便于核对。

`core.decompose()` 的 `stats["manifest"] = str(out_dir / "manifest.json")`、
入口 `main()` 的 `manifest_path = out_dir / "manifest.json"` **均无需改**（本就基于 `out_dir` 根）。
入口 docstring「用法」与 `--out` help 文本同步更新为新布局示例。

> 注：本 Block 与「§2b 拆分」同批落地——即直接把已含本改动的 `write_files` 写进 `decompose/manifest.py`，不重复改两次。

## 5. Block C：`scripts/verify_decompose.py`（需改，含读取路径）

manifest.json 仍在 `out_dir` 根（26 行 `os.path.join(out_dir, "manifest.json")` 命中，不改）；但切片移到 `拆解/`，故两处读取需加子目录：

- 顶部新增常量 `SLICE_SUBDIR = "拆解"`，并派生 `slice_dir = os.path.join(out_dir, SLICE_SUBDIR)`。
- 第 6 项（67 行）：`os.path.join(out_dir, sec["file"])` → `os.path.join(slice_dir, sec["file"])`。
- 第 7 项（74 行）：`glob.glob(os.path.join(out_dir, "*.cob"))` → `glob.glob(os.path.join(slice_dir, "*.cob"))`。
- 其余检查（块数/入参/COPY/重名/唯一/预留字段）只读 manifest 内容，不涉及路径，**不改**。
- 文件头 docstring「用法」示例更新为新 `--out`（程序目录）。

## 6. 受影响文件清单

| 文件 | 动作 |
|---|---|
| `db/__init__.py` | 新建（包标识） |
| `db/mongo_client.py` | 新建（`MongoStore`，Block A） |
| `decompose/__init__.py` | 新建（包标识 + 重导出） |
| `decompose/models.py` | 新建（迁入 `Block`） |
| `decompose/lines.py` | 新建（迁入行级处理） |
| `decompose/structure.py` | 新建（迁入结构定位） |
| `decompose/blocks.py` | 新建（迁入构块） |
| `decompose/manifest.py` | 新建（迁入写文件，**含 Block B 目录调整**） |
| `decompose/importer.py` | 新建（迁入 `import_mongo`） |
| `decompose/core.py` | 新建（迁入 `decompose()`） |
| `scripts/decompose.py` | **改写为瘦入口**（argparse + 调用；逻辑全部迁出） |
| `scripts/verify_decompose.py` | 改切片读取路径加 `拆解/`（第6、7项）+ docstring（Block C） |
| `docs/操作记录/步骤02-…操作记录.md` | 实现后新建（命令/产物/校验） |

> `scripts/decompose.py` 由 494 行 → 约 35 行；原逻辑无丢失，全部迁入 `decompose/` 包对应文件。

## 7. 验收方式（实现后自检）

1. **不入库可用**：`decompose.py --cob … --program ZPOLDWNM --out /home/zp/Documents/cob/ZPOLDWNM`
   → 生成 `ZPOLDWNM/拆解/*.cob`（134 个）+ `ZPOLDWNM/manifest.json` + `manifest.md`；不依赖 pymongo。
2. **校验**：`verify_decompose.py --out /home/zp/Documents/cob/ZPOLDWNM` → 9 项全 PASS。
3. **入库（需用户给连接串、pymongo 可用）**：`decompose.py --import-only --out …/ZPOLDWNM --mongo-uri <…> --db cobol`
   → 首跑 inserted=134；再跑 updated=134、inserted=0（幂等）；分析字段保持不变。

## 8. 已确认的决定（开放问题已定）

1. **架构索引范围**：`docs/架构索引/项目总览.md` **覆盖整个项目**（拆解线 + 翻译线）。✅
2. **旧产物处理**：`/home/zp/Documents/cob/拆解/ZPOLDWNM/`（旧平铺布局）**保留不删**。✅
3. **是否实跑入库**：本步**只交付代码可用**，不实跑（未提供连接串、pymongo 未装）；入库待环境就绪。✅

## 8b. 拆分等价性自检（除功能验收外）

拆分「只搬运不改逻辑」，实现后额外核对：
- 旧 `scripts/decompose.py` 与新结构对同一输入产出的 `manifest.json` **逐字节一致**（可临时对比，确认后清理）。
- 每个新 `.py` 逻辑行（不含 docstring/注释/空行）≈100 以内。
- 无循环导入；`python3 scripts/decompose.py --help` 正常输出。

## 9. 实现备注（工具可靠性）

本设计已基于 `scripts/decompose.py` 全文逐行核对（含 `MongoStore` 五个真实调用点、`write_files` 内部、
manifest 结构）后定稿；§2b.3 的「行→文件」对照即按真实行号给出。
