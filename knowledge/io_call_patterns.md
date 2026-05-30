# COBOL IO 子程序调用模式 → Java Repository 转换

## 标准 IO 调用结构

COBOL 中通过 `CALL '*IO' USING xxx-PARAMS` 模式访问数据，函数码存储在 PARAMS 的 `-FUNCTION` 字段。
翻译前**必须先看 `-FUNCTION` 是什么**：READR 和 BEGN 的条件、返回形态、方法名都不一样。

### 控制字段（不是数据列，只用于标识/控制）

`xxx-PARAMS` / `xxx-FUNCTION` / `xxx-FORMAT` / `xxx-STATUZ` **不是表里的数据字段**，只是调用约定：

| 控制字段 | 含义 |
|---------|------|
| `xxx-PARAMS`   | 参数结构体本身（入参 + 出参容器） |
| `xxx-FUNCTION` | 功能码（READR / BEGN / NEXTR / UPDAT…），决定这次 CALL 怎么翻 |
| `xxx-FORMAT`   | 记录格式名，控制用 |
| `xxx-STATUZ`   | **查询状态**（出参） |

翻成 List + for 的理想形态里，这些控制语句（setFunction / setFormat / 读 statuz）会被**吸收**进
finder 调用和循环条件，不再单独出现。

### 状态码语义（STATUZ）

| STATUZ | 含义 | 布尔 |
|--------|------|------|
| `O-K`  | 查询到数据 | ok |
| `ENDP` | 已到最后一条 / 没有更多数据 | **not ok** |
| `MRNF` | 没有数据（记录未找到） | **not ok** |

即 `STATUZ NOT = O-K`（或 `= ENDP` / `= MRNF`）统一表示「没（更多）数据」→ 结束循环 / 未命中。

### 方法命名约定（关键）

查询方法名**以功能码结尾，驼峰**，一个 IO 表对应两个查询方法：

- `READR` → `findBy...Readr(...)`：按条件**读取一条**，只读一条，返回单条记录。
- `BEGN`  → `findBy...Begn(...)`：定位读，**返回 `List`**，配合 NEXTR 顺序遍历。

---

### 随机读取（READR）—— 单条

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
// READR → findBy...Readr，返回单条；STATUZ = O-K 即 record != null
TmlclstRecord tmlclst = tmlclstRepository.findByKeyReadr(wsaaCompany, wsaaLanguage);
if (tmlclst != null) {
    wsaaLetter = tmlclst.getLetter();
}
```

### 顺序读取（BEGN + NEXTR 循环）—— 返回 List

`BEGN` 第一次 CALL 返回一条，后续每次 `NEXTR` CALL 返回下一条。我们习惯**一次查成 `List`**，
交给后面的 for 循环遍历使用。

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
// BEGN → findBy...Begn，返回 List；NEXTR 折叠为 for 遍历，STATUZ NOT = O-K 即 List 耗尽
List<TmlclstRecord> records = tmlclstRepository.findByCompanyBegn(wsaaCo);
for (TmlclstRecord tmlclst : records) {
    processRecord2000(tmlclst);
}
```

### BEGN 定位读语义（关键：>= 定位 + 等值跳出 = 等值查询）

`BEGN` 不是「查一条」，而是**按索引键定位**到「第一条 >= 入参键」的记录，然后用 `NEXTR` 顺序向后读。
索引键是**复合键**，按字段顺序比较，语义等价于：

```text
PS01CHR-CHDRCOY > CHDRENQ-CHDRCOY                         （首字段已变大，后续字段忽略）
UNION ALL
PS01CHR-CHDRCOY = CHDRENQ-CHDRCOY AND PS01CHR-CHDRNUM >= CHDRENQ-CHDRNUM   （后续字段忽略）
UNION ALL
... 依此类推（后续有多个键字段以此类推）
```

