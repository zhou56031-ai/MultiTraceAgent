import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from agent.subagents.network_search_agent import network_search_agent
from tools.tavily_tool import internet_search

print("助手名称：", network_search_agent["name"])
print("能力说明：", network_search_agent["description"])
print("工作指令：", network_search_agent["system_prompt"])
print("工具数量：", len(network_search_agent["tools"]))

first_tool = network_search_agent["tools"][0]
print("工具名称：", first_tool.name)
print("是否是同一个工具对象：", first_tool is internet_search)