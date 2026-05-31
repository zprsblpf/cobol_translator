"""
入库编排（输出 B，后补）。

职责：读 manifest.json，将每块幂等 upsert 进 MongoDB；仅在显式传 --mongo-uri 时调用。
依赖 db/mongo_client.py 的 MongoStore（其内部惰性导入 pymongo）。
对应设计文档：步骤02 §3.3 幂等写入规则。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def import_mongo(manifest_path: Path, uri: str, db: str, coll: str) -> dict:
    """读 manifest.json，幂等 upsert 入库（设计文档 §6）。仅在显式传 --mongo-uri 时调用。"""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from db.mongo_client import MongoStore
        store = MongoStore(uri=uri, db_name=db)
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"无法连接 MongoDB：{e!r}") from e

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    docs = manifest["documents"]
    store.ensure_unique_index(coll, ["program", "block_name"])

    reserved = {"params_in", "params_out", "calls", "logic", "java_code"}
    stats = {"inserted": 0, "updated": 0, "unchanged": 0}
    for d in docs:
        d = {k: v for k, v in d.items() if k not in ("created_at", "updated_at")}
        set_on_insert = {k: d.get(k) for k in reserved}
        core = {k: v for k, v in d.items() if k not in reserved}
        res = store.upsert(coll, core, key=("program", "block_name"),
                           set_on_insert=set_on_insert)
        stats[res] += 1
    total = store.count(coll, {"program": manifest["program"]})
    store.close()
    stats["total_in_db"] = total
    return stats
