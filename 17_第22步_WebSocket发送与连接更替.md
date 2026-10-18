# 第 22 步：WebSocket 通知要送达当前连接

## 本步要解决的问题

第 12 步保存了“会话编号 → WebSocket”的映射。A 的网页刷新后，会出现旧连接 A1 与新连接 A2 短暂交替；旧连接的清理不能误删新连接。另一个容易误会的地方是 `create_task(send_to_thread(...))`：它只安排发送，实际 `send_json` 可能稍后失败。本步分别照看“发给谁”和“发出去是否报错”。

具体例子：A1 已连接，网页刷新建立 A2。服务器给 A 发送“搜索开始”；应该交给 A2。随后 A1 的断开清理运行，字典里仍应保留 A2。B 的连接始终不受影响。这是本地假 WebSocket 实验，不要求浏览器或外部大模型。

这个例子要求客户端**复用同一个会话编号 A**。当前 `index.html` 整页刷新会清空内存中的会话 Map，再创建新 UUID；它尚未实现“刷新后恢复同一会话”。本步验证的是服务端同编号连接更替，不宣称网页已有自动恢复功能。

## 文件与依赖

- **修改 learning/api/monitor.py → ConnectionManager.connect() 与 ToolMonitor._emit()**：前者替换同编号旧连接；后者为已安排的发送任务安装完成回调，记录失败类型。`send_to_thread()` 继续返回 `bool`：找到连接并调用 `send_json` 才返回 `True`；没有连接返回 `False`。
- **修改 learning/api/static/index.html → openSession()**：连接关闭时及时改变网页状态，不让“已连接”永久留在界面。
- **新建 learning/examples/22_ws_delivery.py**：用假 WebSocket 验证 A1/A2 更替和缺席会话的返回值；文件只放在 `examples/`。
- **依赖**：只用已有 FastAPI、Python `asyncio`，`requirements.txt` 不变。外层目录执行 `learning/.venv/bin/python -c 'from fastapi import WebSocket; print("WebSocket 类型可用")'` 可检查环境。

## 1. 让 ConnectionManager 的“接班”可观察

在 **learning/api/monitor.py → ConnectionManager.connect()** 中，先找到当前的旧函数：

~~~python
    async def connect(self, websocket: WebSocket, thread_id: str) -> None:
        await websocket.accept()
        self.active_connections[thread_id] = websocket
~~~

**替换后**，整个 `connect()` 应为：

~~~python
    async def connect(self, websocket: WebSocket, thread_id: str) -> None:
        await websocket.accept()
        previous = self.active_connections.get(thread_id)
        self.active_connections[thread_id] = websocket
        if previous is not None and previous is not websocket:
            try:
                await previous.close()
            except RuntimeError:
                pass
~~~

对照看：原来 `accept()` 后直接把新连接写进字典；现在先把旧连接保存到 `previous`，再登记新连接，最后尝试关闭旧连接。`disconnect()` 不在本次替换范围内，保留它原有的对象身份判断。

`thread_id` 是网页会话 UUID 字符串，不是操作系统线程。`previous` 是字典里原来登记的 WebSocket 对象；`websocket` 是新请求的对象。先让新连接 `accept` 成功，才把字典指向它；旧连接关闭失败也不抹掉新连接。原有 `disconnect(websocket, thread_id)` 中的 `if self.active_connections.get(thread_id) is websocket` **保留**，因为 A1 的关闭回调晚到时，它会发现字典现在指向 A2，于是不删除 A2。

这里的 `is` 比较的是**两个变量是否指向同一个 WebSocket 对象**。A1 和 A2 即使用同一会话编号，仍是两个不同对象。`send_to_thread` 只查当前字典，因此刷新后会发送给 A2。连接替换也没有补发 A1 断线期间错过的旧事件；这个实验不能声称支持离线消息回放。

## 2. 观察已安排发送的真实结果

在 **learning/api/monitor.py → ToolMonitor 类**中，`_emit()` 前新增：

~~~python
    @staticmethod
    def _observe_delivery(future) -> None:
        if future.cancelled():
            return
        try:
            delivered = future.result()
        except Exception as exc:
            print(f"[Monitor] WebSocket 发送失败：{type(exc).__name__}")
        else:
            if not delivered:
                print("[Monitor] 当前会话没有 WebSocket 连接")
~~~

`future` 是“已安排的发送工作”：同一事件循环时为 `asyncio.Task`，跨线程提交时为线程安全 Future。两者完成后都能调用 `result()`。`delivered=False` 表示根本没找到该会话连接；抛异常则表示发送过程失败。这个完成回调只记录情况，不改变 `_emit` 的返回值，也不让任务结果自动重发。

仍在同文件，找到 `ToolMonitor._emit()` 末尾目前的旧代码：

~~~python
            if current_loop is manager.loop:
                current_loop.create_task(coroutine)
            else:
                asyncio.run_coroutine_threadsafe(coroutine, manager.loop)
~~~

**替换后**，这几行应为：

~~~python
            if current_loop is manager.loop:
                delivery = current_loop.create_task(coroutine)
            else:
                delivery = asyncio.run_coroutine_threadsafe(coroutine, manager.loop)
            delivery.add_done_callback(self._observe_delivery)
~~~

对照看：两条分支仍按原来的规则安排发送；新代码把安排好的任务保存到 `delivery`，随后给它添加完成回调，才能知道发送最后是成功、失败还是没有对应连接。

其余 `payload` 构造、`thread_id = get_thread_context()`、取当前 loop 的 `try/except`、原 `return payload` 都保留。`manager.loop` 来自 `learning/api/server.py → lifespan()` 启动时的 `asyncio.get_running_loop()`，指向服务处理 WebSocket 的调度循环。`current_loop` 是当前执行 `_emit` 时所在线程能拿到的循环；同一个循环用 `create_task`，其他线程用 `run_coroutine_threadsafe` 投递回服务循环。`add_done_callback` 在发送任务**结束后**才检查结果。`_emit` 自己依旧立即返回事件字典，不等网页收到。

## 3. 网页不要显示过期连接状态

在 **learning/api/static/index.html → openSession()** 中，现有 `socket.onerror = ...` 后、`socket.onmessage = ...` 前加入：

~~~javascript
socket.onclose = () => {
  if (session.socket !== socket) return;
  if (session.status === "已连接" || session.status === "运行中") {
    session.status = "连接已断开";
  }
  if (currentId === id) render();
};
~~~

`session.socket` 保存当前会话连接对象，`socket` 是本次回调所属对象；两者不相同表示这是旧连接的晚到事件。已完成的任务不因连接关闭被改成失败。这里只**显示断线**，还没有自动重连或补发，下一次真实联调要明确此限制。

## 4. 新建 learning/examples/22_ws_delivery.py

~~~python
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
~~~

运行 `learning/.venv/bin/python learning/examples/22_ws_delivery.py`。验证的是管理器逻辑，未用真实网络；真实浏览器若要验证同编号接班，需在客户端显式复用 A 的 UUID，而当前网页整页刷新默认会创建新编号。理解检查：为什么 `manager.disconnect(old_a, "A")` 之后，A 仍然有连接？

