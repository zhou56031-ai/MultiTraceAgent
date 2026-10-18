import asyncio
import json
import os
import uuid

import httpx
import websockets


async def main() -> None:
    thread_id = str(uuid.uuid4())
    port = os.getenv("MULTIAGENT_TEST_PORT", "8001")
    base = f"http://127.0.0.1:{port}"
    filename = "开篇.txt"
    content = "这是一份练习文本"

    async with httpx.AsyncClient(trust_env=False) as client:
        upload = await client.post(
            base + "/api/upload",
            data={"thread_id": thread_id},
            files={"file": (filename, content.encode("utf-8"))},
        )
        upload.raise_for_status()
        print("上传：", upload.json())

        before = await client.get(base + "/api/files", params={"thread_id": thread_id})
        before.raise_for_status()
        print("提交前的输出文件：", before.json())

        async with websockets.connect(
            f"ws://127.0.0.1:{port}/ws/{thread_id}", proxy=None
        ) as socket:
            submitted = await client.post(
                base + "/api/task",
                json={"thread_id": thread_id, "query": "请读取上传文件并复述"},
            )
            submitted.raise_for_status()
            print("提交：", submitted.json())

            final_event = None
            async with asyncio.timeout(120):
                while True:
                    event = json.loads(await socket.recv())
                    print("进度：", event.get("event"), event.get("message"))
                    if event.get("event") in {"task_result", "error"}:
                        final_event = event
                        break

        after = await client.get(base + "/api/files", params={"thread_id": thread_id})
        after.raise_for_status()
        print("任务后的输出文件：", after.json())
        assert filename in {item["name"] for item in after.json()["files"]}

        download = await client.get(
            base + "/api/download",
            params={"thread_id": thread_id, "filename": filename},
        )
        download.raise_for_status()
        assert download.content.decode("utf-8") == content
        print("下载正文核对通过：", download.text)

        if final_event["event"] == "error":
            raise RuntimeError(f"Agent 执行失败：{final_event['data']['detail']}")
        print("Agent 最终结果：", final_event["data"]["result"])


asyncio.run(main())
