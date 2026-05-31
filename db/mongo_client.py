"""
MongoDB 访问封装。

对应设计文档：docs/详细设计/步骤02-MongoDB入库实现与输出目录调整设计.md（§3 Block A）。

设计思路
- 薄封装：只暴露 decompose/importer.py 实际调用的 5 个方法，不多造接口（复用优先）。
- 惰性导入 pymongo：仅在构造 MongoStore 时 import，纯文件模式（不入库）零依赖。
- 幂等 upsert：$set 刷新结构字段，$setOnInsert 仅首插写 created_at + 预留分析字段，
  保证重跑不覆盖后续步骤回填的 logic/java_code 等成果。

用法
    store = MongoStore(uri="mongodb://.../", db_name="cobol")
    store.ensure_unique_index("ZPOLDWNM", ["program", "block_name"])
    res = store.upsert("ZPOLDWNM", core, key=("program", "block_name"),
                       set_on_insert=set_on_insert)   # -> "inserted"|"updated"|"unchanged"
    n = store.count("ZPOLDWNM", {"program": "ZPOLDWNM"})
    store.close()
"""
from __future__ import annotations

from datetime import datetime, timezone


class MongoStore:
    """对 MongoDB 的薄封装，供拆解结果幂等入库使用。"""

    def __init__(self, uri: str, db_name: str) -> None:
        """连接 MongoDB 并验证连通性（连不上立即抛异常；不内置默认连接串）。"""
        import pymongo  # 惰性导入：纯文件模式不依赖 pymongo
        self.client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=5000)
        self.client.admin.command("ping")  # 主动探活，连接失败在此抛出
        self.db = self.client[db_name]

    def ensure_unique_index(self, coll: str, keys: list[str]) -> None:
        """对 keys 建复合唯一索引（升序）。幂等：同结构重复调用无副作用。"""
        self.db[coll].create_index([(k, 1) for k in keys], unique=True)

    def upsert(self, coll: str, doc: dict, key: tuple[str, ...],
               set_on_insert: dict) -> str:
        """按 key 幂等 upsert 一条文档，返回 'inserted'/'updated'/'unchanged'。

        doc 只含结构字段，set_on_insert 只含预留分析字段（调用方已拆分）。
        """
        flt = {k: doc[k] for k in key}
        now = datetime.now(timezone.utc)
        update = {
            "$set": {**doc, "updated_at": now},               # 结构字段每次刷新
            "$setOnInsert": {**set_on_insert, "created_at": now},  # 仅首插，保护回填字段
        }
        res = self.db[coll].update_one(flt, update, upsert=True)
        if res.upserted_id is not None:
            return "inserted"
        if res.modified_count:
            return "updated"
        return "unchanged"

    def count(self, coll: str, filt: dict) -> int:
        """统计满足 filt 的文档数（入库后打印「该程序共 N 块」用）。"""
        return self.db[coll].count_documents(filt)

    def close(self) -> None:
        """释放连接。"""
        self.client.close()
