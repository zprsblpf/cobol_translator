# 操作记录 · 步骤一：ZPOLDWNM.cob 拆解 + 写文件

> 执行日期：2026-05-31
> 对应设计文档：`docs/详细设计/步骤01-拆解与存库设计.md`（状态 ✅已认可）
> 执行人：Claude
> 结果：✅ 全部校验通过

---

## 1. 目标

把 `/home/zp/Documents/cob/ZPOLDWNM.cob`（PROGRAM-ID `ZPOLDWNM`，15862 物理行）
按规则拆成独立小块，写成文件 + 生成入库数据源（`manifest.json`）。**本步只拆解，不翻译。**

## 2. 涉及的脚本（均已正式保留）

| 文件 | 作用 |
|---|---|
| `scripts/decompose.py` | 拆解主脚本：切块 + 写文件 + 可选入库（`--mongo-uri`） |
| `scripts/verify_decompose.py` | 拆解结果校验：逐项自检并打印通过情况 |
| `db/mongo_client.py` | MongoDB 封装：连接/存储/查询/更新，幂等 upsert（入库后补用） |
| `db/__init__.py` | 包标识 |

## 3. 执行步骤与命令

### 3.1 环境探测（只读）
- 列出 cob 目录：`/home/zp/Documents/cob/ZPOLDWNM.cob`（1.28 MB）。
- 结构扫描：定位 DIVISION 边界、COPY 清单、PROCEDURE 内 SECTION 头（区分 `!!!!!!` 停用）。
- MongoDB 可用性：本机 27017 未监听、无 docker、项目解释器
  `/data/models/llm-fa312/bin/python` 无 pymongo、venv 禁 `--user` 安装 → 决定「先写文件，后补入库」。

### 3.2 拆解（纯文件模式）
```bash
/data/models/llm-fa312/bin/python scripts/decompose.py \
  --cob "/home/zp/Documents/cob/ZPOLDWNM.cob" --program ZPOLDWNM \
  --out "/home/zp/Documents/cob/拆解/ZPOLDWNM"
```

### 3.3 校验
```bash
/data/models/llm-fa312/bin/python scripts/verify_decompose.py \
  --out "/home/zp/Documents/cob/拆解/ZPOLDWNM"
```

### 3.4 入库（后补，待 Mongo 就绪）
```bash
/data/models/llm-fa312/bin/python scripts/decompose.py --import-only \
  --out "/home/zp/Documents/cob/拆解/ZPOLDWNM" \
  --mongo-uri "mongodb://<用户提供>/" --db cobol
```

## 4. 应用的拆解规则（摘要）

- 第 1–6 列 `!!!!!!` → 停用旧代码，**丢弃**（含 `!!!!!!` 开头的 SECTION 头不作为边界）。
- 第 7 列 `*` `/` → 注释，**保留**。
- 取第 7–72 列代码区，去行尾 `<变更标记>`，rstrip，空行丢弃。
- `PROGRAM-ID` → 类名 `ZPOLDWNM`；`WORKING-STORAGE` → 参数块 `ZPOLDWNMWSAA`。
- `COPY`：REC/SKM=实体字段；VARCOM=逻辑；其余=other（只分类）。
- `PROCEDURE DIVISION USING` → 入参；每个有效 SECTION → 一个切片文件。

## 5. 产物

目录：`/home/zp/Documents/cob/拆解/ZPOLDWNM/`
- 133 个 `*.cob` SECTION 切片
- `ZPOLDWNMWSAA.cob`（WORKING-STORAGE 参数块）
- `manifest.json`（含全部待入库字段，作为后补入库数据源）
- `manifest.md`（人读清单：类名/入参/COPY 分类/SECTION 表）

## 6. 校验结果（全部 ✅）

| 检查项 | 结果 |
|---|---|
| 块数统计 | 135 = META 1 + WORKING-STORAGE 1 + SECTION 133 |
| 入参 | `[LETCMNT-PARAMS, PMSPNT-PARAMS]` |
| COPY 分类 | rec_skm 134 / varcom 1(`VARCOM`) / other 1(`ITEMKEY`) |
| SECTION 名无重复 | ✅ |
| 切片文件名唯一 | ✅ 133 |
| manifest.raw_text 与切片文件逐字一致 | ✅ 0 不符 |
| `!!!!!!` 停用行已丢弃 | ✅ 0 残留 |
| `*` 注释保留 | ✅ 93 文件含注释 |
| 预留字段均为 null | ✅ |

## 7. 后续

- Mongo 就绪后执行 3.4 入库。
- 进入步骤二：逐块的处理逻辑 + 翻译规则（先出设计文档，等认可）。
