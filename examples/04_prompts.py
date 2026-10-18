import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from agent.prompts import main_agent_content, sub_agents_content

search_agent = sub_agents_content["tavily"]

print("主智能体指令：", main_agent_content["system_prompt"])
print("搜索助手名称：", search_agent["name"])
print("搜索助手能力：", search_agent["description"])
print("搜索助手指令：", search_agent["system_prompt"])