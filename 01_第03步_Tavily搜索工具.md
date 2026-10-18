# 第 03 步 · 连接 Tavily：普通搜索与模型工具

> 上一步：[第 02 步](01_第02步_普通函数到模型工具.md) · 下一步：[第 04 步](01_第04步_YAML提示词与加载.md)  
> 本步会使用真实 Tavily 服务；每次搜索都会使用相应账户用量。

## 1. 本步问题和例子

第 02 步的工具只做本地乘法。现在我们需要一个真正能取得外部资料的工具：查询“Python asyncio 官方文档”，打印搜索结果标题和 URL。

分成两次可选择的验证：

- 普通调用 `search_web(...)`，证明 SDK 和账户能正常搜索。
- 工具调用 `internet_search.invoke(...)`，证明同样能力能以工具接口调用。

尚未引入智能体自主决策；不要把手动工具调用说成模型已经学会联网。

## 2. 文件与依赖逐项说明

| 动作和路径 | 谁会用、为什么存在 |
| --- | --- |
| 修改 `learning/requirements.txt` | 增加 SDK 包，工具模块导入它 |
| 修改 `learning/.env.example`、`.env` | 分别记录搜索键名模板与本机真实搜索凭据 |
| 新建 `learning/tools/tavily_tool.py` | 正式搜索能力，之后第 05 步子助手会导入 `internet_search` |
| 新建 `learning/examples/03_tavily_tool.py` | 可切换普通/工具调用的验证入口，不由服务器导入 |

在 `learning/requirements.txt` 保留第 01 步四行，追加：

```text
tavily-python==0.7.21
```

从**外层目录**安装并检查：

```bash
uv pip install --python learning/.venv/bin/python -r learning/requirements.txt
learning/.venv/bin/python -c 'from tavily import TavilyClient; print("Tavily SDK 可导入")'
```

SDK 是访问搜索服务的代码包，不会替你开通账户或创建 Key。

## 3. 修改两份配置文件

`learning/.env.example` 的第 01 步三项下追加模板：

```dotenv
TAVILY_API_KEY=replace_with_your_local_tavily_key
```

在本机 `learning/.env` 中增加同名键并填写 Tavily 签发的真实值，保留已有模型配置。模型 Key 与 Tavily Key 分属不同服务，不能互换；不要把真实值复制进教程或脚本。

## 4. 新建 learning/tools/tavily_tool.py

此处是**第 03 步完整文件**，没有 `monitor` 或重试导入；它们分别到第 11、17 步才加入。

```python
import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from langchain_core.tools import tool
from tavily import TavilyClient

env_file = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_file)

api_key = os.getenv("TAVILY_API_KEY")
if not api_key:
    raise RuntimeError("请检查 .env 中的 TAVILY_API_KEY")

client = TavilyClient(api_key=api_key)


def search_web(
    query: str,
    topic: Literal["general", "news", "finance"] = "general",
    max_results: int = 3,
    include_raw_content: bool = False,
) -> dict:
    return client.search(
        query=query,
        topic=topic,
        max_results=max_results,
        include_raw_content=include_raw_content,
    )


@tool
def internet_search(
    query: str,
    topic: Literal["general", "news", "finance"] = "general",
    max_results: int = 3,
    include_raw_content: bool = False,
) -> dict:
    """搜索公开网页，返回搜索结果及其来源。"""
    return search_web(query, topic, max_results, include_raw_content)
```

## 5. 客户端初始化与实际请求不是同一时刻

导入这个文件时：定位 `.env` → 取 Key → 创建 `client` → 定义两个函数。`TavilyClient(...)` 配置客户端，不是发出了这次查询。

`search_web(...)` 被调用时才执行 `client.search(...)`，真正发请求。返回值通常是包含 `results` 等字段的字典，不是格式化的最终答案。

`client` 是模块级复用对象，不是每条搜索的结果；`api_key` 是凭据字符串，不是客户端。不要把二者混为一谈，也不要 print 凭据。

## 6. 每个参数都代入一个值

