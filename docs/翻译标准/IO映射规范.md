# IO 映射规范 — CALL 'XXXIO' 的翻译配置

> 本文档定义如何配置 `config/mappings/io_mappings.yaml`，使 COBOL 的 `CALL 'XXXIO'`
> 被确定性翻译为 Spring Data Repository 调用。
> 与 `docs/翻译标准/io查询.md`（IO 语义规范）互补，本文侧重**配置方法与映射规则**。

---

## 一、映射体系结构

IO 映射分三层：

```
io_default_pattern  →  *IO 通用派生范式（所有 *IO 结尾的程序自动生效）
       │
       ▼
io_programs         →  显式覆盖（非标准方法名 / 特殊操作码）
       │
       ▼
date_programs / system_programs  →  非 *IO 子程序（日期转换、系统调用）
```

### 第一层：io_default_pattern（通用派生）

所有以 `IO` 结尾的 `CALL` 自动按此范式派生映射，无需逐表登记。

```yaml
io_default_pattern:
  class_suffix: "Repository"          # 类名后缀：SCF4CHR → Scf4chrRepository
  field_suffix: "Repository"          # 字段名后缀：scf4chrRepository
  param_struct_suffix: "-PARAMS"      # 参数结构体后缀：SCF4CHR-PARAMS
  import_package: "com.example.repository"
  operations:
    READR: "findByKeyReadr({key})"    # 单条读：返回实体或 null
    BEGN:  "findByKeyBegn({key})"     # 单次定位读：同 READR 语义
    UPDAT: "save({entity})"           # 更新
    WRITR: "save({entity})"           # 插入
    DELET: "delete({entity})"         # 删除
```

派生结果示例：

| CALL | class_name | field_name | method(READR) |
|------|-----------|-----------|--------------|
| `COVRIO` | `CovrRepository` | `covrRepository` | `findByKeyReadr(obj)` |
| `ITDMIO` | `ItdmRepository` | `itdmRepository` | `findByKeyReadr(obj)` |
| `TMLCLSTIO` | `TmlclstRepository` | `tmlclstRepository` | `findByKeyReadr(obj)` |

### 第二层：io_programs（显式覆盖）

当某个 IO 程序的方法名不符合标准派生时，在此登记增量覆盖。

```yaml
io_programs:
  CHDRENQIO:
    operations:
      READR: "findByPolicyNoReadr({policyNo})"   # 不用 findByKeyReadr
```

只写与范式不同的字段；其余的类名/字段名/import 仍走派生。

### 第三层：非 *IO 子程序

日期转换、系统调用等不以 IO 结尾的子程序，必须显式登记。

```yaml
date_programs:
  DATCON1:
    java_class: "DateConversionService"
    field_name: "dateConversionService"
    method: "convertDate1({params})"

system_programs:
  SYSERR:
    java_code: "throw new SystemException({message})"
  ZPOLDWNTM:
    java_class: "ZpoldwntmService"
    field_name: "zpoldwntmService"
    method: "process({params})"
```

---

## 二、功能码（FUNCTION）与方法对应

每个 `CALL 'XXXIO'` 之前都会有一个 `MOVE <功能码> TO XXX-FUNCTION`。
功能码决定了用 Repository 的哪个方法：

| 功能码 | 语义 | 对应 Repository 方法 | 备注 |
|--------|------|---------------------|------|
| `READR` | 随机读一条 | `findByKeyReadr(key)` | 返回实体或 null |
| `READS` | 随机读（锁） | `findByKeyReads(key)` | 同上，带锁 |
| `BEGN` | 游标定位读首条 | `findByKeyBegn(key)` | 单用等价于 READR |
| `NEXTR` | 游标读下条 | — | 由结构吸收改写为非 foreach |
| `WRITR` | 插入新记录 | `save(entity)` | |
| `WRITE` | 插入 | `save(entity)` | |
| `UPDAT` | 更新 | `save(entity)` | |
| `DELET` | 删除 | `delete(entity)` | |
| `REWRT` | 重写 | `save(entity)` | |

