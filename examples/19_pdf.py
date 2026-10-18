import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from api.context import reset_session_context, set_session_context, set_thread_context
from tools.pdf_tools import convert_md_to_pdf

with TemporaryDirectory() as directory:
    folder = Path(directory)
    (folder / "报告.md").write_text("# 中文报告\n\n|项目|值|\n|---|---|\n|订单|3|\n")
    directory_token = set_session_context(str(folder))
    thread_token = set_thread_context("example-19")
    try:
        print(convert_md_to_pdf.invoke({"md_filename": "报告.md"}))
        pdf = folder / "报告.pdf"
        assert pdf.read_bytes().startswith(b"%PDF")
        print("PDF 文件已生成，字节数：", pdf.stat().st_size)
        print("临时 PDF 路径：", pdf)
        input("按回车结束临时目录；先用访达打开 PDF 检查中文和表格。")
    finally:
        reset_session_context(directory_token, thread_token)
