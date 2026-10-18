import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agent.main_agent import agent_runtime, run_deep_agent
from api.context import set_thread_context, reset_session_context, set_session_context
from api.evidence import EvidenceRegistry, set_evidence, reset_evidence, set_task_id, reset_task_id
from api.monitor import manager, monitor
from api.task_store import TaskStore, TaskConflict

running_tasks: set[asyncio.Task] = set()
project_root = Path(__file__).resolve().parent.parent
upload_root = project_root / "updated"
output_root = project_root / "output"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
task_store = TaskStore(project_root / "data" / "tasks.db")
static_dir = Path(__file__).resolve().parent / "static"


def session_folder(root: Path, thread_id: uuid.UUID) -> Path:
    return root / f"session_{thread_id}"


def safe_output_file(thread_id: uuid.UUID, filename: str) -> Path:
    base = session_folder(output_root, thread_id).resolve()
    relative = Path(filename)
    if not filename or relative.is_absolute():
        raise HTTPException(400, "文件名无效")
    target = (base / relative).resolve()
    if target == base or not target.is_relative_to(base):
        raise HTTPException(400, "文件路径越界")
    return target

@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(task_store.initialize)
    await asyncio.to_thread(task_store.recover_interrupted)
    manager.set_loop(asyncio.get_running_loop())
    monitor.set_websocket_manager(manager)
    try:
        async with agent_runtime():
            try:
                yield
            finally:
                for task in list(running_tasks):
                    task.cancel()
                if running_tasks:
                    await asyncio.gather(*running_tasks, return_exceptions=True)
    finally:
        monitor.set_websocket_manager(None)
        manager.loop = None


app = FastAPI(title="TraceAgent Lab · 多智能体研究工作台", lifespan=lifespan)


@app.websocket("/ws/{thread_id}")
async def websocket_endpoint(websocket: WebSocket, thread_id: uuid.UUID):
    key = str(thread_id)
    await manager.connect(websocket, key)
    try:
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, key)


class TaskRequest(BaseModel):
    query: str = Field(min_length=1, max_length=20000)
    thread_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None


async def execute_task(query: str, thread_id: str, task_id: str) -> None:
    registry = EvidenceRegistry()
    evidence_token = set_evidence(registry)
    task_token = set_task_id(task_id)
    thread_token = set_thread_context(thread_id)
    session_token = set_session_context(str(session_folder(output_root, uuid.UUID(thread_id))))
    try:
        try:
            await asyncio.to_thread(task_store.mark_running, task_id)
            answer = await run_deep_agent(query, thread_id, report_outcome=False)
        except asyncio.CancelledError:
            await asyncio.to_thread(task_store.finish, task_id, "cancelled", sources=registry.snapshot())
            monitor.report_task_cancelled()
            raise
        except Exception as exc:
            # 只保存异常类型，避免把原始凭据或请求正文存进对外任务记录。
            await asyncio.to_thread(task_store.finish, task_id, "failed", error=type(exc).__name__, sources=registry.snapshot())
            monitor.report_error(type(exc).__name__)
        else:
            # 成功落库放在else，提交阶段的取消/错误不再被误报成模型执行失败。
            # 已开始的SQLite线程仍会完成事务；即使通知未发出，也能通过HTTP查回。
            await asyncio.to_thread(task_store.finish, task_id, "succeeded", result=answer, sources=registry.snapshot())
            monitor.report_sources(registry.snapshot())
            monitor.report_task_result(answer)
    finally:
        reset_session_context(session_token, thread_token)
        reset_task_id(task_token)
        reset_evidence(evidence_token)

@app.get("/")
async def home():
    return FileResponse(static_dir / "index.html")



@app.post("/api/task", status_code=202)
async def submit_task(request: TaskRequest) -> dict:
    thread_id = str(request.thread_id or uuid.uuid4())
    task_id = str(request.task_id or uuid.uuid4())
    query = request.query.strip()
    if not query:
        raise HTTPException(422, "问题不能为空")
    try:
        record, created = await asyncio.to_thread(task_store.create, task_id, thread_id, query)
    except TaskConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    if created:
        task = asyncio.create_task(execute_task(query, thread_id, task_id))
        running_tasks.add(task)
        task.add_done_callback(running_tasks.discard)
    return {"status": "started" if created else record["status"], "thread_id": thread_id,
            "task_id": task_id, "created": created}


@app.get("/api/tasks")
async def list_tasks(thread_id: uuid.UUID) -> dict:
    records = await asyncio.to_thread(task_store.list_for_thread, str(thread_id))
    return {"tasks": records}


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: uuid.UUID, thread_id: uuid.UUID) -> dict:
    record = await asyncio.to_thread(task_store.get, str(task_id), str(thread_id))
    if record is None:
        raise HTTPException(404, "任务不存在或不属于当前会话")
    return record

@app.post("/api/upload")
async def upload_file(
    thread_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
) -> dict:
    raw_name = file.filename or ""
    if (
        not raw_name or raw_name in {".", ".."}
        or "/" in raw_name or "\\" in raw_name
    ):
        raise HTTPException(400, "只接受单个文件名")

    folder = session_folder(upload_root, thread_id)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / raw_name
    temporary = None
    size = 0
    try:
        with NamedTemporaryFile(
            mode="wb", dir=folder, prefix=".upload-", delete=False
        ) as output:
            temporary = Path(output.name)
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "文件超过 10 MB")
                output.write(chunk)
        os.replace(temporary, target)
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    return {"status": "uploaded", "filename": raw_name}


@app.get("/api/files")
async def list_files(thread_id: uuid.UUID) -> dict:
    folder = session_folder(output_root, thread_id).resolve()
    if not folder.exists():
        return {"files": []}
    files = []
    for path in folder.rglob("*"):
        if path.is_file() and path.resolve().is_relative_to(folder):
            files.append({
                "name": str(path.relative_to(folder)),
                "size": path.stat().st_size,
            })
    return {"files": files}


@app.get("/api/download")
async def download_file(thread_id: uuid.UUID, filename: str):
    target = safe_output_file(thread_id, filename)
    if not target.is_file():
        raise HTTPException(404, "文件不存在")
    return FileResponse(target, filename=target.name)

