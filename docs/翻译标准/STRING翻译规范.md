# STRING/UNSTRING — COBOL → Java 翻译标准

> 本文件定义 `STRING` 和 `UNSTRING` 语句的翻译规范。

---

## 一、STRING

### 1）标准形态

```cobol
STRING WSAA-A DELIMITED BY SIZE
       '/' DELIMITED BY SIZE
       WSAA-B DELIMITED BY SPACES
  INTO WSAA-OUT
```

```java
wsaaOut = wsaaA + "/" + String.valueOf(wsaaB).split(" ", 2)[0];
```

### 2）各 DELIMITED BY 模式

| DELIMITED BY | Java 翻译 |
|-------------|-----------|
| `SIZE` | 直接拼接：`a` |
| `SPACE` / `SPACES` | 取首空格前：`String.valueOf(a).split(" ", 2)[0]` |
| 字面量 `'/'` | 取首分隔符前：`String.valueOf(a).split("/", 2)[0]` |
| 变量 `WSAA-SPACES` | `String.valueOf(a).split(wsaaSpaces, 2)[0]` |

### 3）逗号分隔

COBOL STRING 中可选的逗号被忽略：

```cobol
STRING 'A' , '#' , WSAA-NAME DELIMITED BY SIZE
```
等价于：
```cobol
STRING 'A' '#' WSAA-NAME DELIMITED BY SIZE
```

### 4）不支持的模式

| 模式 | 处理方式 |
|------|---------|
| `WITH POINTER` | TODO-LEAF |
| `ON OVERFLOW` | TODO-LEAF |
| `NOT ON OVERFLOW` | TODO-LEAF |
| 多行续句（INTO 在后续行） | TODO-LEAF（解析器层面） |
| 多目标 INTO | TODO-LEAF |

---

## 二、UNSTRING

### 1）标准形态

```cobol
UNSTRING WSAA-INPUT DELIMITED BY '/'
   INTO WSAA-OUT1 WSAA-OUT2
```

```java
String[] _parts = wsaaInput.split("/");
if (_parts.length > 0) wsaaOut1 = _parts[0];
if (_parts.length > 1) wsaaOut2 = _parts[1];
```

### 2）DELIMITED BY 模式

同 STRING：`SIZE`、`SPACE`、字面量、变量。

### 3）不支持的模式

- `DELIMITED BY ALL`
- `WITH POINTER`
- `TALLYING IN`
- 多分隔符

---

## 三、INSPECT

### 1）TALLYING

```cobol
INSPECT WSAA-INPUT TALLYING WSAA-COUNT FOR ALL '/'
```
```java
wsaaCount = wsaaInput.length() - wsaaInput.replace("/", "").length();
```

### 2）REPLACING

```cobol
INSPECT WSAA-INPUT REPLACING ALL '/' BY '-'
```
```java
wsaaInput = wsaaInput.replace("/", "-");
```

### 3）不支持的模式

- `CHARACTERS`（非 ALL）
- `BEFORE/AFTER INITIAL`
- `CONVERTING`
- `FIRST`
- `LEADING`

---


### 5）DELIMITED BY 省略

COBOL 中 `DELIMITED BY` 可省略，默认为 `DELIMITED BY SIZE`：

```cobol
STRING 'A' , '#' INTO WSAA-OUT
```
等价于：
```cobol
STRING 'A' DELIMITED BY SIZE ',' DELIMITED BY SIZE '#' DELIMITED BY SIZE INTO WSAA-OUT
```
```java
wsaaOut = "A" + "#";
```

## 四、SEARCH

当前全部 fallback 到 TODO-LEAF。待实现。

---

## 五、保守策略

- 所有不支持的模式 → TODO-LEAF，不输出半个正确代码
- 多行 STRING（续行）→ 需要解析器级别修复
