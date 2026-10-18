# 第 24 步：重开服务后，A 的记忆仍是 A 的

## 本步要解决的问题

第 09 步引入 SQLite 检查点。代码后来又加入数据库和 RAGFlow 助手、监控、PDF 等分支，不能只靠“服务能启动”判断记忆仍正常。本步给检查点做一次**不调用大模型的真实持久化实验**：A、B 各存一句话，退出运行生命周期，再重新进入并读取。

例子：A 的状态里放“蓝色海豚”，B 放“绿色松树”。退出 `agent_runtime()` 后，内存中的 `main_agent` 会清空；第二次进入后，SQLite 文件仍保存各自消息。若读回串线，后面的网页多会话就不能信任。

## 文件、依赖与调用关系

- **新建 learning/examples/24_checkpoint_regression.py**：只在 `examples/` 放验证脚本。它临时替换 `checkpoint_db_path`，让实验写入系统临时目录，不污染 `learning/data/checkpoints.db`；执行的是正式 `agent_runtime()` 和正式图的 `aupdate_state()/aget_state()`。
- **learning/agent/main_agent.py** 原则上不用改；若实验发现生命周期错误，再定位修复。这里的 `agent_runtime` 负责打开/关闭 SQLite 连接并在进入时建图；`checkpointer` 才真正把状态写到文件。
- **learning/requirements.txt** 不新增包。标准库 `tempfile`、`unittest.mock` 已有；第 09 步安装的 `langgraph-checkpoint-sqlite==3.0.3`、`aiosqlite==0.22.1` 仍需在 learning 虚拟环境中。

**本步没有“替换前/替换后”的正式代码。** `learning/agent/main_agent.py` 的 `agent_runtime()` 保持原样；下面整段是新建 `learning/examples/24_checkpoint_regression.py` 的内容。脚本里的 `patch.object(...)` 只在实验运行期间临时换用测试数据库路径，不会改写正式文件。

从外层目录检查：

~~~bash
learning/.venv/bin/python -c 'from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver; print("SQLite 保存器可用")'
~~~

若缺包，执行 `uv pip install --python learning/.venv/bin/python langgraph-checkpoint-sqlite==3.0.3 aiosqlite==0.22.1`；同时确认这两行在 `learning/requirements.txt` 里。实验不需要 DeepSeek 发请求，但导入 `agent.main_agent` 时仍会构建模型对象，并可能做本地数据库/RAGFlow 的**启动探测**；这与实际生成答案不同。

## 新建 learning/examples/24_checkpoint_regression.py

~~~python
import asyncio
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from langchain_core.messages import AIMessage
import agent.main_agent as runtime


async def main():
    config_a = {"configurable": {"thread_id": "A"}}
    config_b = {"configurable": {"thread_id": "B"}}
    with TemporaryDirectory() as directory:
        database = Path(directory) / "checkpoints.db"
        with (
            patch.dict(
                os.environ,
                {"MYSQL_USER": "", "MYSQL_PASSWORD": "", "MYSQL_DATABASE": ""},
            ),
            patch(
                "tools.ragflow_tools.get_ragflow_client",
                side_effect=RuntimeError("缺少 RAGFlow 配置"),
            ),
            patch.object(runtime, "checkpoint_db_path", database),
        ):
            async with runtime.agent_runtime() as graph:
                await graph.aupdate_state(
                    config_a,
                    {"messages": [AIMessage(content="蓝色海豚")]},
                    as_node="model",
                )
                await graph.aupdate_state(
                    config_b,
                    {"messages": [AIMessage(content="绿色松树")]},
                    as_node="model",
                )
            assert runtime.main_agent is None
            assert database.is_file()

            async with runtime.agent_runtime() as reopened:
                state_a = await reopened.aget_state(config_a)
                state_b = await reopened.aget_state(config_b)
                assert state_a.values["messages"][-1].content == "蓝色海豚"
                assert state_b.values["messages"][-1].content == "绿色松树"
            assert runtime.main_agent is None
    print("A/B 隔离、SQLite 重开恢复、运行资源清理通过")


asyncio.run(main())
~~~

`config_a` 与 `config_b` 是两张不同的“档案卡”，其中 `thread_id` 是会话编号，不是操作系统线程编号。`database` 是本次实验的 SQLite 文件路径；`patch.object` 暂时让正式运行模块用它，离开 `with` 后恢复原配置。`patch.dict` 临时关闭数据库助手的启动连接，另一个 `patch` 让 RAGFlow 探测在本地返回“未配置”，避免这项 SQLite 实验依赖外部服务；两者在代码块结束后恢复。`graph` 是第一次进入生命周期得到的执行图；`reopened` 是第二次新建的图。`aupdate_state` 人工写一条 AI 消息，只检验检查点通路；它没有调用模型，也没有模拟用户消息。`aget_state` 读回来后，`state_a.values["messages"]` 才是 A 的消息列表。

执行轨迹：

~~~text
创建临时目录
→ 第一次进入 agent_runtime：打开临时 SQLite、建图
→ 给 A/B 各写一条不同消息
→ 退出生命周期：main_agent 置 None、SQLite 连接关闭
→ 第二次进入：同一个文件，新连接与新图
→ 按 A/B 的 thread_id 分别读回原消息
→ 再次退出并删除临时目录
~~~

`main_agent = None` 只是撤销当前模块对图的引用，不会清空 SQLite 文件；`TemporaryDirectory` 退出才删除本次练习文件。实际服务的 `learning/data/checkpoints.db` 未被本脚本使用。

运行：

~~~bash
learning/.venv/bin/python learning/examples/24_checkpoint_regression.py
~~~

预期打印三项通过。若卡在建图前的外部服务探测，先区分“启动探测”与“SQLite 测试本身”，不要把网络错误误判为检查点损坏。理解检查：如果第二次读取时把 `config_a` 的 `thread_id` 改成 `"C"`，还会读到“蓝色海豚”吗？

