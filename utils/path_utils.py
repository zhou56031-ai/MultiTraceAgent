from pathlib import Path
from api.context import get_session_context


def resolve_session_file(filename: str) -> Path:
    session_dir = get_session_context()
    if session_dir is None:
        raise RuntimeError("当前任务没有会话目录")
    if not filename or not filename.strip():
        raise ValueError("文件名不能为空")

    relative = Path(filename)
    if relative.is_absolute():
        raise ValueError("只接受相对路径")

    base = Path(session_dir).resolve()
    candidate = (base / relative).resolve()
    if candidate == base or not candidate.is_relative_to(base):
        raise ValueError("文件必须位于当前会话目录内")
    return candidate
