# 第 07 步：给每个任务自己的会话目录和上下文

> 上一步：[第 06 步：主图构建与真实委派](01_第06步_主图构建与真实委派.md) · 总入口：[从零复刻阅读导航](从零复刻阅读导航.md)

## 本步解决什么问题

第 06 步只有一个问题和一张执行图。现在假设小明的任务编号是 A，小红的任务编号是 B，两人同时运行：小明的文件应该进 `output/session_A/`，小红的文件应该进 `output/session_B/`。深层的工具函数也需要知道“我正在处理哪个任务”。

`ContextVar` 像每条执行路线各自携带的一张便签。它保存当前路线的目录和编号；它不是数据库，也不会替我们创建目录。先用 A/B 实验证明它能隔离，再把它放进智能体执行函数。

## 要创建和修改的文件

| 文件 | 放什么 |
| --- | --- |
| `api/context.py` | 设置、读取、恢复当前会话的目录和编号 |
| `agent/main_agent.py` | 新增执行一次用户任务的异步函数 |
| `examples/07_context.py` | A/B 并发实验；测试入口只在 examples |

## 先弄清每个文件为什么存在

**`api/context.py`：保存“当前正在替谁工作”。**它是全项目共用的一小块基础能力，不直接搜索、写文件或发网页消息。第 07 步由 `agent/main_agent.py` 在任务开始时调用它，把目录和编号放入当前任务的执行环境；第 08 步的文件工具会来取目录，第 11～12 步的通知代码会来取编号，任务结束后再恢复原值。把这些设置与读取集中在一个文件，是为了让深层工具只需要导入同一套函数，不用每增加一层调用就增加两个参数。少了它，文件工具和通知员就不知道自己当前服务的是 A 还是 B。

**`agent/main_agent.py`：负责把一轮真实任务串起来。**这个文件在第 06 步已经负责“组装主智能体”；现在新增的 `run_deep_agent` 负责“执行一次”。它接收用户问题和会话编号，创建对应的 `output/session_编号/`，设置 ContextVar，调用执行图，最后恢复 ContextVar 并把答案交给调用者。第 10 步的 API 会调用这个函数。目录属于它创建，`api/context.py` 只记录目录的位置；如果只创建目录却不记录，深层工具依然不知道该去哪里。

**`examples/07_context.py`：专门检验“同时运行会不会串台”。**它手动启动 A、B 两个小任务，交替等待和读取各自的目录及编号，不请求 DeepSeek，也不参与正式服务运行。这样如果结果串了，先检查 ContextVar 的用法，不必猜是模型还是网页造成的。`output/session_A/`、`output/session_B/` 是运行时产生的数据目录，不是要手写代码的文件。

按本步例子，调用路线是：`examples/07_context.py` 启动 A/B → 两个任务分别调用 `api/context.py` 写入自己的值 → 暂停后再读取 → 各自恢复。接入真实 Agent 后，路线变为 API（第 10 步）→ `agent/main_agent.py` → `api/context.py` → 后续工具。

### 1. 写 api/context.py

~~~python
from contextvars import ContextVar, Token

_session_dir: ContextVar[str | None] = ContextVar("session_dir", default=None)
_thread_id: ContextVar[str | None] = ContextVar("thread_id", default=None)


def set_session_context(path: str) -> Token:
    return _session_dir.set(path)


def get_session_context() -> str | None:
    return _session_dir.get()


def set_thread_context(thread_id: str) -> Token:
    return _thread_id.set(thread_id)


def get_thread_context() -> str | None:
    return _thread_id.get()


def reset_session_context(session_token: Token, thread_token: Token) -> None:
    _thread_id.reset(thread_token)
    _session_dir.reset(session_token)
~~~

`_session_dir` 和 `_thread_id` 是两个“便签栏”，不是 A/B 的具体值。`default=None` 表示当前执行路线还未设置时，读取结果是 `None`。`set(...)` 写入当前路线，同时返回一个 `Token`；这个 Token 记着写入前的状态。`reset(token)` 用对应 Token 恢复旧值，适合放在 `finally`，即使模型报错也会执行。

