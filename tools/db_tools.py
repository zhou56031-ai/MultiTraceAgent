import csv
import os
import re
from io import StringIO
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.tools import tool
from mysql.connector import Error, connect
from api.monitor import monitor

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def get_db_config() -> dict:
    required = ("MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError("缺少数据库配置：" + "、".join(missing))
    return {
        "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.environ["MYSQL_USER"],
        "password": os.environ["MYSQL_PASSWORD"],
        "database": os.environ["MYSQL_DATABASE"],
        "connection_timeout": 5,
    }


def rows_to_csv(cursor) -> str:
    columns = [item[0] for item in cursor.description or []]
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)
    writer.writerows(cursor.fetchmany(100))
    return output.getvalue()


@tool
def list_sql_tables() -> str:
    """列出当前练习数据库中的表名。"""
    monitor.report_tool("list_sql_tables", {})
    try:
        with connect(**get_db_config()) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SHOW TABLES")
                names = [row[0] for row in cursor.fetchall()]
        return "可用表：" + ("、".join(names) if names else "无")
    except (Error, RuntimeError, ValueError) as exc:
        return f"列出表失败：{exc}"


@tool
def get_table_data(table_name: str) -> str:
    """预览指定表的列名与前 100 行。"""
    monitor.report_tool("get_table_data", {"table_name": table_name})
    if not re.fullmatch(r"[A-Za-z0-9_]+", table_name):
        return "错误：表名只能包含字母、数字和下划线"
    try:
        with connect(**get_db_config()) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SHOW TABLES")
                names = {row[0] for row in cursor.fetchall()}
                if table_name not in names:
                    return "错误：表不存在"
                cursor.execute(f"SELECT * FROM `{table_name}` LIMIT 100")
                return rows_to_csv(cursor)
    except (Error, RuntimeError, ValueError) as exc:
        return f"预览表失败：{exc}"


@tool
def execute_sql_query(query: str) -> str:
    """执行一条只读 SELECT 查询，最多返回 100 行。"""
    monitor.report_tool("execute_sql_query", {"query": query})
    statement = query.strip()
    if not re.match(r"^SELECT\b", statement, re.IGNORECASE) or ";" in statement:
        return "错误：当前只允许一条 SELECT 查询"
    try:
        with connect(**get_db_config()) as conn:
            conn.start_transaction(readonly=True)
            with conn.cursor() as cursor:
                cursor.execute(statement)
                return rows_to_csv(cursor)
    except (Error, RuntimeError, ValueError) as exc:
        return f"查询失败：{exc}"
