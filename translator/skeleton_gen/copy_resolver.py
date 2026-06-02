"""
COPY 角色解析：copies → 服务依赖 / 实体引用 / 常量（步骤05 §6.2）。

用途：调 spec_loader.copy_role 把 COPY 清单按角色分流，产出渲染层需要的依赖信息：
      - service  → 服务类字段（构造器注入），(类名, 字段名)；
      - entity   → 实体类引用（本轮仅引用、不生成实体本体），COBOL名 → Java类名；
      - constant → 常量拷贝簿名（保持字面量，不建数据名）。
对应设计：docs/详细设计/步骤05-cob到Java翻译引擎详细设计.md（§4：实体类仅引用）。

设计思路：实体类多在其它包/由 COPY 展开生成，本引擎无法确定其全限定名，故**不产出 import 语句**，
          仅在主类 doc 注释中登记「COBOL名→Java类名」以便追溯（诚实边界）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from config import spec_loader


@dataclass
class CopyResolution:
    """COPY 分流结果。"""
    services: list[tuple[str, str]] = field(default_factory=list)  # (类名, 字段名)
    entities: dict[str, str] = field(default_factory=dict)         # COBOL名 → Java类名
    constants: list[str] = field(default_factory=list)             # 常量拷贝簿名


def resolve(copies: list[str]) -> CopyResolution:
    """按角色分流 COPY 清单。"""
    res = CopyResolution()
    for c in copies:
        role = spec_loader.copy_role(c)
        if role == "service":
            res.services.append((spec_loader.service_class(c), spec_loader.service_field(c)))
        elif role == "entity":
            res.entities[c.upper()] = spec_loader.entity_class(c)
        else:
            res.constants.append(c)
    return res
