# COBOL 数据类型 → Java 类型规范

## 基础类型映射

| COBOL PIC | 示例 | Java 类型 | 备注 |
|-----------|------|---------|------|
| PIC X(n) | PIC X(08) | String | 去掉尾随空格 trim() |
| PIC X | PIC X | String | 单字符也用 String |
| PIC 9(n) n≤9 | PIC 9(07) | int | 无符号整数 |
| PIC 9(n) n>9 | PIC 9(15) | long | 大整数 |
| PIC S9(n) | PIC S9(07) | int/long | 有符号整数 |
| PIC S9(n)V9(m) | PIC S9(15)V9(2) | BigDecimal | 保险金额，必须用 BigDecimal |
| PIC S9(n) COMP-3 | PIC S9(07) COMP-3 | long | 二进制压缩 |
| 01 GROUP | WS-GROUP | class/record | 封装为内部类或 DTO |

## OCCURS（数组）处理

```cobol
03 WS003-WRESERVES    OCCURS 99 TIMES  PIC S9(07) COMP-3
```
```java
private long[] ws003Wreserves = new long[99];
// 注意: COBOL 下标从1开始，Java从0开始
// COBOL: WS003-WRESERVES(1) → Java: ws003Wreserves[0]
```

```cobol
03 WS001-CVALUES      OCCURS 200       PIC S9(15)V9(2)
```
```java
private BigDecimal[] ws001Cvalues = new BigDecimal[200];
// 初始化
Arrays.fill(ws001Cvalues, BigDecimal.ZERO);
```

## 嵌套 OCCURS（多维数组）

```cobol
03 WSAA-TOAGES-INF    OCCURS 3 TIMES.
   05 WSAA-TOAGES     OCCURS 3 TIMES  PIC S9(07) COMP-3.
```
```java
private long[][] wsaaToages = new long[3][3];
// COBOL: WSAA-TOAGES(I, J) → Java: wsaaToages[i-1][j-1]
```

## REDEFINES（内存重叠）

```cobol
01 WSAA-CVCP-AMOUNT            PIC X(17).
01 WSAA-CVCP-AMOUNT-D REDEFINES WSAA-CVCP-AMOUNT  PIC S9(15)V9(2).
```
```java
// REDEFINES 在 Java 中没有直接等价物
// 两个字段独立维护，需要时手动同步
private String wsaaCvcpAmount;        // 字符视图
private BigDecimal wsaaCvcpAmountD;   // 数值视图
// TODO-REDEFINES: 确认两个字段的同步逻辑
```

## GROUP 变量

```cobol
01 WS-POLICY-INFO.
   03 WS-POLICY-NO    PIC X(08).
   03 WS-POLICY-TYPE  PIC X(02).
   03 WS-POLICY-AMT   PIC S9(15)V9(2).
```
```java
// 选项1：内部类
private static class WsPolicyInfo {
    String wsPolicyNo;
    String wsPolicyType;
    BigDecimal wsPolicyAmt;
}
private WsPolicyInfo wsPolicyInfo = new WsPolicyInfo();

// 选项2：扁平化（大多数情况）
private String wsPolicyNo;
private String wsPolicyType;
private BigDecimal wsPolicyAmt;
```

## 命名规范转换

| COBOL 命名 | Java 命名 | 说明 |
|-----------|---------|------|
| WSAA-POLICY-NO | wsaaPolicyNo | 去连字符，camelCase |
| WSAA-CVCP-AMOUNT-D | wsaaCvcpAmountD | 保留D后缀 |
| WS003-WRESERVES | ws003Wreserves | 数字前缀保留 |
| LETCMNT-PARAMS | letcmntParams | 参数结构 |
| DTC1-INT-DATE | dtc1IntDate | 子程序参数 |

## 特殊注意事项

1. **COMP-3 精度**：COMP-3 是 BCD 编码，转为 Java long 时无精度损失
2. **字符串比较**：COBOL `= SPACES` → Java `StringUtils.isBlank()` 而非 `== null`
3. **数组下标**：COBOL 从 1 开始，Java 从 0 开始，翻译时 -1
4. **BigDecimal 初始化**：PIC S9(n)V9(m) 字段必须初始化为 `BigDecimal.ZERO`
5. **字符串 trim**：从 IO 读取的字符串需要 `.trim()`，AS/400 用空格填充固定长度字段
6. **有符号整数 | PIC S9(n) | PIC S9(07) | int/long |赋值给| PIC 9(n) n≤9 | PIC 9(07) | int | 无符号整数 |，就会变成正数
