import os
import sys
from pathlib import Path

import markdown

# macOS 上让 WeasyPrint 找到 Homebrew 安装的 Pango/GLib 动态库。
if sys.platform == "darwin":
    homebrew_lib = Path("/opt/homebrew/lib")
    if homebrew_lib.is_dir():
        library_paths = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "").split(":")
        if str(homebrew_lib) not in library_paths:
            os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join(
                [str(homebrew_lib), *(path for path in library_paths if path)]
            )

from weasyprint import HTML


def deny_external_resource(url: str, **kwargs):
    raise ValueError("PDF 转换不读取外部资源")


def render_pdf(md_path: Path, pdf_path: Path) -> None:
    """读取 Markdown，生成 PDF 文件；失败时抛出异常。"""
    source = md_path.read_text(encoding="utf-8")
    body = markdown.markdown(source, extensions=["tables", "fenced_code"])
    html = (
        '<meta charset="utf-8">'
        '<style>body { font-family: sans-serif; line-height: 1.6; }'
        'table { border-collapse: collapse; }'
        'td, th { border: 1px solid #888; padding: 6px; }</style>'
        + body
    )
    HTML(string=html, url_fetcher=deny_external_resource).write_pdf(pdf_path)
