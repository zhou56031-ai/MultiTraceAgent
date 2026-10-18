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
