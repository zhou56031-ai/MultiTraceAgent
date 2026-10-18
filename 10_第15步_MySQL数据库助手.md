# 第 15 步：让数据分析助手查询练习数据库

## 本步解决什么问题

到第 14 步，主智能体能查公开网页、读写会话文件。现在加入另一种问题：“A 会话想知道练习订单表中各品类销售额。”公开搜索找不到内部订单，必须由数据库助手连接 MySQL、识别表结构、执行只读查询，再把结果交给主智能体。

数据库不是装了 `mysql-connector-python` 就自动存在；`.env` 有值也不等于服务可连接。没配置或连不上时，本步的数据库助手不能冒充已查询成功。

## 文件与准备

在 `learning/requirements.txt` 增加 `mysql-connector-python==9.6.0`。新建 `learning/tools/db_tools.py`、`learning/agent/subagents/database_query_agent.py`、`learning/examples/15_db.py`，修改 `learning/agent/main_agent.py` 的子助手列表。练习数据可放 `learning/sql/init.sql`；这属于数据库初始化数据，不是 Python 测试入口。

## 先弄清每个文件为什么存在

**`tools/db_tools.py`：实际与 MySQL 说话的地方。**三个工具分别列出表、预览表、执行只读查询。模型可以提出“查各品类销售额”，但只有工具里的数据库连接和 `cursor.execute` 真正向 MySQL 发命令；返回的 CSV 文字才是模型能分析的数据。这个文件还统一读取连接配置并处理游标关闭。如果只写了“数据分析助手”提示词而没有工具，模型没有办法取得真实订单。

**`agent/subagents/database_query_agent.py`：数据库助手的岗位卡。**它从 `prompt/prompts.yml` 取名字、能力说明和工作指令，把 `db_tools.py` 的三个工具装进同一个配置字典。主智能体读取这张岗位卡，才知道“涉及内部订单时可委派给谁”；子智能体也只能使用岗位卡里注册的工具。它不直接建立数据库连接；真实查询发生在工具被调用时。

**`agent/main_agent.py`：决定要不要让这位助手上岗。**`build_main_agent` 本来只注册搜索助手；本步在数据库配置齐全且连接可用时，把数据库助手追加到列表再构建图。配置缺失或服务不可用时保持原名单，同时在当前能力说明中如实反映。`prompt/prompts.yml` 中存在 `db` 配置，不等于运行中的主图已经注册了它。

**`sql/init.sql` 是练习数据的“题目材料”，`.env` 是本地连接地址与账号。**初始化脚本创建示例订单表和几条可预测的数据，便于核对聚合结果；它不是 Python 程序，须由 MySQL 管理端执行。`.env` 中的密码只供本机读取，不写进文档。`requirements.txt` 记录连接器版本，安装后包才真正进入 `.venv`。

**`examples/15_db.py`：绕过模型先验工具。**它直接调用 `list_sql_tables`、`get_table_data` 和 `execute_sql_query`。若这些都不能读到“数码 300、服饰 50”，就先修连接或 SQL，不要把失败归咎于主智能体的委派。工具通过后，才用真实用户提问验证“主图 → 数据库助手 → 工具 → 回答”的完整链路。

一次请求的顺序是：用户问“订单各品类销售额” → `agent/main_agent.py` 中的主图看见数据库助手的岗位卡 → `task` 把任务交给它 → 它按提示先摸清表和字段，再调用 `db_tools.py` 查询 → 查询文字返回主模型 → 主模型作答。

如果本机已有可用 MySQL，建立一个仅供练习的数据库和**只读应用账号**。示意 SQL（用你自己的管理员连接执行，密码填在本地，不要写进文档）：

~~~sql
CREATE DATABASE IF NOT EXISTS learning_search;
USE learning_search;
CREATE TABLE IF NOT EXISTS orders (
  id INT PRIMARY KEY,
  category VARCHAR(50),
  total_amount DECIMAL(10,2)
);
INSERT INTO orders VALUES
  (1, '数码', 100.00),
  (2, '数码', 200.00),
  (3, '服饰', 50.00);
CREATE USER IF NOT EXISTS 'learning_reader'@'127.0.0.1'
  IDENTIFIED BY '请在本机设置密码';
GRANT SELECT ON learning_search.* TO 'learning_reader'@'127.0.0.1';
~~~

