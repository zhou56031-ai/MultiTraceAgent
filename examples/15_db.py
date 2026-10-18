import sys
from pathlib import Path

learning_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(learning_root))

from tools.db_tools import list_sql_tables, get_table_data, execute_sql_query

print(list_sql_tables.invoke({}))
print(get_table_data.invoke({"table_name": "orders"}))
print(execute_sql_query.invoke({
    "query": "SELECT category, SUM(total_amount) AS sales FROM orders GROUP BY category"
}))
