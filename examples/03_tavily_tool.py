import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from tools.tavily_tool import search_web, internet_search



query = "Python asyncio 官方文档"

result = search_web(query, max_results=2)
# 比较工具调用时，把上一行注释掉，启用下一行：
# result = internet_search.invoke({"query": query, "max_results": 2})

print("实际结果数：", len(result["results"]))
for item in result["results"]:
    print("标题：", item["title"])
    print("链接：", item["url"])