函数调用关系：执行任务的函数调用两个 `set_*`；以后文件工具调用 `get_session_context`，通知员调用 `get_thread_context`；任务结束由执行函数调用 `reset_session_context`。这些函数不会自动运行，必须由上述调用者调用。`get_*` 返回字符串或 `None`，`set_*` 返回 Token，`reset_*` 返回 `None`。这里的 `thread_id` 是业务会话编号，不是操作系统线程编号。

### 2. 先做不花 API 费用的实验

`examples/07_context.py`：

~~~python
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from api.context import (
    get_session_context, get_thread_context,
    reset_session_context, set_session_context, set_thread_context,
)


async def worker(thread_id: str) -> None:
    path = f"output/session_{thread_id}"
    path_token = set_session_context(path)
    id_token = set_thread_context(thread_id)
    try:
        await asyncio.sleep(0.1)
        print(thread_id, get_session_context(), get_thread_context())
    finally:
        reset_session_context(path_token, id_token)
        print(thread_id, "恢复后", get_session_context(), get_thread_context())


async def main() -> None:
    await asyncio.gather(worker("A"), worker("B"))


asyncio.run(main())
~~~

`worker("A")` 写入 A 的目录后遇到 `await asyncio.sleep`，运行机会暂时交给 B。B 写入自己的目录。恢复运行时，A 读到的还是 A，不是 B。`gather` 让两个 `worker` 并行推进；`await` 是等它们完成。输出顺序可能变化，但每行的编号与目录必须配对。`finally` 中的“恢复后”通常是两个 `None`，因为本例设置前没有旧值。若原先有旧值，恢复的是旧值，不一定是 `None`。

### 3. 在 agent/main_agent.py 增加执行函数

要修改的文件是 `learning/agent/main_agent.py`：保留文件中已有的 `build_main_agent()`，在这个文件里补充下面的导入、`project_root_path` 和 `run_deep_agent()`。不用改第 06 步的教学文档。

~~~python
from pathlib import Path
from api.context import (
    reset_session_context, set_session_context, set_thread_context,
)

project_root_path = Path(__file__).resolve().parent.parent


async def run_deep_agent(task_query: str, session_id: str) -> str:
    session_dir = project_root_path / "output" / f"session_{session_id}"
    session_dir.mkdir(parents=True, exist_ok=True)
    session_token = set_session_context(str(session_dir))
    thread_token = set_thread_context(session_id)
    try:
        graph = build_main_agent()
        result = await graph.ainvoke({
            "messages": [{"role": "user", "content": task_query}]
        })
        return str(result["messages"][-1].content)
    finally:
        reset_session_context(session_token, thread_token)
~~~

`project_root_path` 从此文件向上两层得到 learning 根目录，避免依赖终端当前目录。`session_dir` 是当前任务专属目录；`mkdir` 真正创建目录，ContextVar 本身不创建。`graph` 是第 06 步构建的执行图；`ainvoke` 才开始调用模型与工具。`result` 是执行结束后的状态字典；最后一条消息的 `content` 是本轮答案。`return` 交给调用 `run_deep_agent` 的代码；到了第 10 步，这个调用者会是 API 后台任务。当前每次调用都会重新构图，尚无跨轮记忆；第 09 步会把图与 SQLite 连接放到服务生命周期中。

一次具体追踪：A 进入 `run_deep_agent("查市场新闻", "A")` → 创建 `output/session_A` → 写入两张上下文便签 → 等待图执行 → 返回答案 → `finally` 恢复便签。B 即使同时进入，也使用自己的编号与目录。

## 运行与验收

在外层工作目录执行：

~~~bash
learning/.venv/bin/python learning/examples/07_context.py
~~~

检查 A 的一行只包含 `session_A`，B 的一行只包含 `session_B`，并且两者结束后都恢复原值。本页描述从第 06 步继续搭建时的阶段代码。2026-10-17 的基础教程检查已验证“保留 build_main_agent 并追加本步代码”可以导入并定义函数；这个衔接检查不代替本页的 A/B 并发实验或真实模型调用。

思考：如果把 `finally` 整段删掉，同一条执行路线后来再次读取上下文时，可能看到什么旧值？下一步会让文件工具实际使用这张“目录便签”。
