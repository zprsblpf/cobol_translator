"""
config —— 全项目的**规范基座**（步骤09）。

定位：一切翻译都由本包的"规范正本"驱动；本包是最底层，**不依赖任何业务模块**。
结构：
  yaml_cache.py   唯一 YAML 缓存加载入口（所有 yaml 读取经此）
  conversions.py  纯转换函数（命名 / VALUE→初值），供 config 与 parser 共用
  llm_config.py   LLM 运行时基础设施配置（非"规范"）
  specs/          各层级翻译/文法规范正本（切分 / 骨架 / WSAA …）
  mappings/       规范配套的查表映射（类型 / 命名 / COPY / IO）
  grammar_loader  访问层：切分 + 骨架文法
  spec_loader     访问层：翻译规范 + 映射

对应设计：docs/详细设计/步骤09-config配置层重构设计.md。
"""
