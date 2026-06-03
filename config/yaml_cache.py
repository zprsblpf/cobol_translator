"""
config.yaml_cache —— 项目唯一的 YAML 读取 + 缓存入口（步骤09 §4.1）。

用途：把散落各处的 `open + yaml.safe_load(+lru_cache)` 收口到一处。访问层（spec_loader /
      grammar_loader）与外部模块一律经本函数取 yaml，不再自定义加载器、不再各自持有 CONFIG_DIR。
对应设计：docs/详细设计/步骤09-config配置层重构设计.md §4.1。

设计：调用方只给**裸文件名**（如 "type_mappings.yaml"），由本函数在 config/ 根及
      specs/、mappings/ 子目录按序解析。如此规范文件的物理归位（分层）对调用方透明，
      目录调整无需改任何业务代码——单一入口、低耦合。

用法：
    from config.yaml_cache import load
    load("skeleton_spec.yaml")     # -> dict（自动定位到 specs/）
    load("type_mappings.yaml")     # -> dict（自动定位到 mappings/）
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

_CONFIG_DIR = Path(__file__).parent
# 解析顺序：根目录优先，其后各分层子目录（新增层级目录在此登记即可）
_SEARCH_DIRS = ("", "specs", "mappings")


@lru_cache(maxsize=None)
def load(name: str) -> dict:
    """加载并缓存一个 config yaml（按裸文件名在根/specs/mappings 解析）。缺失返回 {}。"""
    for sub in _SEARCH_DIRS:
        path = _CONFIG_DIR / sub / name if sub else _CONFIG_DIR / name
        if path.is_file():
            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    return {}