---

## 三、添加新 IO 映射的步骤

### 3.1 *IO 程序（无需登记）

所有 `*IO` 结尾的 CALL 自动生效。**不需要在 yaml 中写任何条目**，
除非方法名与默认派生不同。

验证方法名是否正确：
```python
from config import spec_loader
info = spec_loader.io_programs().get("MYIO")
default = spec_loader.io_default_pattern()
from translator.leaf.call import derive_io_info
derived = derive_io_info("MYIO", default)
print(derived)  # 查看自动派生的映射
```

### 3.2 非 *IO 程序（需要登记）

1. 确认程序类别：日期转换 → `date_programs`、系统调用 → `system_programs`
2. 在对应节添加条目，至少提供 `java_class`、`field_name`、`method`（或 `java_code`）

### 3.3 验证

```bash
python -c "
from config import spec_loader
from translator.leaf.call import resolve_io_info
info = resolve_io_info('MYIO', spec_loader.io_programs(), spec_loader.io_default_pattern())
print(info)
"
```

---

## 四、翻译流程（内部机制）

理解 CALL 的翻译顺序有助于排查问题：

```
SECTION 翻译开始
  │
  ├─ structure_rewrite.rewrite_structures()
  │   ├─ rewrite_begn_foreach()    # BEGN+NEXTR 循环 → for(Rec r : list)
  │   ├─ rewrite_begn_single()     # BEGN + 等值检查 → List<Rec>
  │   ├─ rewrite_readr_single()    # READR + IF STATUZ → Rec r = find...; if(r!=null)
  │   └─ rewrite_write_single()    # UPDAT/WRITR + IF STATUZ → try{ save }catch
  │
  ├─ build_skeleton() / SectionJavaVisitor.render_paragraphs()
  │   └─ 对未被吸收的散点语句：
  │       └─ translate_leaf_stmt()
  │           └─ translate_call()  # 散点 CALL 兜底
  │               ├─ *IO + 已知功能码 → repo.method()
  │               ├─ 日期子程序 → dateConversionService.method()
  │               ├─ 系统子程序 → 直出 java_code 或 service.method()
  │               └─ 其他 → TODO，交 LLM
```

**如果 CALL 变成 TODO，排查顺序：**

1. 是否被 `structure_rewrite` 吸收了？→ 检查 `rewrite_*` 的匹配条件
2. `io_default_pattern` 是否能派生？→ CALL 是否以 `IO` 结尾
3. `struct_function` 是否有功能码？→ 前一句 `MOVE <func> TO XXX-FUNCTION` 是否被识别
4. 功能码是否在 `operations` 中？→ 如 BEGN 需添加

---

## 五、ZPOLDWNM 完整 IO 映射表

### *IO 程序（86 个，全部由默认范式派生）

