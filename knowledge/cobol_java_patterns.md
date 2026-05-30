# COBOL → Java 通用转换模式

## 数据移动 MOVE

```cobol
MOVE SPACES TO WSAA-NAME
```
```java
wsaaName = "";
```

```cobol
MOVE ZEROS TO WSAA-AMOUNT
```
```java
wsaaAmount = BigDecimal.ZERO;  // 金额字段
// 或
wsaaAmount = 0;                // 整数字段
```

```cobol
MOVE 'ABC' TO WSAA-CODE
```
```java
wsaaCode = "ABC";
```

```cobol
MOVE WSAA-A TO WSAA-B
```
```java
wsaaB = wsaaA;
```

```cobol
MOVE CORR WS-GROUP-A TO WS-GROUP-B
```
```java
// MOVE CORR: 逐字段复制同名字段，需人工确认字段列表
wsBGroupField1 = wsAGroupField1;
wsBGroupField2 = wsAGroupField2;
// TODO: 验证 MOVE CORR 字段列表完整性
```

## 条件判断 IF

```cobol
IF WSAA-STATUZ = O-K
   PERFORM 1000-PROCESS
END-IF
```
```java
if ("O-K".equals(wsaaStatuz)) {
    process1000();
}
```

```cobol
IF WSAA-NAME = SPACES
   MOVE 'ERROR' TO WSAA-MSG
END-IF
```
```java
if (wsaaName == null || wsaaName.trim().isEmpty()) {
    wsaaMsg = "ERROR";
}
```

```cobol
IF WSAA-AMT > ZEROS
   PERFORM 2000-CALC
ELSE
   PERFORM 9000-ERROR
END-IF
```
```java
if (wsaaAmt.compareTo(BigDecimal.ZERO) > 0) {
    calc2000();
} else {
    error9000();
}
```

```cobol
IF WSAA-FLAG = 'Y'
   NEXT SENTENCE
ELSE
   PERFORM 9999-ERROR
END-IF
```
```java
if (!"Y".equals(wsaaFlag)) {
    error9999();
}
```

## PERFORM 调用

```cobol
PERFORM 1000-INIT
```
```java
init1000();
```

```cobol
PERFORM 1000-INIT THRU 1000-EXIT
```
```java
init1000();  // 1000-EXIT 是退出标签，直接忽略
```

```cobol
PERFORM VARYING WSAA-IDX FROM 1 BY 1 UNTIL WSAA-IDX > 10
   PERFORM 2000-PROCESS
END-PERFORM
```
```java
for (int wsaaIdx = 1; wsaaIdx <= 10; wsaaIdx++) {
    process2000();
}
```

```cobol
PERFORM UNTIL WSAA-STATUZ NOT = O-K
   PERFORM 3000-READ-NEXT
END-PERFORM
```
```java
while ("O-K".equals(wsaaStatuz)) {
    readNext3000();
}
```

## GO TO 处理

```cobol
GO TO 1000-EXIT
```
```java
return;  // TODO-GOTO: 验证 GO TO 到 EXIT 段的逻辑是否等同于 return
```

```cobol
GO TO 2000-POLICY-OWNER
```
```java
// TODO-GOTO: 非 EXIT 的 GO TO，需人工检查控制流
// 原代码跳转到 2000-POLICY-OWNER SECTION
policyOwner2000();
return;
```

## EVALUATE（类 switch）

```cobol
EVALUATE WSAA-FUNC
   WHEN 'READ'  PERFORM 1000-READ
   WHEN 'WRITE' PERFORM 2000-WRITE
   WHEN OTHER   PERFORM 9000-ERROR
END-EVALUATE
```
```java
switch (wsaaFunc.trim()) {
    case "READ"  -> read1000();
    case "WRITE" -> write2000();
    default      -> error9000();
}
```

## 字符串操作

```cobol
STRING WSAA-A DELIMITED SIZE
       WSAA-B DELIMITED SIZE
       INTO WSAA-RESULT
```
```java
wsaaResult = wsaaA + wsaaB;
```

```cobol
UNSTRING WSAA-INPUT DELIMITED ','
         INTO WSAA-PART1 WSAA-PART2
```
```java
String[] parts = wsaaInput.split(",", -1);
wsaaPart1 = parts.length > 0 ? parts[0] : "";
wsaaPart2 = parts.length > 1 ? parts[1] : "";
```

## 数值计算

```cobol
ADD WSAA-A TO WSAA-B
```
```java
wsaaB = wsaaB.add(wsaaA);  // BigDecimal
// 或
wsaaB += wsaaA;             // int/long
```

```cobol
SUBTRACT WSAA-A FROM WSAA-B
```
```java
wsaaB = wsaaB.subtract(wsaaA);  // BigDecimal
```

```cobol
MULTIPLY WSAA-RATE BY WSAA-AMT GIVING WSAA-RESULT
```
```java
wsaaResult = wsaaAmt.multiply(wsaaRate);
```

```cobol
DIVIDE WSAA-A BY WSAA-B GIVING WSAA-RESULT ROUNDED
```
```java
wsaaResult = wsaaA.divide(wsaaB, 2, RoundingMode.HALF_UP);
```

## COMPUTE

```cobol
COMPUTE WSAA-RESULT = (WSAA-A + WSAA-B) * WSAA-RATE
```
```java
wsaaResult = wsaaA.add(wsaaB).multiply(wsaaRate);
```

## 表格/数组（OCCURS）

```cobol
MOVE WSAA-VALUE(WSAA-IDX) TO WSAA-TEMP
```
```java
wsaaTemp = wsaaValue[wsaaIdx - 1];  // COBOL 下标从1开始，Java从0开始
```

```cobol
PERFORM VARYING WSAA-I FROM 1 BY 1 UNTIL WSAA-I > 99
   MOVE ZEROS TO WS003-WRESERVES(WSAA-I)
END-PERFORM
```
```java
for (int wsaaI = 0; wsaaI < 99; wsaaI++) {
    ws003Wreserves[wsaaI] = 0L;
}
```

## 特殊值判断

```cobol
IF WSAA-FIELD = SPACES OR WSAA-FIELD = LOW-VALUES
```
```java
if (wsaaField == null || wsaaField.trim().isEmpty()) {
```

```cobol
IF WSAA-COUNT NOT = ZEROS
```
```java
if (wsaaCount != 0) {
```

## 系统函数

```cobol
ACCEPT WSAA-SYS-TIME FROM TIME
```
```java
wsaaSysTime = LocalTime.now().format(DateTimeFormatter.ofPattern("HHmmsscc"));
```
