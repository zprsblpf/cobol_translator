# IO 查询 — COBOL → Java 翻译标准

> 本文件由 `docs/翻译标准/io查询`（无扩展名原稿）结构化转换而来，内容忠实保留，仅做 Markdown 排版。
> 主题：`CALL '*IO' USING xxx-PARAMS` 数据访问模式的翻译规范。

---

## 一、IO 调用基本结构与约定

典型 IO 调用片段：

```cobol
INITIALIZE              PS01CHR-PARAMS
MOVE CHDRENQ-CHDRCOY TO PS01CHR-CHDRCOY.
MOVE CHDRENQ-CHDRNUM TO PS01CHR-CHDRNUM.
MOVE XXX             TO PS01CHR-FUNCTION
MOVE PS01CHRREC      TO PS01CHR-FORMAT
CALL 'XXXIO'         USING PS01CHR-PARAMS
IF PS01CHR-STATUZ         NOT = O-K    AND
   PS01CHR-STATUZ           NOT = ENDP
```

**约定说明：**

- `INITIALIZE`：初始化，需要给字段赋值默认值。
- `PS01CHR-FUNCTION`、`PS01CHR-FORMAT`、`PS01CHR-PARAMS`、`PS01CHR-STATUZ`：实际**没有这些字段**，只是用来标识用。
- `PS01CHR-STATUZ`：表示查询的状态。

**STATUZ 状态码：**

| STATUZ | 含义 | 判定 |
|---|---|---|
| `O-K`（ok） | 表示查询到数据 | ok |
| `ENDP` | 查询到最后一条，意思就是没有数据 | not ok |
| `MRNF` | 没有数据 | not ok |

> `ENDP`、`MRNF` 都是 not ok。

---

## 二、CALL 与 FUNCTION：READR vs BEGN

`call` 之前需要看 `FUNCTION` 是什么；`READR` 和 `BEGN` 的条件不一样。查询名字是 2 个，**建议以 `READR`、`BEGN` 结尾，驼峰规则**。

- **READR**：表示按照条件读取一条数据，只读一条。
- **BEGN**：实际是返回一条，他是结合 `NEXTR` 使用。第一次 `FUNCTION` 是 `BEGN`，call 返回一条；后续 `NEXTR`，每一次 call 就是查询下面一条数据；我们习惯**返回 list**，给后面使用。

**BEGN 复合键定位语义（后续字段可忽略）：**

```text
PS01CHR-CHDRCOY > CHDRENQ-CHDRCOY           （后面的字段可以忽略）
union all
PS01CHR-CHDRCOY = CHDRENQ-CHDRCOY
    and
PS01CHR-CHDRNUM >= CHDRENQ-CHDRNUM          （后面的字段可以忽略）
后续有多个字段以此类推
```

---

COBOL 中通过 `CALL '*IO' USING PARAMS` 模式访问数据，函数码存储在 `PARAMS` 的 `-FUNCTION` 字段。

### 随机读取（READR）

```cobol
MOVE SPACES         TO TMLCLST-PARAMS
MOVE WSAA-COMPANY   TO TMLCLST-COMPANY
MOVE WSAA-LANGUAGE  TO TMLCLST-LANGUAGE
MOVE READR          TO TMLCLST-FUNCTION
CALL 'TMLCLSTIO' USING TMLCLST-PARAMS
IF TMLCLST-STATUZ = O-K
   MOVE TMLCLST-LETTER TO WSAA-LETTER
END-IF
```
```java
// Java 等价
TmlclstKey key = new TmlclstKey(wsaaCompany, wsaaLanguage);
TmlclstRecord tmlclst = tmlclstRepository.findByKeyReadr(key);
if (tmlclst != null) {
    wsaaLetter = tmlclst.getLetter();
}
```

### 顺序读取（BEGN + NEXTR 循环）

```cobol
MOVE SPACES    TO TMLCLST-PARAMS
MOVE WSAA-CO   TO TMLCLST-COMPANY
MOVE BEGN      TO TMLCLST-FUNCTION
CALL 'TMLCLSTIO' USING TMLCLST-PARAMS

PERFORM UNTIL TMLCLST-STATUZ NOT = O-K
   PERFORM 2000-PROCESS-RECORD
   MOVE NEXTR TO TMLCLST-FUNCTION
   CALL 'TMLCLSTIO' USING TMLCLST-PARAMS
END-PERFORM
```
```java
// Java 等价（使用 Spring Data 分页或游标）
List<TmlclstRecord> records = tmlclstRepository.findByCompanyBegn(wsaaCo);
for (TmlclstRecord tmlclst : records) {
    // processRecord2000(tmlclst);
    processRecord2000();
}
```

### BEGN 定位读语义（关键：>= 定位 + 等值跳出 = 等值查询）

`BEGN` 不是「查一条」，而是**按索引键定位**到「第一条 >= 入参键」的记录，然后用 `NEXTR` 顺序向后读。
索引键是**复合键**，按字段顺序比较，语义等价于：