`AA01IO`, `AA20AGFIO`, `AA28AGTIO`, `ACBLIO`, `ACMVLDGIO`, `ADOCIO`,
`AFEXIO`, `AGLFIO`, `AGNTIO`, `ANWDIO`, `BABRIO`, `BM12IO`, `BM14IO`,
`C3PDIO`, `CANOAPPIO`, `CHADIO`, `CHDRENQIO`, `CHDRLNBIO`, `CHDRPSNIO`,
`CITYBRNIO`, `CLEXIO`, `CLNTIO`, `CLTSIO`, `COVRIO`, `COVRMJAIO`,
`CRATIO`, `CREPPKYIO`, `CVLLCHRIO`, `CVLLCI3IO`, `CVSTIO`, `DESCIO`,
`EIAACHRIO`, `ELPOIO`, `ES01CHRIO`, `EUAAPKYIO`, `EUABCHRIO`,
`EUABSTMIO`, `EUADPKYIO`, `EUAEALLIO`, `EUAGCLNIO`, `EUCAPKYIO`,
`EUFKPKYIO`, `EUFOPKYIO`, `EULDCRTIO`, `EULEPKYIO`, `EUPMCHBIO`,
`EWAAAPPIO`, `EWABINVIO`, `HPADIO`, `IM02IO`, `ITDMIO`, `ITEMIO`,
`LCCCIO`, `LCCCPRNIO`, `LETCLSTIO`, `LEXTIO`, `LIFECLMIO`,
`LIFEMJAIO`, `MTPAIO`, `PCTPAJMIO`, `PCTPMJAIO`, `PD41IO`,
`PS01CHRIO`, `PS01IO`, `PS29CHRIO`, `PS36IO`, `PTRNCCBIO`,
`RTRNARCIO`, `SCF1PKYIO`, `SCF4CHRIO`, `SCF4PKYIO`, `SCF5CHRIO`,
`SCSDMJAIO`, `SIMGNBIIO`, `SNBIPKYIO`, `TA12IO`, `TA17PARIO`,
`TMLCLSTIO`, `TMLCPKYIO`, `TMRDIO`, `TSRDPKYIO`, `ULNKIO`,
`ZDWNFMTIO`, `ZLCPIO`, `ZLSSINVIO`, `ZRECRCPIO`

### 非 *IO 程序（20 个，需显式登记）

| 程序 | 类别 | java_class/field_name | method/java_code |
|------|------|----------------------|-----------------|
| `DATCON1` | date | DateConversionService | convertDate1({params}) |
| `DATCON2` | date | DateConversionService | convertDate2({params}) |
| `DATCON3` | date | DateConversionService | convertDate3({params}) |
| `DATCON4` | date | DateConversionService | convertDate4({params}) |
| `SYSERR` | system | — | throw new SystemException({message}) |
| `ZPOLDWNTM` | system | ZpoldwntmService | process({params}) |
| `ZPOLPRDNM` | system | ZpolprdnmService | process({params}) |
| `ACMVLDGCP` | service | AcmvldgcpService | process({params}) |
| `BCNVR` | service | BcnvrService | convert({params}) |
| `CAL234` | service | Cal234Service | calculate({params}) |
| `CALAPE` | service | CalapeService | calculate({params}) |
| `CALCSV` | service | CalcsvService | calculate({params}) |
| `CALRDVAL` | service | CalrdvalService | calculate({params}) |
| `CALRUVAL` | service | CalruvalService | calculate({params}) |
| `CHKTL` | service | ChktlService | check({params}) |
| `GETBRN` | service | GetbrnService | get({params}) |
| `HEXACNV` | service | HexacnvService | convert({params}) |
| `NAMADRS` | service | NamadrsService | getNameAddress({params}) |
| `TCPOINT` | service | TcpointService | calculate({params}) |
| `ZBPREM` | service | ZbpremService | getPremium({params}) |

---

## 六、常见问题

### Q: 为什么 *IO 程序还会出现 TODO-CALL？

通常原因：
1. **功能码未被识别**：确认该 CALL 前有 `MOVE <func> TO XXX-FUNCTION` 且被翻译器读到
2. **功能码不在 operations 中**：如 BEGN 需要添加到 `io_default_pattern.operations`
3. **结构吸收未命中**：BEGN+NEXTR 循环或 READR+IF 模式未匹配 `structure_rewrite` 的条件

排查方法：查看生成 Java 中 `// TODO-CALL: CALL 'XXXIO'` 的上下文，确定是哪类问题。

### Q: BEGN 和 READR 的区别？

- `READR`：按键值直接读取一条记录，查不到返回 O-K 或 MRNF
- `BEGN`：按索引键定位到首条记录，配合 `NEXTR` 顺序向下读

当 BEGN **单独使用**（无后续 NEXTR 循环）时，语义等价于 READR。
