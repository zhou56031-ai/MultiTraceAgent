"""
当多个用户或多个 Agent 任务同时运行时，如何让每个任务都能方便地获取属于自己的会话目录和线程 ID，同时避免不同任务之间的数据相互干扰？

"""



from contextvars import ContextVar, Token

_session_dir: ContextVar[str | None] = ContextVar("session_dir", default=None)
_thread_id: ContextVar[str | None] = ContextVar("thread_id", default=None)


def set_session_context(path: str) -> Token:
    return _session_dir.set(path)


def get_session_context() -> str | None:
    return _session_dir.get()


def set_thread_context(thread_id: str) -> Token:
    return _thread_id.set(thread_id)


def get_thread_context() -> str | None:
    return _thread_id.get()


def reset_session_context(session_token: Token, thread_token: Token) -> None:
    _thread_id.reset(thread_token)
    _session_dir.reset(session_token)
