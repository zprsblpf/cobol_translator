# 流程结构（控制流）— COBOL → Java 翻译标准

> 本文件由 `docs/翻译标准/流程结构.md` 扩展而来，补充 GO TO 跳转的翻译规范。
> 翻译规范以 `E:\code\project\db2-for-new-project` 参考项目的手工翻译为准。

---

## 一、GO TO 跳转翻译规范

### 1）核心原则：段落提取为方法

COBOL 的 GO TO 跳转在 Java 中**不**翻译为 while+switch 状态机，
而是**把目标段落提取为独立的 private 方法**，GO TO 处改为方法调用 + return。

### 2）跳转分类与翻译方案

| GO TO 类型 | 示例 | 翻译方案 |
|-----------|------|---------|
| **出口跳转** | `GO TO 190-EXIT` | `return;` |
| **段落调用** | `GO TO C489-NEXT-ITEM` | `nextItemC489(wsaa, cache); return;` |
| **循环回跳** | `GO TO 2071-CALL-PS01` | `continue;`（在 for 循环内） |
| **前向跳过** | `GO TO 2075-ES01` | if/else 重构或 `return;` |

### 3）翻译示例

#### 示例一：出口跳转 → return

**COBOL：**
```cobol
IF WSAA-REP = 'R'
    GO TO 190-EXIT
END-IF.
...
190-EXIT.
    EXIT PROGRAM.
```

**Java（参考项目翻译）：**
```java
if ("R".equals(wsaa.getRep())) {
    return;  // GO TO 190-EXIT
}
...
// 190-EXIT 不需要额外方法，return 表达含义
```

#### 示例二：段落调用 → 提取方法

**COBOL：**
```cobol
C450-GET-NAME.
    ...查找逻辑...
    IF PD41 查到
        GO TO C489-NEXT-ITEM
    END-IF
    ...继续其他查找...
    
C489-NEXT-ITEM.
    ...处理下一项...
```

**Java（参考项目翻译）：**
```java
private void get_name_c450(WsaaZpoldwnm wsaa, ZpoldwnmCache cache) {
    ...查找逻辑...
    if (pd41 != null) {
        next_item_c489(wsaa, pd41, cache);  // GO TO C489-NEXT-ITEM
        return;
    }
    ...继续其他查找...
}

private void next_item_c489(WsaaZpoldwnm wsaa, Pd41pf pd41, ZpoldwnmCache cache) {
    ...处理下一项...
}
```

#### 示例三：循环回跳 → continue

**COBOL：**
```cobol
2070-CHECK-REPRINT SECTION.
2071-CALL-PS01.
    CALL 'PS01CHRIO' USING PS01CHR-PARAMS
    IF PS01CHR-STATUZ NOT = O-K
        GO TO 2075-ES01
    END-IF
    IF CHGSTS NOT = '60'
        MOVE NEXTR TO PS01CHR-FUNCTION
        GO TO 2071-CALL-PS01
    END-IF
2075-ES01.
    EXIT.
```

**Java（参考项目翻译）：**
```java
private void check_reprint_2070(WsaaZpoldwnm wsaa, ZpoldwnmCache cache) {
    ...初始化...
    List<Ps01pf> ps01chrList = ps01pfRepository.findPs01Chr(ps01chr);
    if (ps01chrList != null) {
        for (Ps01pf ps01chr : ps01chrList) {
            if (!"60".equals(ps01chr.getChgsts())) {
                continue;  // GO TO 2071-CALL-PS01（NEXTR）
            }
            ...处理命中逻辑...
        }
    }
    // 2075-ES01 → 方法结束，自然退出
}
```

关键变化：**BEGN+NEXTR 自跳循环**被吸收为 `for(Rec r : list)` 循环，
内部的 `GO TO 2071-CALL-PS01` 自然变成 `continue;`。

#### 示例四：复杂的段落跳转 → 提取方法

**COBOL：**
```cobol
4500-PRINT-DETAIL SECTION.
4510-CP.
    ...
    IF 条件A
        GO TO 4580-EXIT
    END-IF
    ...
    IF 条件B
        GO TO 4510-CSV
    END-IF
    ...
    
4510-CSV.
    ...CSV 处理...
    
4580-EXIT.
    EXIT.
```

**Java（参考项目翻译）：**
```java
private void print_detail_4500(WsaaZpoldwnm wsaa, ...) {
    ...
    if (条件A) {
        return;  // GO TO 4580-EXIT
    }
    ...
    if (条件B) {
        csv_4510(wsaa, ...);  // GO TO 4510-CSV → 提取方法
        return;
    }
    ...
}

private void csv_4510(WsaaZpoldwnm wsaa, ...) {
    ...CSV 处理...
}
```

---

## 二、段落提取规则

### 何时提取为独立方法

1. **被多个 PERFORM 或 GO TO 引用的 paragraph** → 提取为方法
2. **在 THRU 区间内被 GO TO 跳转的 paragraph** → 提取为方法（合成区间方法内）
3. **EXIT paragraph** → 不提取，用 `return;` 替代

### 方法命名规则

```
C489-NEXT-ITEM  →  next_item_c489
2071-CALL-PS01  →  call_ps01_2071
4510-CSV        →  csv_4510
```

### 方法签名

提取的方法统一接收 wsaa 上下文 + 所需参数：

```java
// 原方法
private void check_reprint_2070(WsaaZpoldwnm wsaa, ZpoldwnmCache cache) {
    ...
    next_item_c489(wsaa, pd41, cache);  // GO TO C489-NEXT-ITEM
    return;
}

// 提取的方法
private void next_item_c489(WsaaZpoldwnm wsaa, Pd41pf pd41, ZpoldwnmCache cache) {
    ...
}
```

---

## 三、与状态机方案的对比

| 方案 | 优点 | 缺点 |
|------|------|------|
| **while+switch 状态机**（旧方案） | 自动生成、无需解析引用 | 代码冗余、可读性差、每段一个状态机 |
| **段落提取为方法**（参考项目方案） | 代码整洁、可读性强、与方法调用模式一致 | 需要解析 paragraph 引用、需处理参数传递 |
