import asyncio
import sys
from pathlib import Path

# 这个文件位于 learning/examples/。直接运行它时，Python 会先从 examples/
# 寻找模块；agent/ 却在上一级 learning/，所以需要把 learning/ 加入搜索路径。
# __file__ 是当前脚本的路径；parent 是 examples/，parent.parent 是 learning/。
learning_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(learning_root))

# 必须先设置 sys.path，再导入 agent；否则执行到这一行就会报找不到 agent。
# agent_module 是 agent.main_agent 这个模块，下面通过它调用运行环境和执行函数。
import agent.main_agent as agent_module


async def main():
    # 第一次进入运行环境：agent_runtime() 打开 SQLite 检查点连接，
    # 创建共用这条连接的智能体执行图，并通过 as graph 交给这里使用。
    # 离开这个 async with 时连接会关闭，但数据库文件及其中的记录仍保留。
    async with agent_module.agent_runtime() as graph:
        # 两次调用都要 await，表示等各自的智能体任务真正执行完毕。
        # 第 2 个参数是会话编号：A 的对话记在 A 名下，B 的记在 B 名下。
        await agent_module.run_deep_agent("请记住代号是蓝色海豚。", "A")
        await agent_module.run_deep_agent("请记住代号是绿色松树。", "B")

        # aget_state() 读取执行图保存的状态快照，不会再次向模型提问。
        # 这里指定 thread_id="A"，因此取的是 A 的记录，而不是 B 的。
        state_a = await graph.aget_state(
            {"configurable": {"thread_id": "A"}}
        )
        # values 是状态里的数据字典；messages 是其中的消息列表。
        # len(...) 只统计消息条数，不能单靠这个数字证明 A/B 内容没有串台。
        print("A 消息数：", len(state_a.values["messages"]))

    # 第一次的 SQLite 连接已关闭。这里在同一个 Python 进程中重新打开连接，
    # 用来检查：记录是不是保存在数据库文件里，而非只留在旧 graph 的内存中。
    async with agent_module.agent_runtime() as graph:
        # 仍用相同的 thread_id，分别从新打开的图里取回 A、B 的状态。
        restored_a = await graph.aget_state(
            {"configurable": {"thread_id": "A"}}
        )
        restored_b = await graph.aget_state(
            {"configurable": {"thread_id": "B"}}
        )
        # 两个数字都大于 0，说明重开连接后仍能读到各自的消息；
        # 要验证内容确实分开，还需进一步检查两份 messages 的具体内容。
        print("重开后 A 消息数：", len(restored_a.values["messages"]))
        print("重开后 B 消息数：", len(restored_b.values["messages"]))

# main() 是异步函数；asyncio.run(...) 创建事件循环并运行它。
# Python 执行到脚本末尾这一行时，才会真正启动上面定义的 main()。
asyncio.run(main())
