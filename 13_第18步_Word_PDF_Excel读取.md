# 第 18 步：让同一个读取工具看懂 Word、PDF 和 Excel

## 本步要解决的问题

第 13 步的上传接口可以保存任意文件，但第 08 步的 `read_file_content` 只会读 `.txt` 和 `.md`。这就像收件室收到了 Word 合同，却只有“读纯文本”的眼镜：文件确实在工作目录，智能体仍看不到正文。本步扩展**读取工具**，不改上传接口，也不把文件正文放进监控事件。

贯穿例子：小明给会话 A 上传“报价表.xlsx”。任务开始后文件被复制到 `output/session_A/`；模型调用 `read_file_content("报价表.xlsx")`；工具用 Excel 解析器读取第一张表的预览，再把文字交回模型。上传成功、复制成功、内容读取成功依旧是三件事。

## 文件与依赖：逐个找到位置

- **修改 learning/tools/upload_file_read_tool.py**：保留现有 `read_file_content` 名字和 `@tool`，新增普通函数 `extract_file_text` 负责格式分流。它由读取工具调用，接收已检查的 `Path`，返回文字。没有它，上传 Word/PDF/Excel 仍会报“只支持 txt/md”。
- **修改 learning/requirements.txt**：逐行加入 `python-docx==1.2.0`、`pypdf==6.7.2`、`pandas==3.0.1`、`openpyxl==3.1.5`。`python-docx` 读 Word；`pypdf` 提取可选择的 PDF 文字；`pandas` 整理表格预览；`openpyxl` 是 pandas 读取 `.xlsx` 的引擎。Excel 的旧 `.xls` 不在本步范围。
- **新建 learning/examples/18_read_formats.py**：制作小型 Word 与 Excel 文件，给 ContextVar 指定临时会话目录，直接调用正式工具。它是验证入口，不由服务器导入。
- `learning/updated/` 和 `learning/output/` 是已有运行目录，无须手动新建。新文件仍在会话目录中，不进入 RAGFlow 数据集。

在外层目录 **ai agent 学习项目1** 安装到指定解释器：

~~~bash
uv pip install --python learning/.venv/bin/python python-docx==1.2.0 pypdf==6.7.2 pandas==3.0.1 openpyxl==3.1.5
learning/.venv/bin/python -c 'import docx, pypdf, pandas, openpyxl; print("四种读取依赖可用")'
~~~

## 1. 修改 learning/tools/upload_file_read_tool.py 的导入与普通函数

在原有导入处新增 `from pathlib import Path`、`from docx import Document`、`from pypdf import PdfReader`、`import pandas as pd`。在现有 `@tool` **之前**加：

~~~python
def extract_file_text(path: Path) -> str:
    """把一个已定位的会话文件转换成给模型看的文字。"""
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8")
    if suffix == ".docx":
        document = Document(path)
        return "\n".join(p.text for p in document.paragraphs)
    if suffix == ".pdf":
        reader = PdfReader(path)
        return "\n".join(page.extract_text() or "" for page in reader.pages[:20])
    if suffix == ".xlsx":
        frame = pd.read_excel(path, sheet_name=0, nrows=100)
        return (
            f"列名：{', '.join(map(str, frame.columns))}\n"
            f"读取行数：{len(frame)}\n"
            f"{frame.head(10).to_string(index=False)}"
        )
    raise ValueError(f"不支持的文件类型：{suffix or '无扩展名'}")
~~~

这里 `path` 是经过 `resolve_session_file` 检查后的真实路径；`suffix` 决定借哪副“眼镜”。Word 的 `paragraphs` 是段落列表，提取段落文字；此最小版还不读 Word 表格。PDF 的 `pages[:20]` 限制页数，`extract_text() or ""` 处理没有文字层的页面；扫描图片 PDF 通常还需 OCR，本步不假装已识别图片。Excel 的 `sheet_name=0` 是第一张表，`nrows=100` 限制实际读取行数，`head(10)` 再把前十行展示给模型。返回值始终是 `str`，与原工具接口保持一致。

| 变量 | “报价表.xlsx”例子中的值 | 谁用它 |
| --- | --- | --- |
| `path` | 例如 `.../output/session_A/报价表.xlsx` | `extract_file_text` 打开文件 |
| `suffix` | `".xlsx"` | 决定走 Excel 分支 |
| `frame` | 第一张表的最多 100 行 DataFrame 对象 | 取列名、行数、前十行 |
| 返回的文字 | “列名：商品, 价格…” | `read_file_content` 再交给模型 |

## 2. 替换同文件的 read_file_content()

在 **learning/tools/upload_file_read_tool.py** 中找到现有 `@tool def read_file_content(filename: str)`，整体替换为下段；`resolve_session_file` 和 `monitor` 的原导入保留：

~~~python
@tool
def read_file_content(filename: str) -> str:
    """读取当前会话中的 txt、md、docx、pdf 或 xlsx 文件。"""
    try:
        target = resolve_session_file(filename)
        if not target.is_file():
            return f"错误：文件不存在：{target.name}"
        monitor.report_tool("read_file_content", {"filename": target.name})
        text = extract_file_text(target)
        return text[:12000] or "文件中没有可提取的文字"
    except (ValueError, RuntimeError, OSError, UnicodeError) as exc:
        return f"读取失败：{exc}"
    except Exception as exc:
        return f"读取失败：{type(exc).__name__}"
~~~

`filename` 来自模型工具调用，只应是会话内相对文件名。`target` 由已有的 `resolve_session_file` 把它限定在当前会话目录；这不是新建文件。`monitor.report_tool` 只发文件名，不能发提取的正文。`text[:12000]` 限制返回给模型的字符数，避免一本很长的 PDF 直接塞满模型上下文；这是**返回截断**，不是从磁盘删除文件。异常分支不应打印上传文件正文。

完整路线：`run_deep_agent` 复制“报价表.xlsx” → 主模型看到文件名 → 工具收到 `filename` → 路径检查 → 格式分流 → pandas 读第一张表 → 预览文字返回 → 模型据此回答。若文件只是扫描 PDF，返回“没有可提取的文字”比编造内容可靠。

## 3. 新建 learning/examples/18_read_formats.py

~~~python
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
~~~

运行 `learning/.venv/bin/python learning/examples/18_read_formats.py`。PDF 分支需要再选一份**有可选择文字**的 PDF 放进测试会话目录做实际验证；这个脚本未测 PDF，也未测真实模型调用。理解检查：为什么 `monitor` 只收到文件名，而模型能收到文件内容？为什么扫描 PDF 可能提取不到字？

