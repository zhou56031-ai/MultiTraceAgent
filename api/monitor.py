from datetime import datetime
from typing import Any


import asyncio
from fastapi import WebSocket
from api.context import get_thread_context
from api.evidence import get_task_id


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[str, WebSocket] = {}#websocket 的作用是建立一个持久的连接，允许客户端和服务器之间进行实时通信。它可以在不重新加载页面的情况下发送和接收数据，从而实现即时更新和交互。
        self.loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    async def connect(self, websocket: WebSocket, thread_id: str) -> None:
        await websocket.accept()
        previous = self.active_connections.get(thread_id)
        self.active_connections[thread_id] = websocket
        if previous is not None and previous is not websocket:
            try:
                await previous.close()
            except RuntimeError:
                pass

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


class ToolMonitor:
    def __init__(self) -> None:
        self.websocket_manager = None

    def set_websocket_manager(self, manager) -> None:
        self.websocket_manager = manager

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

    def _emit(
        self, event: str, message: str, data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        payload = {
            "type": "monitor_event",
            "event": event,
            "message": message,
            "data": data or {},
            "timestamp": datetime.now().isoformat(),
            "task_id": get_task_id(),
        }
        print(f"[Monitor:{event}] {message}")
        manager = self.websocket_manager
        thread_id = get_thread_context()
        if manager is not None and manager.loop is not None and thread_id:
            coroutine = manager.send_to_thread(payload, thread_id)
            try:
                current_loop = asyncio.get_running_loop()
            except RuntimeError:
                current_loop = None

            if current_loop is manager.loop:
                delivery = current_loop.create_task(coroutine)
            else:
                delivery = asyncio.run_coroutine_threadsafe(coroutine, manager.loop)
            delivery.add_done_callback(self._observe_delivery)
        return payload

    def report_session_dir(self, path: str) -> dict[str, Any]:
        return self._emit("session_created", "工作目录已创建", {"path": path})

    def report_assistant(
        self, name: str, description: str
    ) -> dict[str, Any]:
        return self._emit(
            "assistant_call", f"正在调用助手：{name}",
            {"assistant_name": name, "description": description},
        )

    def report_tool(self, name: str, args: dict) -> dict[str, Any]:
        return self._emit(
            "tool_start", f"开始执行工具：{name}",
            {"tool_name": name, "args": args},
        )

    def report_task_result(self, result: str) -> dict[str, Any]:
        return self._emit(
            "task_result", "任务执行完成", {"result": result},
        )
    def report_task_cancelled(self) -> dict[str, Any]:
        return self._emit("task_cancelled", "任务已取消")

    def report_sources(self, sources: list[dict]) -> dict[str, Any]:
        return self._emit("source_update", "资料来源与读取范围已更新", {"sources": sources})

    def report_error(self, message: str) -> dict[str, Any]:
        return self._emit("error", "任务执行失败", {"detail": message})


monitor = ToolMonitor()
