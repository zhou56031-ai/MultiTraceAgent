# 第 37 步 · 独立任务编号与SQLite账本

> 上一步：[第36步](31_第36步_网页来源编号与报告引用.md) · 下一步：[第38步](33_第38步_任务查询接口与持久化结果.md)  
> 总入口：[从零复刻阅读导航](从零复刻阅读导航.md) · 本轮改造基线：2026-10-17  
> 当前成品已经包含这些修改。本页供你在自己的练习副本逐步复刻，不要反复把运行中的成品替换回旧版。

## 1. 为什么需要第二种编号

小明的会话编号是A。第一次问“查市场趋势”得到任务T1，第二次问“生成报告”得到T2。A负责把整段对话连在一起，T1/T2分别标识一次执行。

以前仅返回A，浏览器断线后无法明确查询“第一次问的问题到底完成没有”。本步先建立任务账本，不改WebSocket，也不让模型重新执行。任务账本保存受理记录、状态、最终答案和来源元数据；图检查点仍保存多轮对话状态，两者职责不同。

## 2. 文件与依赖

| 路径 | 动作和职责 |
| --- | --- |
| `learning/api/task_store.py` | 新建，用sqlite3实现任务创建、查询、状态结束和重启标记；第38步API调用它 |
| `learning/data/tasks.db` | 运行时自动创建，不手写，不提交Git；与checkpoints.db是两个数据库文件 |
| `learning/examples/37_task_store.py` | 新建，使用临时真实SQLite验证去重、并发与持久化 |

sqlite3、contextmanager、datetime、pathlib、json都是Python标准库，不执行 `pip install sqlite3`，也不新增requirements条目。在**外层目录**检查：

```bash
learning/.venv/bin/python -c 'import sqlite3; print("SQLite版本", sqlite3.sqlite_version)'
```

## 3. 建立正式账本模块

### 新建 `learning/api/task_store.py`

这是本步完整文件，写入以下内容：

```python
"""任务账本与图检查点分开保存：前者供HTTP查询，后者供智能体继续对话。"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ACTIVE_STATUSES = ("queued", "running")
TERMINAL_STATUSES = ("succeeded", "failed", "cancelled", "interrupted")


class TaskConflict(ValueError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, query TEXT NOT NULL,
                status TEXT NOT NULL, result TEXT, error TEXT,
                sources_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS tasks_thread ON tasks(thread_id, created_at)")
            conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS tasks_one_active
                ON tasks(thread_id) WHERE status IN ('queued', 'running')""")

    @staticmethod
    def decode(row) -> dict | None:
        if row is None:
            return None
        record = dict(row)
        record["sources"] = json.loads(record.pop("sources_json"))
        return record

    def create(self, task_id: str, thread_id: str, query: str) -> tuple[dict, bool]:
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            if existing is not None:
                if existing["thread_id"] != thread_id or existing["query"] != query:
                    raise TaskConflict("该 task_id 已用于其他请求，请生成新的任务编号")
                return self.decode(existing), False
            timestamp = now()
            try:
                conn.execute("""INSERT INTO tasks
                    (task_id, thread_id, query, status, created_at, updated_at)
                    VALUES (?, ?, ?, 'queued', ?, ?)""", (task_id, thread_id, query, timestamp, timestamp))
            except sqlite3.IntegrityError as exc:
                raise TaskConflict("当前会话已有未结束的任务，请等待完成或新建会话") from exc
            return self.decode(conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()), True

    def get(self, task_id: str, thread_id: str) -> dict | None:
        with self.connection() as conn:
            return self.decode(conn.execute("SELECT * FROM tasks WHERE task_id = ? AND thread_id = ?",
                                            (task_id, thread_id)).fetchone())

    def list_for_thread(self, thread_id: str, limit: int = 20) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM tasks WHERE thread_id = ? ORDER BY created_at DESC, rowid DESC LIMIT ?",
                                (thread_id, limit)).fetchall()
            return [self.decode(row) for row in rows]

    def mark_running(self, task_id: str) -> None:
        with self.connection() as conn:
            conn.execute("UPDATE tasks SET status = 'running', updated_at = ? WHERE task_id = ? AND status = 'queued'",
                         (now(), task_id))

    def finish(self, task_id: str, status: str, *, result: str | None = None,
               error: str | None = None, sources: list[dict] | None = None) -> None:
        if status not in TERMINAL_STATUSES:
            raise ValueError("finish 只接受终态")
        with self.connection() as conn:
            conn.execute("""UPDATE tasks SET status = ?, result = ?, error = ?, sources_json = ?, updated_at = ?
                WHERE task_id = ? AND status IN ('queued', 'running')""",
                         (status, result, error, json.dumps(sources or [], ensure_ascii=False), now(), task_id))

    def recover_interrupted(self) -> int:
        # 单进程服务重启后，旧协程已不存在，不能假装它仍在运行或已经自动续跑。
        with self.connection() as conn:
            cursor = conn.execute("""UPDATE tasks SET status = 'interrupted', error = ?, updated_at = ?
                WHERE status IN ('queued', 'running')""",
                                  ("服务重启，执行已中断；请用新的 task_id 重试", now()))
            return cursor.rowcount
```

