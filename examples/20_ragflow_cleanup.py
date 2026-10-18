import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.ragflow_tools import ask_chat_and_cleanup


class FakeSession:
    id = "temporary-S"

    def __init__(self, fail: bool):
        self.fail = fail

    def ask(self, question: str, stream: bool):
        if self.fail:
            raise RuntimeError("模拟提问失败")
        yield SimpleNamespace(content="退款期限是七天")


class FakeChat:
    def __init__(self, fail: bool):
        self.fail = fail
        self.deleted = []

    def create_session(self, name: str):
        return FakeSession(self.fail)

    def delete_sessions(self, ids: list[str]):
        self.deleted.extend(ids)


success = FakeChat(fail=False)
assert "七天" in ask_chat_and_cleanup(success, "如何退款")
assert success.deleted == ["temporary-S"]

failure = FakeChat(fail=True)
try:
    ask_chat_and_cleanup(failure, "如何退款")
except RuntimeError:
    pass
else:
    raise AssertionError("预期提问失败")
assert failure.deleted == ["temporary-S"]
print("成功和提问失败两条路线都清理了临时会话")
