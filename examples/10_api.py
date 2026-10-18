import httpx

response = httpx.post(
    "http://127.0.0.1:8001/api/task",
    json={"query": "请搜索 Python 官方文档并附上网址"},
    timeout=10,
    trust_env=False,  # 请求本机服务时不读取代理设置，直接连接 127.0.0.1
)
print("HTTP 状态：", response.status_code)
print("提交结果：", response.json())