`GRANT SELECT` 让这个练习账号只读。若你使用远程 MySQL、Docker 或其他地址，账号的 host 部分按实际服务配置。`learning/.env` 增加 `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、`MYSQL_PASSWORD`、`MYSQL_DATABASE`，只写真实值到本地忽略提交的文件。

当前学习环境已用独立 Docker 容器 `learning-search-mysql` 完成这一步：容器只把 MySQL 的 3306 端口映射到宿主机 `127.0.0.1:3306`，示例建表和数据在 `learning/sql/init.sql`；只读账号为 `learning_reader`。Docker 端口转发后，MySQL 看到的连接来源未必是 `127.0.0.1`，因此此容器中的账号 host 使用 `%`，而对外监听仍限制在宿主机回环地址。管理员配置在 Git 忽略的 `learning/.mysql-root.env`，应用连接配置在 Git 忽略的 `learning/.env`；文档不记录密码。两个本地文件权限均为 `600`。

Docker Desktop 运行时，可在项目根目录用 `docker start learning-search-mysql` 启动练习库，用 `docker stop learning-search-mysql` 停止；首次容器和数据卷已经创建，无需重新运行初始化 SQL。已从宿主机使用只读账号验证聚合结果为数码 `300.00`、服饰 `50.00`，并确认 `INSERT` 被拒绝。数据库助手的工具与委派代码仍需按本步骤后续部分实现。

### 1. tools/db_tools.py：配置与结果格式

~~~python
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
~~~

`get_db_config` 由下面的查询工具调用，把环境变量整理成连接参数字典。`required` 是必须有的三项；`missing` 是缺少的名字列表，不打印密码值。`port` 从文字变成整数。`rows_to_csv` 把游标当前查询结果的列名和最多 100 行写成 CSV 文字；`csv.writer` 能正确处理值中含逗号的情况。`cursor` 是一条数据库连接创建的查询游标，用完要关闭。`StringIO` 是内存中的文本缓冲区，不是磁盘文件。

### 2. 三个业务工具

~~~python
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
~~~

`list_sql_tables` 先告诉模型有哪些表；`get_table_data` 验证表名确实存在，再预览列和数据；`execute_sql_query` 接受模型给出的 SQL，只允许单条以 SELECT 开头的查询，并在数据库只读事务中执行。程序限制与只读数据库账号一起约束操作，不能仅靠提示词说“别修改数据”。`fetchmany(100)` 限制**返回行数**，但复杂查询本身仍可能耗时；第 17 步再增加更细的超时与失败处理。

每个工具里 `with connect(...)` 打开连接，内部 `with conn.cursor()` 打开游标；离开两个代码块时释放资源。`monitor.report_tool` 仅报告“工具开始”，真正数据库动作发生在 `cursor.execute`。示例数据里：

~~~sql
SELECT category, SUM(total_amount) AS sales
FROM orders GROUP BY category
~~~

应得到数码 300.00、服饰 50.00（CSV 行顺序由数据库决定）。

### 3. 子助手与主助手注册

`agent/subagents/database_query_agent.py`：

~~~python
from agent.prompts import sub_agents_content
from tools.db_tools import list_sql_tables, get_table_data, execute_sql_query

config = sub_agents_content["db"]
database_query_agent = {
    "name": config["name"],
    "description": config["description"],
    "system_prompt": config["system_prompt"],
    "tools": [list_sql_tables, get_table_data, execute_sql_query],
}
~~~

这和第 05 步的搜索助手是同一种四字段字典。`description` 告诉主智能体何时委派，`system_prompt` 告诉数据库助手具体工作顺序，`tools` 决定它真正能做什么。

修改 `learning/agent/main_agent.py`：在文件顶部补充 `import os`；在 `build_main_agent()` 内，找到 `create_deep_agent(...)` 原有的 `subagents=[network_search_agent]`，先在调用它之前创建下面的 `subagents` 列表并按连接结果追加，最后把那个参数改成 `subagents=subagents`：

~~~python
subagents = [network_search_agent]
if all(os.getenv(key) for key in
       ("MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE")):
    from mysql.connector import connect, Error
    from tools.db_tools import get_db_config
    try:
        with connect(**get_db_config()) as conn:
            from agent.subagents.database_query_agent import database_query_agent
            subagents.append(database_query_agent)
    except (Error, RuntimeError, ValueError):
        pass

# create_deep_agent(..., subagents=subagents, ...)
~~~

这里的 `pass` 只表示“数据库助手不注册”，应另打印不含密钥的连接失败原因，便于排查。还要修改 `learning/prompt/prompts.yml` 中主助手的能力描述，并让 `learning/agent/main_agent.py` 的 `build_main_agent()` 按实际 `subagents` 名单生成当前能力说明；不能继续声称永远只有搜索助手。注册成功后，模型才能通过 `task` 指定数据库助手。

## 运行与验收

`learning/examples/15_db.py` 是独立运行的脚本；它位于 `examples/`，而 `tools/` 位于上一级 `learning/`。因此必须先把 `learning/` 加入 Python 模块搜索路径，再导入工具：

~~~python
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
~~~

在外层目录运行 `learning/.venv/bin/python learning/examples/15_db.py`。本地已运行此脚本：查到 `orders` 表及三条记录，聚合结果为数码 `300.00`、服饰 `50.00`。验收仍分三层：能连通 MySQL、三个工具能读出练习数据、主模型能委派数据库助手回答问题；当前已验证前两层，主图委派尚需单独运行。仅 `import` 成功或 `.env` 有值不算数据库查询成功。若没有 MySQL 服务，保留这一文档与未启用分支，明确标记“未做真实查询”，继续下一步不影响基础搜索链路。
