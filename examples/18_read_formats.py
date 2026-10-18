import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from docx import Document

from api.context import reset_session_context, set_session_context, set_thread_context
from tools.upload_file_read_tool import read_file_content


with TemporaryDirectory() as directory:
    folder = Path(directory)
    document = Document()
    document.add_paragraph("退货期限为七天")
    document.save(folder / "规则.docx")
    pd.DataFrame({"商品": ["杯子"], "价格": [39]}).to_excel(
        folder / "报价表.xlsx", index=False
    )

    session_token = set_session_context(str(folder))
    thread_token = set_thread_context("example-18")
    try:
        word_text = read_file_content.invoke({"filename": "规则.docx"})
        excel_text = read_file_content.invoke({"filename": "报价表.xlsx"})
        assert "七天" in word_text
        assert "杯子" in excel_text
        print("Word 与 Excel 读取通过")
    finally:
        reset_session_context(session_token, thread_token)
