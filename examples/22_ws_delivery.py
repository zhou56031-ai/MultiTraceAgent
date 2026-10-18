import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from api.monitor import ConnectionManager


class FakeWebSocket:
    def __init__(self):
        self.sent = []
        self.closed = False

    async def accept(self):
        pass

    async def send_json(self, payload):
        self.sent.append(payload)

    async def close(self):
        self.closed = True


async def main():
    manager = ConnectionManager()
    old_a, new_a, b = FakeWebSocket(), FakeWebSocket(), FakeWebSocket()
    await manager.connect(old_a, "A")
    await manager.connect(b, "B")
    await manager.connect(new_a, "A")
    manager.disconnect(old_a, "A")
    assert old_a.closed
    assert manager.active_connections["A"] is new_a
    assert await manager.send_to_thread({"event": "搜索开始"}, "A")
    assert new_a.sent == [{"event": "搜索开始"}]
    assert b.sent == []
    assert not await manager.send_to_thread({}, "C")
    print("新连接接班、会话隔离、缺席连接三项通过")


asyncio.run(main())
