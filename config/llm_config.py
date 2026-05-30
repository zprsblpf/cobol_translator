"""集中式大模型（翻译模型）配置。

url / key / 模型名 / 温度等参数全部从环境变量读取，切换模型只改 .env，
无需改动业务代码。默认值与原先写死的本地 vLLM 行为一致，因此不配置也能照常跑。

环境变量（在项目根目录 .env 中配置）：
    LLM_BASE_URL             接口地址（OpenAI 兼容）        默认 http://localhost:8000/v1
    LLM_API_KEY              接口密钥                       默认 dummy（本地 vLLM 占位即可）
    LLM_MODEL                模型名；留空则自动探测          默认 空 → 探测 {BASE_URL}/models
    LLM_MODEL_FALLBACK       探测失败时兜底模型名            默认 qwen3-8b-GPTQ
    LLM_TEMPERATURE          采样温度                       默认 0
    LLM_MAX_TOKENS           最大输出 token                 默认 4096
    LLM_MAX_THINKING_TOKENS  思考预算（vLLM 扩展字段）       默认 2048
    LLM_TIMEOUT              请求超时（秒）                  默认 120

切换模型示例（改 .env 即可）：
    # 切到云端 OpenAI 兼容服务
    LLM_BASE_URL=https://api.openai.com/v1
    LLM_API_KEY=sk-xxxx
    LLM_MODEL=gpt-4o
"""
import os
from functools import lru_cache

try:  # 自动加载项目根目录 .env（已装 python-dotenv 时）
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # pragma: no cover
    pass


def _env(name: str, default=None):
    val = os.getenv(name)
    return val if val not in (None, "") else default


def get_llm_config() -> dict:
    """读取当前生效的大模型配置（环境变量优先，回退到与原写死值一致的默认）。"""
    base_url = _env("LLM_BASE_URL", "http://localhost:8000/v1").rstrip("/")
    return {
        "base_url": base_url,
        "api_key": _env("LLM_API_KEY", "dummy"),
        "model": _env("LLM_MODEL"),  # 空 → resolve_model() 自动探测
        "model_fallback": _env("LLM_MODEL_FALLBACK", "qwen3-8b-GPTQ"),
        "temperature": float(_env("LLM_TEMPERATURE", "0")),
        "max_tokens": int(_env("LLM_MAX_TOKENS", "4096")),
        "max_thinking_tokens": int(_env("LLM_MAX_THINKING_TOKENS", "2048")),
        "timeout": float(_env("LLM_TIMEOUT", "120")),
    }


def auth_headers(cfg: dict | None = None) -> dict:
    """Bearer 鉴权头。"""
    cfg = cfg or get_llm_config()
    return {"Authorization": f"Bearer {cfg['api_key']}"}


def resolve_model(cfg: dict | None = None) -> str:
    """返回模型名：LLM_MODEL 显式配置优先；留空则探测 {BASE_URL}/models，失败用兜底。"""
    cfg = cfg or get_llm_config()
    if cfg["model"]:
        return cfg["model"]
    try:
        import requests
        resp = requests.get(f"{cfg['base_url']}/models",
                            headers=auth_headers(cfg), timeout=5)
        data = resp.json().get("data", [])
        if data:
            return data[0]["id"]
    except Exception:
        pass
    return cfg["model_fallback"]


@lru_cache(maxsize=None)
def get_llm():
    """LangChain Chat 模型（OpenAI 兼容端点），供需要 langchain 接口的路径复用。"""
    from langchain_openai import ChatOpenAI
    cfg = get_llm_config()
    return ChatOpenAI(
        model=resolve_model(cfg),
        base_url=cfg["base_url"],
        api_key=cfg["api_key"],
        temperature=cfg["temperature"],
        max_tokens=cfg["max_tokens"],
    )
