# 第 09 步：用 SQLite 保存会话对话，并管理连接的生命周期

## 本步解决什么问题

第 07 步虽然有 `session_id="A"`，但它只决定目录和当前上下文。主智能体每次重新构建，服务重启后不知道 A 之前说过什么。本步让 A 的对话状态写进 `learning/data/checkpoints.db`；B 使用同一个数据库文件，但按自己的编号读取状态。

把它想成图书馆：数据库文件是书架，`thread_id` 是每本借阅记录的编号；`AsyncSqliteSaver` 是打开的登记台。结束服务时关闭登记台，书架上的记录仍在。

## 先看 yield 到底交给谁

以下是讲解实验，放进 `learning/examples/09_lifecycle.py` 的前半部分：

~~~python
import asyncio
from contextlib import asynccontextmanager

@asynccontextmanager
async def demo_room():
    print("进入：开门")
    try:
        yield "一张桌子"
    finally:
        print("退出：关门")

async def demo():
    async with demo_room() as desk:
        print("使用期间：", desk)

asyncio.run(demo())
~~~

调用 `demo_room()` 得到一个异步上下文管理器。进入 `async with` 时，运行到 `yield "一张桌子"`；这个值交给 `as desk`，此时函数暂停，门保持打开。代码块结束，无论正常还是异常，回来继续执行 `finally`，打印关门。这里的 `yield` 不是“函数全部结束”。理解这个顺序后，再看下面的真实数据库连接。

## 文件与依赖

在 `learning/requirements.txt` 增加 `langgraph-checkpoint-sqlite==3.0.3` 和 `aiosqlite==0.22.1`，从外层工作目录运行：

~~~bash
uv pip install --python learning/.venv/bin/python -r learning/requirements.txt
~~~

修改 `learning/agent/main_agent.py`；新增 `learning/examples/09_checkpoint.py`。正式代码仍放 `learning/agent/`，示例只放 `learning/examples/`。

## 先弄清每个文件为什么存在

**`agent/main_agent.py`：保存图对象与数据库连接的共同工作时段。**前两步它已经能组装和执行智能体，这一步新增 `agent_runtime`：启动服务时打开 SQLite saver，并把它交给执行图；服务关闭时清掉当前图引用、关闭连接。`run_deep_agent` 也改为使用这张正在运行的图，并给每次调用传入 `configurable.thread_id`。如果每次提问都随手创建一张无检查点的新图，A 的第二轮问题无法接上 A 的第一轮记录。

**`data/checkpoints.db`：运行时生成的记录本，不需要手写。**A 和 B 的对话状态都可保存在这个 SQLite 文件里，但按各自的 `thread_id` 查找。它与 `output/session_A/` 的 Markdown 文件不同：前者保存图的对话状态，后者保存用户可下载的工作文件。关闭连接后数据库文件仍在；`main_agent = None` 也不会删除它。

**`examples/09_lifecycle.py` 与 `examples/09_checkpoint.py` 各验证一件事。**前者用“开门—使用—关门”的小实验，让你先看清 `yield` 把控制权交到哪里、什么时候回来；它不使用 SQLite。后者才真正打开 saver，让 A/B 各运行一轮，关闭连接后重新打开，并按编号检查消息是否还在。两个示例都不应混进正式的 `agent/main_agent.py`。

**`requirements.txt` 记录恢复环境所需的包，`.venv/` 才是包真正安装的位置。**增加 SQLite 相关依赖后必须安装；只改列表不会自动让 Python 获得新模块。`api/context.py` 在这一阶段仍负责“当前执行链路是谁”，而 SQLite 的 `thread_id` 负责“从记录本找哪一页”，两者使用同一个编号却解决不同问题。

一次具体路线：A 的请求进入 `run_deep_agent` → 当前 ContextVar 写 A 与 A 的目录 → 运行图携带 `configurable.thread_id="A"` → saver 把状态存到 `checkpoints.db` 的 A 记录 → 请求结束恢复 ContextVar → 服务重启后用编号 A 再找回记录。

### 1. 修改 build_main_agent

要修改的文件是 `learning/agent/main_agent.py`。找到 `build_main_agent()`；如果它还没有 `checkpointer` 参数和 `checkpointer=checkpointer`，将函数改成下面的版本。若你已写好这两个位置，就不用重复改。

~~~python
def build_main_agent(checkpointer=None):
    return create_deep_agent(
        model=model,
        tools=[generate_markdown, read_file_content],
        system_prompt=main_agent_content["system_prompt"],
        subagents=[network_search_agent],
        checkpointer=checkpointer,
    )
~~~