## 4. 用一笔任务看懂数据表

| 字段 | 示例 | 为什么保存 |
| --- | --- | --- |
| task_id | T1的UUID字符串 | 一次请求的唯一身份，也是防止重复执行的键 |
| thread_id | A的UUID字符串 | 把任务归到会话；查询时与task_id一起限制 |
| query | 用户这次原问题 | 刷新后能重建问题；重复编号时核对请求是否相同 |
| status | queued/running/succeeded等 | 告诉前端已受理、正在跑还是结束 |
| result | 最终答案，未完成为None | 无WebSocket也能找回 |
| error | ValueError或中断说明 | 对外保存可识别原因，避免保存原始凭据异常 |
| sources_json | 来源元数据的JSON字符串 | SQLite存文字，查询时还原为sources列表 |
| created_at/updated_at | UTC时间字符串 | 展示顺序、状态更新时间 |

这里T1/A是讲解用简称，正式API仍使用UUID。`None` 对应“目前没有结果”，不是空答案成功。

## 5. 每个函数为什么存在、谁调用

| 函数 | 调用者、输入、执行与返回 |
| --- | --- |
| `now()` | 写状态时调用，返回UTC时间字符串；不读取用户机器的聊天内容 |
| `__init__(path)` | 服务器创建TaskStore时调用，只保存数据库路径，暂不建表 |
| `connection()` | 每个数据库方法使用：打开连接→在事务里执行→成功提交/失败回滚→finally关闭连接 |
| `initialize()` | lifespan启动时调用，创建目录、表与索引；已有数据保留 |
| `decode(row)` | 查询后调用，把Row转dict，把sources_json解析成sources；没找到时返回None |
| `create(task_id, thread_id, query)` | POST接口调用；返回(record, created)，created=False时不应再次启动图 |
| `get(task_id, thread_id)` | 单任务查询调用，两个编号同时匹配才返回记录 |
| `list_for_thread(thread_id, limit=20)` | 恢复页面与列表接口调用，返回最近20条；完整历史不在本步一次拉取 |
| `mark_running(task_id)` | 后台开始执行前调用，只把queued改为running |
| `finish(task_id, status, ...)` | 任务完成、失败或取消时调用，只允许写终态；已是终态不再覆盖 |
| `recover_interrupted()` | 单进程服务启动时调用，把上次残留queued/running改成interrupted并返回条数 |

`@contextmanager` 与你学过的异步上下文管理器有相似的三段：进入时连接，yield把conn交给外部with代码块，退出时回来关闭。这里是同步SQLite，所以使用普通with，而不是async with。真正的异步API会在第38步用to_thread执行这些短数据库操作。

## 6. create 如何防止重复执行

把 `create(T1,A,"查趋势")` 代入：

```text
BEGIN IMMEDIATE：先取得写事务资格
→ 查task_id=T1
→ 没有：尝试插入queued，created=True
→ 已有且会话、问题相同：返回原记录，created=False
→ 已有但问题或会话不同：TaskConflict
```

查询和插入在一个事务里，不给两个并发请求留下“都查到不存在”的空隙。SQL中的问号是参数占位符，真实值经参数绑定传入，不把用户问题拼成SQL。

主键阻止同一个task_id出现两次；部分唯一索引 `tasks_one_active` 进一步保证同一个thread_id最多存在一条queued/running。小明的A任务还没结束时，新T2会冲突；小红的B不受影响。这个约束也保护同一会话的图检查点，避免两轮任务并行写乱。

`TaskConflict` 是我们定义的异常类型，第38步把它转成HTTP409。它不同于模型执行失败，冲突时根本不应该再请求模型。

## 7. 状态变化与重启的真实含义

```text
queued → running → succeeded / failed / cancelled
queued/running → 服务进程退出后仍残留 → 下次启动标记interrupted
```

成功答案已写入时，晚来的finish(failed)不会覆盖它。interrupted不表示已经自动续跑；图检查点存在也不等于进程里的协程能跨重启继续。用户需要用新的task_id明确重试。

本实现用于单个应用进程，启动时会认领并中断旧运行态。不要直接加 `--workers 4`，否则一个新进程可能把另一个进程的正常任务当成遗留任务。多进程需要额外的执行租约或队列，不在本步实现。

## 8. 验证真实SQLite行为

### 新建 `learning/examples/37_task_store.py`

这是本步完整文件，写入以下内容：

```python
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
```

线程池同时提交四次相同编号，created=True只能出现一次。测试还会重新实例化TaskStore读取同一个文件，证明结果来自磁盘；这不只是同一个对象内存里还留着变量。

从**外层目录**运行：

```bash
learning/.venv/bin/python learning/examples/37_task_store.py
```

本次已通过，无外部API调用。练习：如果T1已经成功，再用相同T1/A/原问题提交，应该新执行还是返回原记录？为什么更换问题时必须换task_id？
