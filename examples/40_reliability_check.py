"""真实HTTP/SQLite/正式主任务函数，模拟图与搜索；不调用外部API。

直接运行做后端验收；--serve 启动临时验收服务供浏览器脚本使用。
"""
import asyncio
import os
import shutil
import sys
import time
import uuid
from contextlib import asynccontextmanager, ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for key, value in {
    "OPENAI_API_KEY": "offline-test-placeholder", "TAVILY_API_KEY": "offline-test-placeholder",
    "OPENAI_BASE_URL": "https://example.invalid/v1", "LLM_QWEN_MAX": "offline-test-model",
}.items():
    os.environ[key] = value

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
import agent.main_agent as runtime
import api.server as server
from api.context import get_session_context
from api.task_store import TaskStore
from tools.tavily_tool import client, internet_search
from tools.upload_file_read_tool import read_file_content
from tools.markdown_tools import generate_markdown


class FixtureGraph:
    """只替换不确定的模型决策，目录、工具、上下文、持久化都执行正式代码。"""
    def __init__(self):
        self.executions = 0

    async def astream(self, state, **kwargs):
        self.executions += 1
        query = state["messages"][0]["content"]
        if "wait" in query:
            await asyncio.sleep(30)
        if "slow" in query or "恢复验收" in query:
            await asyncio.sleep(1)
        if "fail" in query:
            raise ValueError("模拟失败")
        await asyncio.to_thread(internet_search.invoke, {"query": "模拟来源检索"})
        folder = Path(get_session_context())
        for file in sorted(folder.glob("*.txt")):
            await asyncio.to_thread(read_file_content.invoke, {"filename": file.name})
        await asyncio.to_thread(generate_markdown.invoke, {"filename": "验收报告", "content": "# 离线模拟报告\n结论使用模拟搜索资料 [S1]。"})
        yield {"model": {"messages": [AIMessage(content="离线模拟答案：任务结果可以找回，资料见 [S1]；文件读取范围见来源面板。") ]}}


@asynccontextmanager
async def fake_runtime():
    yield runtime.main_agent


def fixture(root: Path, graph: FixtureGraph):
    stack = ExitStack()
    for target, name, value in [
        (server, "task_store", TaskStore(root / "data/tasks.db")),
        (server, "upload_root", root / "updated"), (server, "output_root", root / "output"),
        (server, "agent_runtime", fake_runtime),
        (runtime, "project_root_path", root), (runtime, "main_agent", graph),
    ]:
        stack.enter_context(patch.object(target, name, value))
    stack.enter_context(patch.object(client, "search", return_value={"results": [
        {"title": "模拟来源", "url": "https://example.org/reliability", "content": "仅供离线验收的模拟摘要"},
    ]}))
    # 禁止真实出网。TestClient走进程内ASGI；--serve只需本机接受浏览器连接。
    stack.enter_context(patch("socket.socket.connect", side_effect=RuntimeError("离线验收禁止出网")))
    return stack


def wait_for(client: TestClient, thread: str, task: str, expected: str) -> dict:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        response = client.get(f"/api/tasks/{task}", params={"thread_id": thread})
        response.raise_for_status()
        record = response.json()
        if record["status"] == expected:
            return record
        if record["status"] in {"failed", "cancelled", "interrupted"}:
            raise AssertionError(record)
        time.sleep(0.03)
    raise AssertionError("等待持久化状态超时")


def main():
    with TemporaryDirectory(prefix="learning-reliability-") as directory:
        root = Path(directory)
        graph = FixtureGraph()
        with fixture(root, graph):
            if "--serve" in sys.argv:
                import uvicorn
                print("模拟验收服务：http://127.0.0.1:8012；退出后清理全部临时数据", flush=True)
                uvicorn.run(server.app, host="127.0.0.1", port=8012, log_level="warning")
                return
            thread, task = str(uuid.uuid4()), str(uuid.uuid4())
            with TestClient(server.app) as client_api:
                uploaded = client_api.post("/api/upload", data={"thread_id": thread},
                                           files={"file": ("长文.txt", ("恢复验收\n" + "甲" * 13000).encode())})
                assert uploaded.status_code == 200
                body = {"query": "slow 恢复验收", "thread_id": thread, "task_id": task}
                submitted = client_api.post("/api/task", json=body)
                assert submitted.status_code == 202 and submitted.json()["created"]
                repeated = client_api.post("/api/task", json=body)
                assert not repeated.json()["created"]
                assert client_api.post("/api/task", json={**body, "task_id": str(uuid.uuid4())}).status_code == 409
                assert client_api.post("/api/task", json={**body, "query": "换一个问题"}).status_code == 409
                # 不连接WebSocket也能完成并找回结果。
                record = wait_for(client_api, thread, task, "succeeded")
                assert graph.executions == 1
                assert "本次工具来源" in record["result"] and "[S1]" in record["result"] and "[F1]" in record["result"]
                file_source = next(s for s in record["sources"] if s["kind"] == "file")
                assert file_source["char_truncated"] and file_source["returned_chars"] == 12000
                assert "仅供离线验收的模拟摘要" not in str(record["sources"])
                assert client_api.get(f"/api/tasks/{task}", params={"thread_id": str(uuid.uuid4())}).status_code == 404
                report = client_api.get("/api/download", params={"thread_id": thread, "filename": "验收报告.md"})
                assert report.status_code == 200 and "https://example.org/reliability" in report.text
                failed = client_api.post("/api/task", json={"query": "fail", "thread_id": thread}).json()["task_id"]
                assert wait_for(client_api, thread, failed, "failed")["error"] == "ValueError"
                cancelled = client_api.post("/api/task", json={"query": "wait", "thread_id": thread}).json()["task_id"]
            # 退出lifespan取消后台任务，结果落库。
            store = TaskStore(root / "data/tasks.db")
            assert store.get(cancelled, thread)["status"] == "cancelled"
            abandoned = str(uuid.uuid4())
            store.create(abandoned, thread, "模拟进程崩溃遗留任务")
            with TestClient(server.app) as reopened:
                assert reopened.get(f"/api/tasks/{task}", params={"thread_id": thread}).json()["result"] == record["result"]
                assert reopened.get(f"/api/tasks/{abandoned}", params={"thread_id": thread}).json()["status"] == "interrupted"
                assert reopened.get("/api/tasks", params={"thread_id": thread}).status_code == 200
    print("通过：HTTP受理与幂等、同会话并发保护、无WebSocket找回答案、真实工具来源/范围/报告、失败与取消、服务重开及崩溃遗留标记；图与搜索为模拟")


if __name__ == "__main__":
    main()
