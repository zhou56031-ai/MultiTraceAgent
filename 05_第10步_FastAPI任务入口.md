# 第 10 步：让 HTTP 请求启动智能体任务

## 本步解决什么问题

前面只能从命令行调用 `run_deep_agent`。本步启动一个本地网页服务：浏览器访问 `/` 能看到入口，`/docs` 能看到接口说明，向 `/api/task` 提交问题会获得会话编号，并安排后台执行。

把服务想成前台：它收件、给编号、把任务交给后台；给出“已受理”不等于后台已经完成。当前先看终端里的完成输出；第 11～12 步才加进度通知和 WebSocket。

## 文件与依赖

这一节的所有终端命令都在外层项目目录运行，也就是终端提示符所在的 `ai agent 学习项目1/`。从这里能看到 `learning/requirements.txt` 和 `learning/.venv/`。如果你已经 `cd learning`，先执行 `cd ..`，再照抄下面的命令；这样路径才与命令一致。

本步要操作的文件如下。**依赖清单是要修改的旧文件，服务与测试脚本是要新建的文件**；不要把示例脚本写到 `learning/` 根目录。

| 路径 | 本步操作 | 谁使用它，起什么作用 |
| --- | --- | --- |
| `learning/requirements.txt` | 在末尾增加三行依赖 | 供 `uv` 读取并安装；它只是清单，本身不是已安装的包 |
| `learning/api/server.py` | 新建 | Uvicorn 导入其中的 `app`；FastAPI 根据这里的路由接收 `/api/task` 请求，并调用已有的 `run_deep_agent` |
| `learning/examples/10_api.py` | 新建 | 你在第二个终端手动运行；它模拟客户端向服务发 HTTP 请求，不会被服务端导入 |
| `learning/agent/main_agent.py` | 本步直接使用，不重写 | `server.py` 从这里导入第 09 步已有的 `agent_runtime` 和 `run_deep_agent` |
| `learning/api/__init__.py` | 已存在，不用改 | 让 `api.server` 按本项目的包结构导入 |

先打开 `learning/requirements.txt`。保留原有的 DeepSeek、Tavily、SQLite 等依赖；在最后一行 `aiosqlite==0.22.1` 后按回车，新增下面三行，然后保存：

~~~text
fastapi==0.129.2
uvicorn==0.41.0
httpx==0.28.1
~~~

`==` 表示要求安装指定版本，便于你重建同一套练习环境。三个包各有分工：

| 包 | 用在哪里 | 少了会怎样 |
| --- | --- | --- |
| `fastapi` | `learning/api/server.py` 的 `FastAPI`、路由、请求解析 | 服务模块无法导入 |
| `uvicorn` | 运行 `api.server:app`，监听本机 `8001` 端口 | 即使写好了路由，也没有本地 HTTP 服务接收请求 |
| `httpx` | `learning/examples/10_api.py` 发测试请求 | 服务仍可运行，但这个测试脚本无法导入 `httpx` |

代码中的 `asyncio`、`uuid`、`contextlib` 来自 Python 标准库，无须单独安装；`agent.main_agent` 是本项目已有的文件，也不是要从网上安装的包。`pydantic` 会作为 FastAPI 的依赖安装，本步无需再单独增加一行。即使当前环境碰巧已有 `httpx`，也要把它写进清单，因为新建环境时测试脚本同样需要它。

保存清单后，在**外层项目目录**执行安装命令：

~~~bash
uv pip install --python learning/.venv/bin/python -r learning/requirements.txt
~~~

