"""真实SQLite账本：编号、并发保护、状态持久化、重启恢复。"""
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from api.task_store import TaskStore, TaskConflict


def main():
    with TemporaryDirectory() as directory:
        path = Path(directory) / "tasks.db"
        store = TaskStore(path)
        store.initialize()
        thread = str(uuid.uuid4())
        task = str(uuid.uuid4())
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(lambda _: store.create(task, thread, "原问题"), range(4)))
        assert sum(created for _, created in responses) == 1
        try:
            store.create(str(uuid.uuid4()), thread, "同会话的另一个问题")
            raise AssertionError("未阻止同会话并发任务")
        except TaskConflict:
            pass
        try:
            store.create(task, thread, "修改原问题")
            raise AssertionError("编号被错误复用")
        except TaskConflict:
            pass
        store.mark_running(task)
        store.finish(task, "succeeded", result="持久化答案", sources=[{"id": "S1", "kind": "web", "url": "https://example.org"}])
        store.finish(task, "failed", error="晚到的失败")
        reopened = TaskStore(path)
        assert reopened.get(task, thread)["result"] == "持久化答案"
        assert reopened.get(task, "别人的会话") is None
        abandoned = str(uuid.uuid4())
        reopened.create(abandoned, thread, "中断的任务")
        assert reopened.recover_interrupted() == 1
        assert reopened.get(abandoned, thread)["status"] == "interrupted"
        assert reopened.get(task, thread)["status"] == "succeeded"
    print("通过：4路相同请求只创建一次、同会话并发拒绝、编号冲突、终态不倒退、重开找回答案、会话隔离、重启中断标记")


if __name__ == "__main__":
    main()
