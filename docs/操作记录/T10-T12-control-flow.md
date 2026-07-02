# T10/T11 条件与控制流基础 + T12 GO TO DEPENDING ON

日期：2026-07-02

## 范围

- 补充独立回归测试 `test_t10_t12_control_flow.py`，覆盖条件表达式 AND/OR 壳、IF then/else 内基础控制词、GO TO DEPENDING ON 保守边界。
- 保留既有 T10/T11 实现，不重写条件翻译或 IF/EVALUATE/基础控制流 visitor。
- 对 `GO TO ... DEPENDING ON ...` 做显式 fallback：输出 `TODO-GOTO-DEPENDING` 和 `return;`，避免按第一个目标生成错误跳转。
- ASG builder 不再为 DEPENDING ON 解析单一 `GotoStmt.target`。
- ASG section 状态机目标收集跳过 DEPENDING ON，避免 dispatch 抢先误译。

## 保守边界

- 本次不实现 indexed dispatch 语义。
- GO TO DEPENDING ON 不生成任一目标调用，也不进入段内状态机 dispatch。
- 普通 GO TO、GOBACK、STOP、EXIT、CONTINUE、NEXT 的既有输出保持不变。

## 验证

- 红测：`python -m unittest test_t10_t12_control_flow -v`，T12 相关 4 个用例失败，显示当前会误译为单目标跳转。
- 绿测：`python -m unittest test_t10_t12_control_flow -v`，6 tests OK。