逐段看这条命令：`uv pip install` 负责安装；`--python learning/.venv/bin/python` 指定安装到 learning 自己的虚拟环境；`-r learning/requirements.txt` 指定读取刚才保存的依赖清单。这样即使终端提示符显示 `(base)`，包也会装进 `learning/.venv`，不会误装到 `/opt/homebrew/bin/python3`。**改清单但不运行安装命令，Python 仍可能报 `ModuleNotFoundError`。**如果提示找不到 `requirements.txt`，先确认自己是否在外层项目目录，不要把上面命令中的 `learning/` 随意删掉。`uv` 的这两项参数含义也可查阅[官方环境说明](https://docs.astral.sh/uv/pip/environments/)和[依赖文件说明](https://docs.astral.sh/uv/pip/packages/#installing-packages-from-files)。

安装完成后，用**同一个解释器**检查实际可导入的版本。这一步只检查包，不会启动服务，也不会调用 DeepSeek：

~~~bash
learning/.venv/bin/python -c 'import fastapi, uvicorn, httpx; print("fastapi:", fastapi.__version__); print("uvicorn:", uvicorn.__version__); print("httpx:", httpx.__version__)'
~~~

预期分别看到 `0.129.2`、`0.41.0`、`0.28.1`。若仍报找不到包，先核对安装命令和检查命令里的 Python 路径是否都是 `learning/.venv/bin/python`。最后在 VS Code 的 `learning/api/` 下新建 `server.py`，在 `learning/examples/` 下新建 `10_api.py`；下方第 1 节、第 2 节分别给出这两个文件的代码。写完文件后，再到文末“运行与验收”启动服务并发测试请求。

## 先弄清每个文件为什么存在

**`api/server.py`：站在用户与 Agent 之间的“服务前台”。**浏览器或脚本不能直接把 Python 对象传给执行图，于是它们向 `/api/task` 发送 JSON。FastAPI 在此文件中把请求解析成 `TaskRequest`，取得或生成会话编号，安排后台调用 `agent/main_agent.py` 的 `run_deep_agent`，立刻返回 `started` 和编号。这个文件还定义服务的启动与关闭时段，让第 09 步的 `agent_runtime` 在整个服务期间保持可用。它不负责决定搜索关键词，也不负责生成答案；那些仍属于智能体及其工具。

**`agent/main_agent.py`：已经存在的“后厨”。**`api/server.py` 只把 `query`、`thread_id` 交给它；`run_deep_agent` 才创建会话目录、设置 ContextVar、调用图、读写 SQLite 检查点并返回答案。拆成两个文件后，你可以独立检查“请求有没有进入服务”和“Agent 有没有做完”，不会把 HTTP 200 误解成模型成功。

**`examples/10_api.py`：模拟一个外部用户。**它使用 `httpx` 向已启动的 `127.0.0.1:8001` 发送真实 HTTP 请求，打印服务的即时响应。它不能仅凭 `started` 验证最终答案，所以还要去服务器终端看后台的“完成/失败”。`/docs` 是 FastAPI 根据接口声明自动生成的页面，不需要自己创建 `docs` 文件。

**`requirements.txt` 与 `.venv/`：分别是“依赖清单”和“实际安装位置”。**FastAPI 用于定义路由和解析请求，Uvicorn 负责运行服务，httpx 只供示例客户端发请求。缺 FastAPI 时服务无法导入；缺 Uvicorn 时没有启动入口；缺 httpx 只影响本步的示例脚本。

本步完整路线：`examples/10_api.py` → `api/server.py` 的 `submit_task` → 立即得到编号 → 后台 `execute_task` → `agent/main_agent.py` 的 `run_deep_agent` → 终端打印真实结果。第 11 步才补“把过程持续报告出去”。

### 1. api/server.py：可运行的最小服务

~~~python
import asyncio
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from agent.main_agent import agent_runtime, run_deep_agent

running_tasks: set[asyncio.Task] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with agent_runtime():
        try:
            yield
        finally:
            for task in list(running_tasks):
                task.cancel()
            if running_tasks:
                await asyncio.gather(*running_tasks, return_exceptions=True)


app = FastAPI(title="MultiAgent-Search 学习版", lifespan=lifespan)


class TaskRequest(BaseModel):
    query: str
    thread_id: uuid.UUID | None = None


async def execute_task(query: str, thread_id: str) -> None:
    try:
        answer = await run_deep_agent(query, thread_id)
        print(f"任务 {thread_id} 完成：{answer[:100]}")
    except Exception as exc:
        print(f"任务 {thread_id} 失败：{exc}")


@app.get("/", response_class=HTMLResponse)
async def home() -> str:
    return "<h1>MultiAgent-Search 学习版</h1><p>打开 /docs 查看接口</p>"


@app.post("/api/task")
async def submit_task(request: TaskRequest) -> dict:
    thread_id = str(request.thread_id or uuid.uuid4())
    task = asyncio.create_task(execute_task(request.query, thread_id))
    running_tasks.add(task)
    task.add_done_callback(running_tasks.discard)
    return {"status": "started", "thread_id": thread_id}
~~~

### 每个函数与变量在做什么

`lifespan` 在服务启动时由 FastAPI 调用，不是每来一位用户都调用。进入 `async with agent_runtime()` 后，SQLite 连接与主图就绪；`yield` 把运行时段交给服务处理请求；关服时回来，先取消并等候剩余后台任务，再离开 `agent_runtime` 关闭连接。`app` 是服务对象。

`TaskRequest` 描述请求体，例如 `{"query":"查公开市场新闻","thread_id":null}`。Pydantic 会把合法 UUID 文字变成 `uuid.UUID` 对象；不传时为 `None`。`thread_id` 是业务会话编号，传同一个值能继续第 09 步保存的对话。空的 `query` 暂时仍是字符串；后面可增加非空校验。

`submit_task` 由 FastAPI 收到 POST 后调用。`uuid.uuid4()` 在没有编号时生成新编号；`asyncio.create_task(...)` 把 `execute_task` 安排到当前事件循环，立即返回一个 Task 对象。`running_tasks` 保存仍在执行的任务引用，完成回调把它移走。接口返回 `started` 仅表示“已经安排”，不能据此说模型回答成功。

`execute_task` 是后台实际执行者，调用第 09 步的 `run_deep_agent`；`await` 等它完成，随后打印答案前 100 个字符。异常打印到终端，避免后台任务悄悄失败。第 11 步会把完成与错误改为结构化通知。`home` 仅提供当前简单首页；第 14 步换成真正的网页。

一次输入与状态变化：

~~~text
POST {"query":"查公开资料"}
→ submit_task 生成编号 550e...，安排 execute_task
→ HTTP 立即收到 {"status":"started","thread_id":"550e..."}
→ 后台 run_deep_agent 创建对应目录、读取同编号检查点并运行
→ 终端稍后显示“完成”或“失败”
~~~

### 2. examples/10_api.py：接口实验

~~~python
import httpx

response = httpx.post(
    "http://127.0.0.1:8001/api/task",
    json={"query": "请搜索 Python 官方文档并附上网址"},
    timeout=10,
    trust_env=False,
)
print("HTTP 状态：", response.status_code)
print("提交结果：", response.json())
~~~

`trust_env=False` 只用于这个请求本机 `127.0.0.1` 的练习脚本：它让 HTTPX 忽略环境中的代理配置并直连本地服务。若出现 `httpx.RemoteProtocolError: Server disconnected without sending a response`，而 traceback 中有 `http_proxy.py`，先检查这一行是否写进了 `learning/examples/10_api.py`。这不是关闭 HTTPS 证书校验；本例使用的地址本来就是本机 HTTP。HTTPX 默认会读取环境配置，`trust_env=False` 的行为见[官方说明](https://www.python-httpx.org/environment_variables/)。

## 运行与验收

终端一（外层工作目录）：

~~~bash
learning/.venv/bin/python -m uvicorn api.server:app --app-dir learning --host 127.0.0.1 --port 8001
~~~

浏览器打开 `http://127.0.0.1:8001/` 和 `http://127.0.0.1:8001/docs`。终端二运行：

~~~bash
learning/.venv/bin/python learning/examples/10_api.py
~~~

先检查 HTTP 200 与合法编号，再回终端一观察真正的“完成”或“失败”。如果只得到 `started`，本步仅验证了提交，不代表 Agent 已经成功。`examples/10_api.py` 是正式接口的测试案例，按你的要求留在 `examples/`。本地已验证该脚本可以收到 HTTP 200 和 `started`；Agent 的最终结果仍以终端一的日志为准。

思考：为什么 `agent_runtime` 要包住整个服务生命周期，而不是写在 `submit_task` 里面？
