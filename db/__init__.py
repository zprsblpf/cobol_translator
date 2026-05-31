"""
数据访问层（DB Access Layer）。

对应设计文档：docs/详细设计/步骤02-MongoDB入库实现与输出目录调整设计.md（Block A）。
本包封装对外部存储的访问，目前仅含 MongoDB 封装 `MongoStore`。
pymongo 在 `MongoStore.__init__` 内惰性导入，未入库时本包零外部依赖。
"""
from .mongo_client import MongoStore

__all__ = ["MongoStore"]
