from agent.prompts import sub_agents_content
from tools.number_tools import sum_numbers

number_config = sub_agents_content["numbers"]

number_agent = {
    "name": number_config["name"],
    "description": number_config["description"],
    "system_prompt": number_config["system_prompt"],
    "tools": [sum_numbers],
}
