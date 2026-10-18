# 第 12 步：把通知送到对应网页

## 本步解决什么问题

第 11 步的通知只打印在服务器终端。现在 A 和 B 各打开一条 WebSocket 连接：A 的任务事件只送给 A 的连接，B 的事件只送给 B。WebSocket 是浏览器与服务器持续连接的一条通道，适合接收后台进度。

这里有两张不同的“编号表”：ContextVar 让正在执行的代码知道当前会话编号；连接管理器用这个编号找到对应网页连接。把事件安排到发送队列、真正网络发送完成、浏览器显示出来，是三个时刻。

## 文件与依赖

在 `learning/requirements.txt` 增加 `websockets==15.0.1` 用于示例客户端。修改 `learning/api/monitor.py`、`learning/api/server.py`；新增 `learning/examples/12_ws.py`。

## 先弄清每个文件为什么存在

**`api/monitor.py`：从“打印通知”升级为“按编号找收件人”。**第 11 步已有的事件格式保留；本步在同一文件增加 `ConnectionManager`，用字典保存 `会话编号 → WebSocket连接对象`。`ToolMonitor._emit` 先从 `api/context.py` 取得当前任务编号，再请管理器给对应连接发事件。为什么还要有 ContextVar？因为深处的搜索工具调用 `report_tool` 时没有直接拿到网页连接，也不该自己保存网页对象；它只需知道当前任务编号。

**`api/server.py`：负责建立和结束网络连接。**浏览器请求 `/ws/A` 时，FastAPI 调用这里的 WebSocket 路由，接收连接并登记到 `ConnectionManager`；断开时删除登记。服务启动时，它还把正在运行的事件循环交给管理器，供通知员把发送安排到正确的循环。没有登记，通知员即使知道编号 A，也找不到可发送的网页。

**`examples/12_ws.py`：扮演一个真正连上来的浏览器。**示例先创建编号并建立 WebSocket，再用同一编号向 `/api/task` 提交任务，随后逐条等待收到的事件。它能区分“服务器打印了事件”与“客户端实际收到了事件”；再开两个实例可观察 A/B 是否串台。`requirements.txt` 新增的 `websockets` 主要为这个示例客户端服务，FastAPI/Uvicorn 仍负责服务端。

把本步串起来：`examples/12_ws.py` 连上 A → `api/server.py` 把 A 与连接对象登记到 `api/monitor.py` 的管理器 → A 的 Agent 工具报告事件 → `api/context.py` 给出当前编号 A → 管理器找到 A 的连接并发送 → 示例脚本的 `recv` 真正取到消息。编号是“信封上的收件人”，WebSocket 对象才是“实际投递通道”。

### 1. api/monitor.py：管理连接

修改 `learning/api/monitor.py`：在顶部补充下面的导入，在模块末尾（`ToolMonitor` 类外）增加 `ConnectionManager` 类和 `manager = ConnectionManager()`：

~~~python
import asyncio
from fastapi import WebSocket
from api.context import get_thread_context


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[str, WebSocket] = {}
        self.loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    async def connect(self, websocket: WebSocket, thread_id: str) -> None:
        await websocket.accept()
        self.active_connections[thread_id] = websocket

    def disconnect(self, websocket: WebSocket, thread_id: str) -> None:
        if self.active_connections.get(thread_id) is websocket:
            del self.active_connections[thread_id]

    async def send_to_thread(self, payload: dict, thread_id: str) -> bool:
        websocket = self.active_connections.get(thread_id)
        if websocket is None:
            return False
        await websocket.send_json(payload)
        return True


manager = ConnectionManager()
~~~

`active_connections` 是字典：键是会话编号，值是真正的 WebSocket 对象。`connect` 接受握手后存入；`disconnect` 只有在字典里仍是**同一条连接对象**时才删除，避免 A 重连后旧连接的断开事件误删新连接。`send_to_thread` 先查字典，再发送 JSON；没有连接时返回 `False`，不会自动缓存事件。`loop` 是服务启动时取得的事件循环对象，不是新建的操作系统线程。

### 2. api/monitor.py：扩展第 11 步的 _emit

仍修改 `learning/api/monitor.py`：在 `class ToolMonitor` 的类体内增加 `__init__()` 和 `set_websocket_manager()`：

~~~python
def __init__(self) -> None:
    self.websocket_manager = None

