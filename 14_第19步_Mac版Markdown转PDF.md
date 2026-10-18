# 第 19 步：在 Mac 上把会话报告转成 PDF

## 本步要解决的问题

参考项目的 PDF 代码通过 Windows Word COM 工作；当前学习环境是 macOS，直接复制 `win32com` 会导入失败。主提示词目前却说“可以生成 PDF”，而 `build_main_agent()` 实际只注册了 Markdown 与读取工具。本步把“能不能生成 PDF”变成真实工具能力，并用 Mac 可运行的渲染器完成转换。

例子：用户让 A 会话写一份 PDF 报告。主智能体先用 `generate_markdown` 写出 `报告.md`，再调用 `convert_md_to_pdf` 生成同一会话目录里的 `报告.pdf`；网页的文件列表显示 PDF，可下载。单独创建 PDF 文件不意味着内容正确，所以最后要打开查看排版与中文。

## 文件、调用者与依赖

1. **新建 learning/utils/pdf_converter.py**：纯转换函数接收两个 `Path`，把 Markdown 渲染为 PDF。由工具调用；它不认识会话编号。
2. **新建 learning/tools/pdf_tools.py**：给主模型注册的 `@tool`。它使用已有 `resolve_session_file` 把输入和输出限制在当前会话目录，并向 monitor 报告文件名。
3. **修改 learning/agent/main_agent.py 的 build_main_agent()**：原来的 `tools=[generate_markdown, read_file_content]` 需变成实际工具名单，并根据 PDF 工具是否能导入决定是否追加。`create_deep_agent` 在这里拿到最终名单；不在这一步直接转换任何文件。
4. **修改 learning/prompt/prompts.yml 的 main_agent.system_prompt**：把无条件承诺 PDF 的句子改为“仅当 PDF 工具已注册才转换”。避免提示词与真实能力冲突。
5. **新建 learning/examples/19_pdf.py**：创建临时会话目录，用正式工具生成 PDF，检查文件签名，再人工打开看中文。示例不进入服务。
6. **修改 learning/requirements.txt**：增加 `Markdown==3.10.2` 和 `weasyprint==68.1`。前者把 Markdown 转 HTML；后者把 HTML 排版成 PDF。第 18 步的 `pypdf` 可用于进一步检查，不是生成 PDF 的依赖。

在外层目录 **ai agent 学习项目1**，Mac 先装渲染库所需的系统组件，再装进 learning 的 Python：

~~~bash
brew install pango libffi
uv pip install --python learning/.venv/bin/python Markdown==3.10.2 weasyprint==68.1
learning/.venv/bin/python -c 'import markdown; from weasyprint import HTML; print("PDF 依赖可导入")'
~~~

若最后一条报找不到 Pango，再检查 Homebrew 安装路径和 [WeasyPrint 官方 macOS 安装说明](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html)。不要把系统 `python3` 的成功导入误认为 `learning/.venv/bin/python` 已安装成功。参考项目的 Word COM 转换仍只适合 Windows；这里是**Mac 适配版**，效果需以本机输出验证。

## 1. 新建 learning/utils/pdf_converter.py

~~~python
from pathlib import Path

import markdown
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
~~~

`md_path` 是源文件路径，`pdf_path` 是目标路径，均由工具先做会话目录检查。`source` 是 Markdown 原文；`body` 是 HTML 片段；`HTML(...).write_pdf(...)` 才真正写文件。`deny_external_resource` 拒绝 Markdown 内嵌的网页图片等外部读取；本步只支持纯文字、表格和代码块排版。无显式 `return` 表示成功后函数返回 `None`，效果是磁盘上出现 PDF；失败会抛异常给调用者。

## 2. 新建 learning/tools/pdf_tools.py

~~~python
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
~~~

`md_filename` 由模型给出，例如 `"报告.md"`；`pdf_filename=None` 表示模型没指定输出名，于是程序自动使用 `"报告.pdf"`。`source` 与 `target` 是两个不同的 `Path` 对象，但必须指向同一会话目录里的文件。`monitor.report_tool` 发出“将开始转换”的事件，不能当成 PDF 已完成；`render_pdf` 返回后才报告“已生成”。已有 `resolve_session_file` 拒绝绝对路径和 `../` 越界。

## 3. 在 learning/agent/main_agent.py 注册真实可用的工具

在 `build_main_agent()` 里，原 `return create_deep_agent(...)` **之前**，在生成 `system_prompt` 的代码附近增加：

~~~python
tools = [generate_markdown, read_file_content]
pdf_capability = "当前未注册 PDF 工具；若用户要求 PDF，说明目前无法转换。"
try:
    from tools.pdf_tools import convert_md_to_pdf
except (ImportError, OSError) as exc:
    print(f"PDF 工具未启用：{type(exc).__name__}")
else:
    tools.append(convert_md_to_pdf)
    pdf_capability = "当前可生成 PDF：先生成 Markdown，再调用 convert_md_to_pdf。"
~~~

随后把同一函数中 `system_prompt = ...replace("{available_subagents}", assistant_descriptions)` 的赋值改为：

~~~python
system_prompt = (
    main_agent_content["system_prompt"]
    .replace("{available_subagents}", assistant_descriptions)
    .replace("{pdf_capability}", pdf_capability)
)
~~~

再把 `create_deep_agent(..., tools=[generate_markdown, read_file_content], ...)` 中的 `tools` 参数**只改成** `tools=tools`。不要额外再建第二个图。`tools` 是主智能体工具列表；`subagents` 是专家助手名单，二者不同。只有导入成功时 PDF 工具才出现在图里；安装依赖后须**重新构建图或重启服务**，已有图不会自动多出工具。

在 **learning/prompt/prompts.yml → main_agent.system_prompt** 中，找到目前写着“你可以使用自己掌握的工具生成 Markdown 和 PDF 两种格式的文件”的行，以及“用户明确要求生成文件时”“生成文件时”“不能跳过 Markdown”这三行。分别替换成：

~~~text
    - 你可以生成 Markdown 文件。{pdf_capability}
    - 用户明确要求生成 Markdown 时，调用 generate_markdown；要求 PDF 时，只有当前注册了 convert_md_to_pdf 才先生成 Markdown 再转换。
    - 生成 PDF 的顺序是：generate_markdown → convert_md_to_pdf。
    - 没有注册 PDF 工具时，不得声称已生成 PDF；也不得生成用户未要求的文件类型。
~~~

第一行替换文件生成段的能力描述；后三行替换“你的主要任务类别”段中的对应三行，**不要把四行挤到同一位置**，也不能改到子助手提示词里。`{pdf_capability}` 只在建图时替换成当前真实状态。

## 4. 新建 learning/examples/19_pdf.py 并验收

~~~python
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
~~~

从外层目录运行 `learning/.venv/bin/python learning/examples/19_pdf.py`。脚本停在 `input` 时查看临时目录；关闭后它会被删除。验证成功要同时满足工具返回成功、文件以 `%PDF` 开头、打开后中文及表格可读。理解检查：为什么 `monitor.report_tool` 出现在 `write_pdf` 之前，却不能证明 PDF 已生成？

