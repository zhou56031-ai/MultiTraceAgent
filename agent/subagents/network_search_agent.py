from agent.prompts import sub_agents_content
from tools.tavily_tool import internet_search

search_config = sub_agents_content["tavily"]

network_search_agent = {
    "name": search_config["name"],
    "description": search_config["description"],
    "system_prompt": search_config["system_prompt"],
    "tools": [internet_search],
}