`checkpointer` 是保存图状态的对象。默认为 `None` 时，仍能进行单次实验；传入 SQLite saver 时，图执行过程会按配置的编号保存状态。它和第 07 步的 ContextVar 不互相替代。

### 2. 增加长期运行的数据库上下文

继续修改 `learning/agent/main_agent.py`：把两个 `import` 放到文件顶部的其他导入附近；把 `checkpoint_db_path`、`main_agent` 和 `agent_runtime()` 放在 `run_deep_agent()` 外面，作为模块级代码。

~~~python
from contextlib import asynccontextmanager
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

checkpoint_db_path = project_root_path / "data" / "checkpoints.db"
main_agent = None


@asynccontextmanager
async def agent_runtime():
    global main_agent
    checkpoint_db_path.parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(
        str(checkpoint_db_path)
    ) as checkpointer:
        main_agent = build_main_agent(checkpointer)
        try:
            yield main_agent
        finally:
            main_agent = None
~~~

`checkpoint_db_path` 是数据库文件的路径；`mkdir` 创建它的父目录，不会清空已有数据。`from_conn_string(...)` 建立异步 SQLite saver 的上下文；`async with ... as checkpointer` 进入时打开所需连接，退出时关闭。`main_agent` 保存当前服务可使用的执行图引用。`yield main_agent` 把这张图交给外部的 `async with agent_runtime() as graph` 使用，图和连接在代码块期间持续可用。`finally` 把变量重置为 `None`；真正关闭连接的是外层 SQLite 上下文退出。关闭连接不会删除 `checkpoints.db`。

谁调用？第 09 步示例手动调用 `agent_runtime`；第 10 步由 FastAPI 的服务生命周期调用。不要在每次请求里短暂打开、马上关闭检查点连接。

### 3. 让 run_deep_agent 使用现有图和会话编号

仍然修改 `learning/agent/main_agent.py`，找到 `async def run_deep_agent(task_query: str, session_id: str)`。在它的 `try:` 里面，删除从 `graph = build_main_agent()` 到原来 `result = await graph.ainvoke(...)` 结束的代码，换成下面这段；后面的 `return str(result["messages"][-1].content)` 和 `finally:` 保留。

~~~python
if main_agent is None:
    raise RuntimeError("智能体尚未初始化")
config = {"configurable": {"thread_id": session_id}}
result = await main_agent.ainvoke(
    {"messages": [{"role": "user", "content": task_query}]},
    config=config,
)
~~~

保留第 07 步的目录创建、两个 ContextVar 的设置以及 `finally` 恢复。`config` 的 `thread_id` 告诉检查点系统“这轮属于哪本记录”。例如 A 第二次提问仍传 A，便能接在 A 之前的消息后；传 B 则读取 B 的记录。它与操作系统线程无关。`ainvoke` 完成后才返回最终状态；第 11 步会换成逐段观察。

## 验证方式：关掉连接，再打开

把下面代码写入 `learning/examples/09_checkpoint.py`。开头的路径准备代码必须放在 `import agent.main_agent` **之前**：直接运行这个示例文件时，Python 首先只把 `learning/examples/` 当作搜索位置；加入上一级 `learning/` 后才能找到 `agent/`。

~~~python
import asyncio
import sys
from pathlib import Path

learning_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(learning_root))

import agent.main_agent as agent_module

async def main():
    async with agent_module.agent_runtime() as graph:
        await agent_module.run_deep_agent("请记住代号是蓝色海豚。", "A")
        await agent_module.run_deep_agent("请记住代号是绿色松树。", "B")
        state_a = await graph.aget_state(
            {"configurable": {"thread_id": "A"}}
        )
        print("A 消息数：", len(state_a.values["messages"]))

    async with agent_module.agent_runtime() as graph:
        restored_a = await graph.aget_state(
            {"configurable": {"thread_id": "A"}}
        )
        restored_b = await graph.aget_state(
            {"configurable": {"thread_id": "B"}}
        )
        print("重开后 A 消息数：", len(restored_a.values["messages"]))
        print("重开后 B 消息数：", len(restored_b.values["messages"]))

asyncio.run(main())
~~~

`state_a`、`restored_a`、`restored_b` 是图状态快照，不是数据库连接。A 与 B 都有自己的消息列表；关闭再打开后仍能取得它们。不要打印完整状态到共享日志，因为其中可能包含用户输入。更严格的验证还要检查 A 的消息里有“蓝色海豚”，B 里有“绿色松树”，并确认互不串台。

运行命令：

~~~bash
learning/.venv/bin/python learning/examples/09_checkpoint.py
~~~

这个示例会调用模型，可能花费一些时间和 API 费用。当前文档只提供待实现的教学步骤，尚未声称你本地的检查点已通过验收。下一步会让网页请求触发 `run_deep_agent`。