```text
PS01CHR-CHDRCOY > CHDRENQ-CHDRCOY                         （首字段已变大，后续字段忽略）
UNION ALL
PS01CHR-CHDRCOY = CHDRENQ-CHDRCOY AND PS01CHR-CHDRNUM >= CHDRENQ-CHDRNUM
UNION ALL
... 依此类推
```

因此 COBOL 里在 `BEGN` 之后用 `IF ... NOT = ... 跳出` 的写法，本质是把「>= 范围扫描」**裁剪成等值查询**：一旦读到的键不等于入参键，说明已越过目标区间，立即跳出循环。

#### 示例一：单条等值定位（LETCLSTIO）

```cobol
      INITIALIZE                      LETCLST-PARAMS.
      MOVE ZEROS                   TO LETCLST-LETTER-SEQNO.
      MOVE LETCMNT-REQUEST-COMPANY TO LETCLST-REQUEST-COMPANY.
      MOVE LETCMNT-LETTER-TYPE     TO LETCLST-LETTER-TYPE.
      MOVE LETCMNT-CLNTCOY         TO LETCLST-CLNTCOY.
      MOVE LETCMNT-RDOCNUM         TO LETCLST-RDOCNUM.
      MOVE SPACES                  TO LETCLST-CLNTNUM.
      MOVE LETCLSTREC              TO LETCLST-FORMAT.
      MOVE BEGN                    TO LETCLST-FUNCTION.
      CALL 'LETCLSTIO'             USING LETCLST-PARAMS.

      IF LETCLST-STATUZ NOT = O-K OR
         LETCLST-REQUEST-COMPANY NOT = LETCMNT-REQUEST-COMPANY OR
         LETCLST-LETTER-TYPE     NOT = LETCMNT-LETTER-TYPE     OR
         LETCLST-CLNTCOY         NOT = LETCMNT-CLNTCOY         OR
         LETCLST-RDOCNUM         NOT = LETCMNT-RDOCNUM
         MOVE 'N' TO WSAA-REP
      END-IF.
```

`BEGN` 定位后用一组 `NOT =` 判断：只要任一键字段不等于入参，就视为「未命中」。
等价于按等值条件查首条记录：

```java
// 等值查询 + 取首条；查不到（或键不匹配）则 wsaaRep = "N"
LetclstRecord letclst = letclstRepository.findFirstByRequestCompanyAndLetterTypeAndClntcoyAndRdocnum(
        letcmntRequestCompany, letcmntLetterType, letcmntClntcoy, letcmntRdocnum);
if (letclst == null) {
    wsaaRep = "N";
}
```

#### 示例二：定位 + NEXTR 循环 + 内层过滤（PS01CHRIO）

```cobol
      MOVE SPACES                  TO PS01CHR-PARAMS.
      MOVE LETCMNT-REQUEST-COMPANY TO PS01CHR-CHDRCOY.
      MOVE WSAA-CHDRNO             TO PS01CHR-CHDRNUM.
      MOVE PS01CHRREC              TO PS01CHR-FORMAT.
      MOVE BEGN                    TO PS01CHR-FUNCTION.

2071-CALL-PS01.
      CALL 'PS01CHRIO'             USING PS01CHR-PARAMS.

      IF PS01CHR-STATUZ NOT = O-K OR
         PS01CHR-CHDRCOY NOT = LETCMNT-REQUEST-COMPANY OR
         PS01CHR-CHDRNUM NOT = WSAA-CHDRNO
         GO TO 2075-ES01
      END-IF.

      IF PS01CHR-CHGSTS NOT = '60'
         MOVE NEXTR TO PS01CHR-FUNCTION
         GO TO 2071-CALL-PS01
      END-IF.

      MOVE NEXTR TO PS01CHR-FUNCTION.
      GO TO 2071-CALL-PS01.
```

要点拆解：
- 外层 `NOT =` 判断 = **等值查询条件**：`CHDRCOY = LETCMNT-REQUEST-COMPANY AND CHDRNUM = WSAA-CHDRNO`，越界即 `GO TO 2075-ES01` 退出。
- 内层 `CHGSTS NOT = '60'` = 在结果集上的**附加过滤**：不满足就 `NEXTR` 跳过，继续下一条。
- 整体语义：在 `CHDRCOY/CHDRNUM` 等值的记录中，筛选 `CHGSTS = '60'` 的记录逐条处理。

```java
// 等值查询条件 + 结果集过滤
List<Ps01chrRecord> records = ps01chrRepository.findByChdrcoyAndChdrnum(
        letcmntRequestCompany, wsaaChdrno);
for (Ps01chrRecord ps01chr : records) {
    if (!"60".equals(ps01chr.getChgsts())) {
        continue;   // 对应 CHGSTS NOT = '60' → NEXTR 跳过
    }
    // 命中：处理逻辑
}
// records 为空 → 对应外层跳出 2075-ES01
```
