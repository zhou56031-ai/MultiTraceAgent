import httpx
response = httpx.get("http://127.0.0.1:8001/", trust_env=False)
print(response.status_code, "新会话" in response.text)
