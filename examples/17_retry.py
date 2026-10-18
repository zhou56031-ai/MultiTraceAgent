import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.retry import retry_with_backoff

attempts = 0


@retry_with_backoff(max_retries=2, base_delay=0, exceptions=(TimeoutError,))
def pretend_search(query: str) -> str:
    global attempts
    attempts += 1
    if attempts < 3:
        raise TimeoutError("模拟网络超时")
    return f"找到了：{query}"


print(pretend_search("某品牌新品"))
print("总调用次数：", attempts)
assert attempts == 3
