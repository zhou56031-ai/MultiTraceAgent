import os
from pathlib import Path
from dotenv import load_dotenv


def get_ragflow_config() -> tuple[str, str]:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    api_key = os.getenv("RAGFLOW_API_KEY")
    base_url = os.getenv("RAGFLOW_API_URL")
    if not api_key or not base_url:
        raise RuntimeError("缺少 RAGFlow 配置")
    return api_key, base_url