因此 COBOL 里在 `BEGN` 之后用 `IF ... NOT = ... 跳出` 的写法，本质是把「>= 范围扫描」**裁剪成等值查询**：
一旦读到的键不等于入参键，说明已越过目标区间，立即跳出循环。

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
List<LetclstRecord> records = letclstRepository.findByRequestCompanyAndLetterTypeAndClntcoyAndRdocnumBegn(
        letcmntRequestCompany, letcmntLetterType, letcmntClntcoy, letcmntRdocnum);
if (records.isEmpty()) {
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
// 等值查询条件 + 结果集过滤；BEGN → findBy...Begn 返回 List
List<Ps01chrRecord> records = ps01chrRepository.findByChdrcoyAndChdrnumBegn(
        letcmntRequestCompany, wsaaChdrno);
for (Ps01chrRecord ps01chr : records) {
    if (!"60".equals(ps01chr.getChgsts())) {
        continue;   // 对应 CHGSTS NOT = '60' → NEXTR 跳过
    }
    // 命中：处理逻辑
}
// records 为空 → 对应外层跳出 2075-ES01
```

> 转换规则小结：`BEGN` 之后凡是用 `键字段 NOT = 入参 → 跳出` 的判断，统一翻译为 **`WHERE 键字段 = 入参`** 的
> 等值条件（finder 名 `findBy<等值键...>Begn`，返回 `List`）；位于键判断之后的非键字段判断，翻译为对结果集的
> 过滤（`continue` / WHERE 附加条件）。

### 更新（UPDAT）

```cobol
MOVE UPDAT TO TMLCLST-FUNCTION
MOVE WSAA-NEW-VALUE TO TMLCLST-FIELD
CALL 'TMLCLSTIO' USING TMLCLST-PARAMS
IF TMLCLST-STATUZ NOT = O-K
   PERFORM 9999-ERROR
END-IF
```
```java
tmlclst.setField(wsaaNewValue);
try {
    tmlclstRepository.save(tmlclst);
} catch (Exception e) {
    error9999();
}
```

## ITEM 表操作（最常用，READR 单条）

```cobol
MOVE SPACES       TO ITEM-PARAMS
MOVE WSAA-ITMPFX  TO ITEM-ITEMPFX
MOVE WSAA-ITMTYP  TO ITEM-ITEMTYPE
MOVE WSAA-ITMSEQ  TO ITEM-ITEMSEQ
MOVE READR        TO ITEM-FUNCTION
CALL 'ITEMIO' USING ITEM-PARAMS
IF ITEM-STATUZ = O-K
   MOVE ITEM-GENAREA TO WSAA-GENAREA
END-IF
```
```java
ItemRecord item = itemRepository.findByKeyReadr(wsaaItmpfx, wsaaItmtyp, wsaaItmseq);
if (item != null) {
    wsaaGenarea = item.getGenarea();
}
```

## 日期转换子程序（非 *IO）

```cobol
MOVE WSAA-INT-DATE TO DTC1-INT-DATE
CALL 'DATCON1' USING DTC1-PARAMS
MOVE DTC1-EXT-DATE TO WSAA-EXT-DATE
```
```java
Datcon1Params dtc1 = new Datcon1Params();
dtc1.setIntDate(wsaaIntDate);
dateConversionService.convertDate1(dtc1);
wsaaExtDate = dtc1.getExtDate();
```

## 系统错误处理

```cobol
MOVE 'ERROR MESSAGE' TO SYSERR-MSGID
CALL 'SYSERR' USING SYSERR-PARAMS
```
```java
throw new SystemException("ERROR MESSAGE");
```

## 状态码判断规范

| COBOL 状态码 | Java 等价 |
|------------|---------|
| O-K        | record != null / !list.isEmpty() / 操作成功 |
| MRNF       | record == null / list.isEmpty()（记录未找到） |
| ENDP       | 遍历结束（list 耗尽，循环退出） |
| MDUP       | 重复键异常 |
