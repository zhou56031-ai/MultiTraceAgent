from langchain_core.tools import tool

from api.monitor import monitor
from utils.path_utils import resolve_session_file
from utils.pdf_converter import render_pdf


@tool
def convert_md_to_pdf(
    md_filename: str, pdf_filename: str | None = None
) -> str:
    """把当前会话中的 Markdown 文件转换为 PDF。"""
    try:
        source = resolve_session_file(md_filename)
        if source.suffix.lower() != ".md" or not source.is_file():
            return "转换失败：源文件必须是已存在的 .md 文件"
        output_name = pdf_filename or source.with_suffix(".pdf").name
        target = resolve_session_file(output_name)
        if target.suffix.lower() != ".pdf":
            return "转换失败：输出文件必须以 .pdf 结尾"
        monitor.report_tool("convert_md_to_pdf", {"filename": target.name})
        render_pdf(source, target)
        return f"已生成 PDF 文件：{target.name}"
    except (ValueError, RuntimeError, OSError) as exc:
        return f"转换失败：{exc}"
    except Exception as exc:
        return f"转换失败：{type(exc).__name__}"
