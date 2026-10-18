from agent.prompts import sub_agents_content
from tools.db_tools import list_sql_tables, get_table_data, execute_sql_query

config = sub_agents_content["db"]
database_query_agent = {
    "name": config["name"],
    "description": config["description"],
    "system_prompt": config["system_prompt"],
    "tools": [list_sql_tables, get_table_data, execute_sql_query],
}
