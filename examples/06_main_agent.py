import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from agent.main_agent import build_main_agent


graph = build_main_agent()
question = (
    "请让市场情报助手搜索 Shopify 官方公布的 "
    "2025 年 Black Friday Cyber Monday 销售数据，并给出来源网址。"
)

for namespace, update in graph.stream(
    {"messages": [{"role": "user", "content": question}]},
    stream_mode="updates",
    subgraphs=True,
):
    for node_name, state in update.items():
        if not isinstance(state, dict):
            continue

        messages = state.get("messages", [])
        messages = getattr(messages, "value", messages)#从指定对象中获取属性值，如果对象没有该属性，则返回默认值（这里是 messages 本身）
        if not isinstance(messages, list):
            continue

        for message in messages:
            calls = getattr(message, "tool_calls", []) or []

            for call in calls:
                if call["name"] == "task":
                    print("主智能体委派给：", call["args"].get("subagent_type"))
                    print("交代的具体任务：", call["args"].get("description"))
                elif call["name"] == "internet_search":
                    print("搜索助手搜索：", call["args"].get("query"))

            if (
                getattr(message, "type", None) == "tool"
                and getattr(message, "name", None) == "internet_search"
            ):
                print("搜索工具已返回结果")

            if (
                not namespace
                and node_name == "model"
                and getattr(message, "type", None) == "ai"
                and not calls
                and message.content
            ):
                print("\n主智能体最终回答：\n", message.content)