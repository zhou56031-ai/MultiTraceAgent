from pathlib import Path
from langchain_core.tools import tool
from api.monitor import monitor
from api.evidence import append_source_references
from utils.path_utils import resolve_session_file


@tool
def generate_markdown(content: str, filename: str) -> str:
    """把 content 保存为当前会话目录中的 Markdown 文件。"""
    if not content.strip():
        return "错误：文档内容不能为空"
    name = filename if filename.endswith(".md") else filename + ".md"
    try:
        target = resolve_session_file(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        monitor.report_tool("generate_markdown", {"filename": target.name})
        target.write_text(append_source_references(content), encoding="utf-8")
        return f"已生成 Markdown 文件：{target.name}"
    except (ValueError, RuntimeError, OSError) as exc:
        return f"生成失败：{exc}"
