import os
from pathlib import Path

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

env_file = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_file)


def build_model():
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model_name = os.getenv("LLM_QWEN_MAX")

    if not api_key or not base_url or not model_name:
        raise RuntimeError("请检查 .env 中的 DeepSeek 三项配置")

    return init_chat_model(
        model=model_name,
        model_provider="openai",
        api_key=api_key,
        base_url=base_url,
        extra_body={"thinking": {"type": "disabled"}},
    )


model = build_model()


