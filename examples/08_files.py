import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from api.context import set_session_context, set_thread_context, reset_session_context
from tools.markdown_tools import generate_markdown
from tools.upload_file_read_tool import read_file_content

folder = root / "output" / "session_demo"
folder.mkdir(parents=True, exist_ok=True)
path_token = set_session_context(str(folder))
id_token = set_thread_context("demo")
try:
    print(generate_markdown.invoke({
        "content": "# A 的笔记\n今天学会了文件隔离。",
        "filename": "notes/report",
    }))
    print(read_file_content.invoke({"filename": "notes/report.md"}))
    print(read_file_content.invoke({"filename": "../session_B/secret.txt"}))
finally:
    reset_session_context(path_token, id_token)
