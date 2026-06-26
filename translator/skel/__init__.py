"""
相3 骨架装配公用底座（skeleton-assembly shared layer）—— 与 translator/leaf/ 平行。

用途：把旧 rules.py 的**骨架装配**逻辑（过程拓扑解析、合成区间方法登记、状态机降级…）
      逐块下沉为公用纯函数底座，旧 rules 与相3 asg.visitor 共调同一份 → 产物逐字符一致。
对应设计：docs/详细设计/步骤24A-绞杀项4骨架装配①out-of-line-PERFORM迁visitor设计.md。
设计思路：leaf/ 管「单条语句 → Java 片段、无程序级副作用」；skel/ 管「跨过程装配 + 程序级副作用
      （如 pending_range_methods 登记）」。依赖单向 rules→skel、asg.visitor→skel，skel 不反向 import，无环。

用法示例：
    from translator.skel import render_perform_call
    lines = render_perform_call(header, hu, target, ctx, indent)   # out-of-line PERFORM 调用体
"""
from translator.skel.context import SkelCtx
from translator.skel.perform_call import render_perform_call
from translator.skel.flow_dispatch import (
    render_flow_dispatch, dispatch_goto, dispatch_exit,
)
from translator.skel.io_rewrite import (
    rewrite_io_paras, NodeAccess, STMT_ACCESS,                  # 24C BEGN/READR/WRITE IO 形态吸收
)

__all__ = [
    "SkelCtx", "render_perform_call",
    "render_flow_dispatch", "dispatch_goto", "dispatch_exit",   # 24B GO TO dispatch 状态机
    "rewrite_io_paras", "NodeAccess", "STMT_ACCESS",            # 24C IO 形态吸收
]
