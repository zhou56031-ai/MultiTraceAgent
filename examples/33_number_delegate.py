"""通过真实 HTTP/WebSocket 验证主图委派数字助手。"""

import asyncio
import json
import os
import re
import uuid

import httpx
from websockets.asyncio.client import connect


async def main() -> None:
    thread_id = str(uuid.uuid4())
    port = os.getenv("LEARNING_HOST_PORT", "8001")
    assistant_seen = False
    tool_seen = False
    answer = ""

    async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
        async with connect(f"ws://127.0.0.1:{port}/ws/{thread_id}", proxy=None) as socket:
            response = await client.post(
                f"http://127.0.0.1:{port}/api/task",
                json={
                    "thread_id": thread_id,
                    "query": (
                        "请委派数字统计助手，用工具计算 10,20,30 的数量、合计和平均值。"
                        "按“数量=…；合计=…；平均值=…”报告，不生成文件。"
                    ),
                },
            )
            response.raise_for_status()
            assert response.json()["thread_id"] == thread_id
            async with asyncio.timeout(120):
                while True:
                    event = json.loads(await socket.recv())
                    if event.get("type") != "monitor_event":
                        continue
                    kind = event.get("event")
                    data = event.get("data", {})
                    if kind == "assistant_call":
                        assistant_seen |= data.get("assistant_name") == "数字统计助手"
                    elif kind == "tool_start":
                        tool_seen |= data.get("tool_name") == "sum_numbers"
                    elif kind in {"error", "task_cancelled"}:
                        raise RuntimeError(f"数字任务未完成：{kind}，{data.get('detail', '')}")
                    elif kind == "task_result":
                        answer = str(data.get("result", ""))
                        break

    assert assistant_seen, "主模型没有委派数字助手"
    assert tool_seen, "数字助手没有调用求和工具"
    normalized = re.sub(r"[\s*`]", "", answer).replace(";", "；").rstrip("。")
    expected_format = r"数量=3(?:\.0+)?；合计=60(?:\.0+)?；平均值=20(?:\.0+)?"
    assert re.fullmatch(expected_format, normalized), answer
    print("会话编号：", thread_id)
    print("已观察到：委派数字统计助手 → sum_numbers → 最终答案")
    print("第四子助手真实委派通过：", answer[:200])


if __name__ == "__main__":
    asyncio.run(main())
