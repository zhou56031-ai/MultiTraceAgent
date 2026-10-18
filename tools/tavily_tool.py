import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from langchain_core.tools import tool
from tavily import TavilyClient

from api.monitor import monitor
from api.evidence import EvidenceRegistry, get_evidence, safe_web_url

from requests.exceptions import ConnectionError as RequestConnectionError
from requests.exceptions import Timeout as RequestTimeout
from tavily.errors import TimeoutError as TavilyTimeoutError
from utils.retry import retry_with_backoff


env_file = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_file)

api_key = os.getenv("TAVILY_API_KEY")
if not api_key:
    raise RuntimeError("请检查 .env 中的 TAVILY_API_KEY")

client = TavilyClient(api_key=api_key)

@retry_with_backoff(
    max_retries=2,
    base_delay=0.2,
    max_delay=2.0,
    exceptions=(TavilyTimeoutError, RequestTimeout, RequestConnectionError),
)#这里会把search_web 这个函数传入retry_with_backoff 装饰器，装饰器会返回一个新的函数，这个新的函数会在调用时进行重试逻辑。
def search_web(
    query: str,
    topic: Literal["general", "news", "finance"] = "general",
    max_results: int = 3,
    include_raw_content: bool = False,
) -> dict:
    return client.search(
        query=query,
        topic=topic,
        max_results=max_results,
        include_raw_content=include_raw_content,
    )






@tool
def internet_search(
    query: str,
    topic: Literal["general", "news", "finance"] = "general",
    max_results: int = 3,
    include_raw_content: bool = False,
) -> dict:
    """搜索公开网页，返回搜索结果及其来源。"""
    monitor.report_tool("internet_search", {"query": query})
    response = search_web(query, topic, max_results, include_raw_content)
    registry = get_evidence() or EvidenceRegistry()
    results = []
    for item in response.get("results", []):
        url = safe_web_url(str(item.get("url", "")))
        if url is None:
            continue
        source = registry.add("web", (url,), {"title": str(item.get("title") or url)[:300], "url": url})
        results.append({**item, "url": url, "source_id": source["id"], "citation": f"[{source['id']}]"})
    monitor.report_sources(registry.snapshot())
    return {**response, "results": results,
            "source_instruction": "结论引用实际来源编号如 [S1] 并保留网址；不得编造来源或把搜索摘要当作已读全文。"}
