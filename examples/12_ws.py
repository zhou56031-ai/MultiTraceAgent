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
