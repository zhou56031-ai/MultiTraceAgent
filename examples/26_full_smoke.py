import asyncio
import json
import os
import uuid

import httpx
from websockets.asyncio.client import connect


async def main():
    thread_id = str(uuid.uuid4())
    port = os.getenv("LEARNING_HOST_PORT", "8001")
    base = f"http://127.0.0.1:{port}"
    ws_url = f"ws://127.0.0.1:{port}/ws/{thread_id}"
    seen = []

    async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
        async with connect(ws_url, proxy=None) as socket:
            upload = await client.post(
                base + "/api/upload",
                data={"thread_id": thread_id},
                files={"file": ("规则.txt", "练习代号：蓝色海豚".encode("utf-8"))},
            )
            upload.raise_for_status()
            print("上传状态：", upload.json()["status"])

            submission = await client.post(
                base + "/api/task",
                json={
                    "thread_id": thread_id,
                    "query": "请先用 read_file_content 读取规则.txt，再说出练习代号；不生成文件。",
                },
            )
            submission.raise_for_status()
            assert submission.json()["thread_id"] == thread_id

            async with asyncio.timeout(180):
                while True:
                    event = json.loads(await socket.recv())
                    if event.get("type") != "monitor_event":
                        continue
                    seen.append(event)
                    print("事件：", event.get("event"))
                    if event.get("event") == "error":
                        raise RuntimeError("Agent 执行失败，请看服务端日志")
                    if event.get("event") == "task_result":
                        answer = str(event.get("data", {}).get("result", ""))
                        assert "蓝色海豚" in answer
                        break

            assert any(
                item.get("event") == "tool_start"
                and item.get("data", {}).get("tool_name") == "read_file_content"
                for item in seen
            )
            files = await client.get(
                base + "/api/files", params={"thread_id": thread_id}
            )
            files.raise_for_status()
            assert any(item["name"] == "规则.txt" for item in files.json()["files"])
            print("上传、读取、回答、文件列表四段联调通过")


asyncio.run(main())
