# 第 32 步：刷新网页之后，新连接能接班吗？

## 场景与预期

第 22 步用假 WebSocket 对象验证连接字典；这一步用真实网络连接重演。A 的页面先连上 `ws/A`，刷新后 A2 用相同会话编号连接。预期服务先接受 A2，然后关闭 A1；A2 发 `ping` 仍能收到 `pong`。随后 A1 的断开回调晚到，也不能把 A2 从字典删掉。

还要用真实 HTTP 尝试非法上传文件名：`../escape.txt` 应被拒绝为 400。连接接班和上传拒绝是两个独立结果；前者看 `ConnectionManager`，后者看 `upload_file` 对文件名的检查。

## 文件与依赖

- **新建 `learning/examples/32_network_edges.py`**：真实网络验收入口；正式逻辑仍位于 `learning/api/monitor.py → ConnectionManager.connect()/disconnect()` 与 `learning/api/server.py → upload_file()`。
- **检查 `learning/api/static/index.html`**：浏览器刷新同一会话时，应使用相同 `thread_id` 重新连接；网页是否保留编号，需在浏览器实际操作确认。此步不预设修改 HTML。
- **依赖**：`httpx==0.28.1` 与 `websockets==15.0.1` 已在 `learning/requirements.txt`。从外层目录检查 `learning/.venv/bin/python -c 'import httpx, websockets; print("网络客户端可用")'`；缺失时 `uv pip install --python learning/.venv/bin/python -r learning/requirements.txt`。不需要模型或外部 API Key 回答。

本步没有正式代码替换；下面完整内容放在新文件 `learning/examples/32_network_edges.py`。若实验失败，再根据真实输出修改对应函数，并在修改教程时写出当时真实的旧代码和新代码。

## 写入 `learning/examples/32_network_edges.py`

```python
import asyncio
import json
import os
import uuid

import httpx
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed


async def main():
    thread_id = str(uuid.uuid4())
    port = os.getenv("LEARNING_HOST_PORT", "8001")
    ws_url = f"ws://127.0.0.1:{port}/ws/{thread_id}"
    base = f"http://127.0.0.1:{port}"

    async with connect(ws_url, proxy=None) as first:
        async with connect(ws_url, proxy=None) as second:
            try:
                await asyncio.wait_for(first.recv(), timeout=5)
            except ConnectionClosed:
                print("旧连接 A1 已被服务关闭")
            else:
                raise AssertionError("新连接接班后，旧连接 A1 仍然可收消息")

            await second.send("ping")
            reply = json.loads(await asyncio.wait_for(second.recv(), timeout=5))
            assert reply == {"type": "pong"}
            print("新连接 A2 仍可收发：", reply)

    async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
        response = await client.post(
            base + "/api/upload",
            data={"thread_id": thread_id},
            files={"file": ("../escape.txt", b"should not be written")},
        )
        assert response.status_code == 400, response.status_code
        print("越界样式文件名被拒绝：HTTP", response.status_code)


asyncio.run(main())
```

## 把 A1、A2 对应到实际对象

`first` 是第一个 WebSocket 对象，`second` 是刷新后建立的另一个 WebSocket 对象。它们用同一个 `thread_id`，但在 Python 中不是同一个对象。`active_connections[thread_id]` 一开始指向 A1；A2 连接成功后改指 A2。`connect()` 再关闭 A1。A1 的 `disconnect()` 随后运行时，`is websocket` 比较发现字典里是 A2，不会删掉新连接。

`first.recv()` 在这里等旧连接关闭，因此应抛 `ConnectionClosed`。`wait_for(..., timeout=5)` 防止代码无限卡住；若超时，说明没有观察到预期关闭。`second.send("ping")` 是服务器已有的小型探针：`websocket_endpoint` 收到字符串 `ping`，回复 JSON `{"type":"pong"}`。这个探针不调用模型；它证实 A2 还活着。

上传部分的 `files` 是 HTTP multipart 表单中的文件元数据，`../escape.txt` 是故意构造的非法文件名。正式接口应该在写入前因 `/` 字符拒绝它。这里发送的是本地无害练习内容，预期 HTTP 400。

## 运行与浏览器复查

从外层目录执行 `learning/.venv/bin/python learning/examples/32_network_edges.py`。如果 8001 已占用且容器在 8002，命令前加 `LEARNING_HOST_PORT=8002`。脚本通过只能证明真实 WebSocket 与 HTTP 路由；还要在浏览器打开首页，创建一个会话、刷新、观察会话编号和连接状态是否符合预期。浏览器可能在刷新时重新生成编号，若如此应把它当作新的会话，而不是把脚本里的“同编号接班”误套到页面上。

若 `first.recv()` 没结束，查 `ConnectionManager.connect()` 是否把新连接登记并关闭旧连接。若 A2 收不到 `pong`，查旧连接的 `disconnect()` 是否误删字典里的新对象。理解检查：A1 与 A2 编号相同，为什么 `previous is not websocket` 仍是 `True`？
