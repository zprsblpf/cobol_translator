"""
COBOL 拆解功能包。

把整份 .cob 按规则切成独立小块，写文件 + 生成入库数据源（manifest），可选幂等入库 MongoDB。
对应设计文档：docs/详细设计/步骤01-拆解与存库设计.md、步骤02-MongoDB入库实现与输出目录调整设计.md。

模块职责（详见 docs/架构索引/项目总览.md）
- models    : Block 数据结构
- lines     : 行级清洗与有效行判定
- structure : 读取物理行、DIVISION/COPY 结构定位
- blocks    : 切 SECTION、构建 WS/META 块、切片命名
- manifest  : 写切片文件 + manifest.json/md
- importer  : 读 manifest 幂等入库（调 db.mongo_client）
- core      : 顶层编排 decompose()

对外入口：scripts/decompose.py（瘦入口，argparse + 调用）。
"""
from .core import decompose
from .importer import import_mongo

__all__ = ["decompose", "import_mongo"]
