"""
统一日志设施：把"处理流程日志"与"LLM 沟通日志"分成两个独立通道。

- flow 通道（logger 名 `cobol.flow`）：清晰展示流水线各节点的处理流程
  （① 解析 → ② 骨架 → ③ 翻译各段 → ④ 组装），每条带阶段标记，便于跟踪进度。
- llm  通道（logger 名 `cobol.llm`）：**单独展示**每次与本地 LLM 的沟通，
  完整打印入参（system / user prompt）与出参（response）及耗时。

两个 logger 互不传播到 root，各自挂自己的 handler：
  - flow → 控制台
  - llm  → 控制台（带醒目分隔块）+ 可选独立文件（logs/llm_io.log）

设计为零外部依赖（仅标准库 logging），`setup_logging()` 幂等，可在入口安全多次调用。
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

FLOW_LOGGER = "cobol.flow"
LLM_LOGGER = "cobol.llm"

_CONFIGURED = False


class _ChannelFormatter(logging.Formatter):
    """统一格式：`HH:MM:SS │ <通道> │ <消息>`，通道标签固定宽度便于对齐。"""

    def __init__(self, channel: str):
        super().__init__(datefmt="%H:%M:%S")
        self._channel = channel

    def format(self, record: logging.LogRecord) -> str:
        ts = self.formatTime(record, self.datefmt)
        msg = record.getMessage()
        if record.exc_info:
            msg = msg + "\n" + self.formatException(record.exc_info)
        prefix = f"{ts} │ {self._channel:<4} │ "
        # 多行消息：每行都补通道前缀，视觉上归属清晰
        return "\n".join(prefix + line for line in msg.split("\n"))


def setup_logging(level: int = logging.INFO,
                  llm_level: int = logging.INFO,
                  log_dir: str | Path | None = None,
                  to_file: bool = True,
                  to_console: bool = True) -> None:
    """
    配置 flow / llm 两个独立通道，并落到**各自独立的日志文件**。幂等：重复调用直接返回。

    参数:
      level       flow 通道级别（默认 INFO；--verbose 时传 DEBUG）
      llm_level   llm 通道级别
      log_dir     日志文件目录（默认 cobol_translator/logs）
      to_file     是否落盘：py 处理流程 → flow.log；大模型沟通 → llm_io.log
      to_console  是否同时输出到控制台

    落盘文件：
      logs/flow.log    —— py 处理流程日志（节点 ①②③④）
      logs/llm_io.log  —— 大模型沟通日志（入参 system/user prompt + 出参 response）
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    d = Path(log_dir) if log_dir else Path(__file__).parent / "logs"
    if to_file:
        d.mkdir(parents=True, exist_ok=True)
    file_fmt = logging.Formatter(
        "%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    # ── flow 通道（py 处理流程）──────────────────────────────────
    flow = logging.getLogger(FLOW_LOGGER)
    flow.setLevel(level)
    flow.propagate = False
    if to_console:
        fh = logging.StreamHandler(sys.stdout)
        fh.setFormatter(_ChannelFormatter("FLOW"))
        flow.addHandler(fh)
    if to_file:
        flow_file = logging.FileHandler(d / "flow.log", encoding="utf-8")
        flow_file.setFormatter(file_fmt)
        flow.addHandler(flow_file)

    # ── llm 通道（大模型沟通，与 flow 分离，单独落文件）─────────────
    llm = logging.getLogger(LLM_LOGGER)
    llm.setLevel(llm_level)
    llm.propagate = False
    if to_console:
        lh = logging.StreamHandler(sys.stdout)
        lh.setFormatter(_ChannelFormatter("LLM"))
        llm.addHandler(lh)
    if to_file:
        llm_file = logging.FileHandler(d / "llm_io.log", encoding="utf-8")
        llm_file.setFormatter(file_fmt)
        llm.addHandler(llm_file)

    _CONFIGURED = True


def get_flow_logger() -> logging.Logger:
    """流程通道 logger。setup_logging 未调用时退化为标准 logging（不报错）。"""
    return logging.getLogger(FLOW_LOGGER)


def get_llm_logger() -> logging.Logger:
    return logging.getLogger(LLM_LOGGER)


def _indent(text: str, mark: str = "    ") -> str:
    text = (text or "").rstrip("\n")
    if not text:
        return mark + "(空)"
    return "\n".join(mark + line for line in text.split("\n"))


def log_llm_request(scene: str, system_prompt: str, user_prompt: str,
                    model: str = "") -> float:
    """
    打印一次 LLM 调用的入参（system + user prompt）。返回起始时间戳，
    供 log_llm_response 计算耗时。
    """
    log = get_llm_logger()
    log.info("╭── LLM 请求 ─ 场景: %s ─ 模型: %s", scene or "?", model or "?")
    log.info("│ ▼ 入参 system_prompt:\n%s", _indent(system_prompt))
    log.info("│ ▼ 入参 user_prompt:\n%s", _indent(user_prompt))
    log.info("│ … 等待响应 …")
    return time.time()


def log_llm_response(scene: str, response: str, started_at: float = 0.0) -> None:
    """打印一次 LLM 调用的出参（response）与耗时。"""
    log = get_llm_logger()
    elapsed = (time.time() - started_at) if started_at else 0.0
    log.info("│ ▲ 出参 response (耗时 %.2fs, %d 字符):\n%s",
             elapsed, len(response or ""), _indent(response))
    log.info("╰── LLM 完成 ─ 场景: %s", scene or "?")


def log_llm_error(scene: str, error: Exception, started_at: float = 0.0) -> None:
    log = get_llm_logger()
    elapsed = (time.time() - started_at) if started_at else 0.0
    log.error("│ ✖ LLM 调用失败 (耗时 %.2fs): %s", elapsed, error)
    log.error("╰── LLM 中断 ─ 场景: %s", scene or "?")
