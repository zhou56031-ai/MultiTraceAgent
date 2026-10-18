import time
from functools import wraps


def retry_with_backoff(
    max_retries: int = 2,
    base_delay: float = 0.2,
    max_delay: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (TimeoutError,),
):
    """只对指定异常重试同步函数；max_retries 不含首次调用。"""
    if max_retries < 0 or base_delay < 0 or max_delay < 0:
        raise ValueError("重试次数和等待时间不能为负数")

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = base_delay
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions:
                    if attempt == max_retries:
                        raise
                    print(f"[重试] {func.__name__} 第 {attempt + 1} 次失败")
                    time.sleep(delay)
                    delay = min(delay * 2, max_delay)

        return wrapper

    return decorator