def set_websocket_manager(self, manager) -> None:
    self.websocket_manager = manager
~~~

仍修改 `learning/api/monitor.py`：找到 `ToolMonitor._emit()`，在它构造 `payload` 并打印之后、原来的 `return payload` 之前插入：

~~~python
manager = self.websocket_manager
thread_id = get_thread_context()
if manager is not None and manager.loop is not None and thread_id:
    coroutine = manager.send_to_thread(payload, thread_id)
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if current_loop is manager.loop:
        current_loop.create_task(coroutine)
    else:
        asyncio.run_coroutine_threadsafe(coroutine, manager.loop)
~~~

`self` 是第 11 步创建的 `monitor` 对象。`manager` 是绑定到它的连接管理器；`thread_id` 来自当前任务的 ContextVar。`coroutine` 是“待执行的发送工作”，创建它不等于已经发送。

如果当前代码就在 FastAPI 的服务循环中，`create_task` 在该循环安排发送；如果同步工具在其他线程运行，`run_coroutine_threadsafe` 把发送安排回管理 WebSocket 的服务循环。两者都是**安排**动作；要确认网页确实收到了，需要下面的客户端实验。生产化时还应保留返回的 Task/Future 并检查发送异常；这是第 17 步的失败处理。`create_task` 不会自动开新线程。

### 3. api/server.py：绑定循环并提供连接入口

修改 `learning/api/server.py` 的 `lifespan()`：在原有的 `async with agent_runtime():` 前加入：

~~~python
manager.set_loop(asyncio.get_running_loop())
monitor.set_websocket_manager(manager)
~~~

同一个 `learning/api/server.py` 中，在 `lifespan()` 退出时把 `manager.loop` 重置为 `None`；把下面的导入放到文件顶部。**`@app.websocket(...)` 和整个 `websocket_endpoint()` 函数必须放在 `app = FastAPI(...)` 之后**，例如紧接在那一行之后、`class TaskRequest` 之前。Python 读取装饰器时就需要已经存在的 `app`；若放在 `app = FastAPI(...)` 前面，启动会立即报 `NameError: name 'app' is not defined`，客户端随后也无法完成握手。

~~~python
from fastapi import WebSocket, WebSocketDisconnect
from api.monitor import manager, monitor


@app.websocket("/ws/{thread_id}")
async def websocket_endpoint(websocket: WebSocket, thread_id: uuid.UUID):
    key = str(thread_id)
    await manager.connect(websocket, key)
    try:
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, key)
~~~

FastAPI 在收到连接请求时创建 `websocket` 对象并传进函数；URL 里的 `thread_id` 被解析成 UUID。`connect` 将编号与连接配对。`receive_text` 让函数等待客户端消息或断开，`finally` 保证离开时清理。`ping/pong` 只是连接实验消息，与 Agent 结果无关。

### 4. examples/12_ws.py：先连，再提交

~~~python
import asyncio
import json
import uuid
import httpx
import websockets


async def main():
    thread_id = str(uuid.uuid4())
    url = "ws://127.0.0.1:8001/ws/" + thread_id
    async with websockets.connect(url, proxy=None) as socket:
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.post(
                "http://127.0.0.1:8001/api/task",
                json={
                    "query": "请搜索 Python 官方文档并给来源",
                    "thread_id": thread_id,
                },
            )
            print("提交：", response.json())
        while True:
            event = json.loads(await asyncio.wait_for(socket.recv(), 120))
            print(event.get("event"), event.get("message"))
            if event.get("event") in {"task_result", "error"}:
                break


asyncio.run(main())
~~~

先建立 WebSocket，再 POST 同一个 `thread_id`，避免第一个进度事件在连接建立前丢失。示例只连接本机 `127.0.0.1`，所以 WebSocket 使用 `proxy=None`，HTTPX 使用 `trust_env=False`，避免系统代理接管本机请求。`socket.recv()` 等网页侧收到一条事件；这比服务器打印“准备发送”更能证明传输完成。

## 运行与验收

先按第 10 步启动服务，再运行：

~~~bash
learning/.venv/bin/python learning/examples/12_ws.py
~~~

观察 `session_created`、`assistant_call`、`tool_start`、`task_result`；再开两个脚本实例，确认编号不同、事件不串台。已在 learning 代码上验证 WebSocket 握手、`ping/pong` 和断开清理；涉及真实模型的完整事件链仍需运行服务后观察。
