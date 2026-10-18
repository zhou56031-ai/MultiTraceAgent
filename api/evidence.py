"""一次任务共用的来源登记册；子助手与同步工具通过 ContextVar 取得它。"""

from contextvars import ContextVar
from copy import deepcopy
from threading import Lock
from urllib.parse import quote, urlsplit

_evidence: ContextVar["EvidenceRegistry | None"] = ContextVar("evidence", default=None)
_task_id: ContextVar[str | None] = ContextVar("task_id", default=None)


class EvidenceRegistry:
    def __init__(self) -> None:
        self._sources: list[dict] = []
        self._keys: dict[tuple, str] = {}
        self._lock = Lock()

    def add(self, kind: str, key: tuple, data: dict) -> dict:
        # 多个并行子助手可能在不同工具线程中登记；编号必须在锁内生成。
        with self._lock:
            identity = (kind, *key)
            if identity in self._keys:
                return deepcopy(next(s for s in self._sources if s["id"] == self._keys[identity]))
            prefix = "S" if kind == "web" else "F"
            number = 1 + sum(source["kind"] == kind for source in self._sources)
            source = {**deepcopy(data), "id": f"{prefix}{number}", "kind": kind}
            self._keys[identity] = source["id"]
            self._sources.append(source)
            return deepcopy(source)

    def snapshot(self) -> list[dict]:
        with self._lock:
            return deepcopy(self._sources)


def get_evidence() -> EvidenceRegistry | None:
    return _evidence.get()#_evidence 是个contextvar，get()方法返回当前上下文中_evidence的值，如果没有设置，则返回默认值None。   


def set_evidence(registry: EvidenceRegistry):
    return _evidence.set(registry)


def reset_evidence(token) -> None:
    _evidence.reset(token)


def set_task_id(task_id: str):
    return _task_id.set(task_id)


def reset_task_id(token) -> None:
    _task_id.reset(token)


def get_task_id() -> str | None:
    return _task_id.get()


def safe_web_url(value: str) -> str | None:
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
            return None
        if any(ord(char) < 32 for char in value):
            return None
        return quote(value, safe=":/?#[]@!$&'*+,;=%~.-_")
    except ValueError:
        return None


def append_source_references(content: str, sources: list[dict] | None = None) -> str:
    """只附上实际工具登记的目录，不声称来源能自动证明模型的每条结论。"""
    if sources is None:
        registry = get_evidence()
        sources = registry.snapshot() if registry else []
    if not sources:
        return content
    lines = ["## 本次工具来源", "", "以下是本次工具实际取得的资料；引用仍需对照原文核查。", ""]
    for source in sources:
        label = source["id"]
        title = str(source.get("title") or source.get("filename") or "资料").replace("\n", " ")
        title = title.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
        url = safe_web_url(str(source.get("url", "")))
        if source["kind"] == "web" and url:
            lines.append(f"- [{label}] [{title}]({url})")
        else:
            lines.append(f"- [{label}] {title}：{source.get('scope', '读取范围未记录')}")
    # 按本次登记册重建附录，避免模型或前一次调用留下过期的来源目录。
    body = content.split("\n\n## 本次工具来源\n", 1)[0]
    return body.rstrip() + "\n\n" + "\n".join(lines) + "\n"
