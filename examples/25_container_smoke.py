import os

import httpx

base = f"http://127.0.0.1:{os.getenv('LEARNING_HOST_PORT', '8001')}"
with httpx.Client(timeout=10, trust_env=False) as client:
    for path in ("/", "/docs"):
        response = client.get(base + path)
        response.raise_for_status()
        print(path, "HTTP", response.status_code)
