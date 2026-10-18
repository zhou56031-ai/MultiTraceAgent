from agent.prompts import sub_agents_content
from tools.ragflow_tools import get_assistant_list, create_ask_delete

config = sub_agents_content["ragflow"]
knowledge_base_agent = {
    "name": config["name"],
    "description": config["description"],
    "system_prompt": config["system_prompt"],
    "tools": [get_assistant_list, create_ask_delete],
}