| 参数 | 本例 | 作用 | 默认值在哪里生效 |
| --- | --- | --- | --- |
| `query` | `"Python asyncio 官方文档"` | 要查询的关键词 | 无默认值，调用者必须提供 |
| `topic` | `"general"` | 选择搜索主题 | 调用者省略时使用 general |
| `max_results` | `2` | 请求期望的结果数量上限 | 省略时 3，不保证总能取得这么多结果 |
| `include_raw_content` | `False` | 是否请求页面原始正文内容 | 默认不请求，避免初次实验返回过长文本 |

`Literal[...]` 表达允许的字符串候选，便于类型检查及工具参数结构。它不会自动替普通 Python 函数的所有调用执行校验；工具框架和服务端还会有各自校验。

`return client.search(...)` 把 SDK 返回值原样交给调用者。这个阶段不加工成报告，也不自行判断每条网页事实是否可靠。

### 为什么保留两个名字

- `search_web` 是普通函数，测试搜索与后续重试逻辑时方便直接调用。
- `internet_search` 是对模型暴露的工具入口，名称和说明会出现在助手的工具描述中。

工具入口再调用普通函数，避免写两份 SDK 搜索逻辑。第 17 步给 `search_web` 加重试后，工具入口也会自然用到它。

## 7. 新建 learning/examples/03_tavily_tool.py

```python
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from tools.tavily_tool import internet_search, search_web

mode = sys.argv[1] if len(sys.argv) > 1 else "plain"
if mode not in {"plain", "tool"}:
    raise ValueError("模式只能是 plain 或 tool")

query = "Python asyncio 官方文档"
if mode == "plain":
    result = search_web(query, max_results=2)
else:
    result = internet_search.invoke({"query": query, "max_results": 2})

items = result.get("results", [])
assert isinstance(items, list) and items, "搜索未返回非空结果列表"
print("调用方式：", mode)
print("实际结果数：", len(items))
for item in items:
    print("标题：", item.get("title", ""))
    print("链接：", item.get("url", ""))
```

### 7.1 示例怎样选择一条路线

`sys.argv` 是运行脚本时的命令参数列表。没有额外参数时用 plain；写了 tool 就走工具调用。`if/else` 保证一次运行只搜索一次，不默认把两种方式都跑一遍。

`result` 是整个响应字典；`items` 是其中 `results` 对应的列表；`item` 是循环中当前那一条结果字典。不是整个响应都能当成一篇文章。

响应形状示意，以下不是固定真实结果：

```json
{
  "results": [
    {"title": "某篇官方文档", "url": "https://docs.python.org/...", "content": "页面摘要"}
  ]
}
```

`len(items)` 取得实际结果数。`item.get(...)` 在字段缺失时返回默认空串，避免为了打印标题发生 KeyError；断言仍要求有非空结果列表。

## 8. 运行与通过标准

在**外层目录**运行普通调用：

```bash
learning/.venv/bin/python learning/examples/03_tavily_tool.py plain
```

需要比较工具入口时，再运行：

```bash
learning/.venv/bin/python learning/examples/03_tavily_tool.py tool
```

每条命令都是真实搜索。你应看到对应模式、非零结果数、标题和可核查 URL。结果可能随时间变化，不把某个标题固定为断言。

完整路线：

```text
示例取得关键词
→ plain：search_web；或 tool：internet_search.invoke
→ search_web 调用 client.search
→ SDK 请求 Tavily
→ 响应字典回到示例
→ 取 results 列表并打印标题/链接
```

## 9. 常见错误与阶段边界

| 错误 | 原因方向 |
| --- | --- |
| `cannot import name search_web` | 文件里可能只写了工具入口，必须按本步定义两个函数 |
| `No module named tools` | 先执行示例中的 sys.path 准备，再 import 项目包 |
| 找不到 requirements.txt | 你若在外层目录安装，要写 `-r learning/requirements.txt` |
| 认证或配额错误 | 本机检查 Tavily 账户与对应 Key，不是 DeepSeek 凭据 |
| 超时 | 当前阶段先把错误定位清楚，第 17 步只对可恢复网络异常加重试 |

不要提前从尚未创建的 `api.monitor` 导入对象。当前成品的工具文件已经有后续阶段功能，初学时使用本页代码快照。

理解检查：`result`、`items`、`item` 分别是什么类型？把 `max_results` 改为 1，改变的是请求上限还是保证返回条数？

下一步：[第 04 步](01_第04步_YAML提示词与加载.md)，先把团队规则与 Python 组装代码分开。
