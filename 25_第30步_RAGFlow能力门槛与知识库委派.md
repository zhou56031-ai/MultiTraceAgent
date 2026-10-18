# 第 30 步：把“配置了 RAGFlow”和“知识库真的能回答”分开

## 本步要弄清什么

`RAGFLOW_API_KEY` 有值，仅说明程序拿到了一个字符串。要让知识库助手被主图注册，还必须能访问 API，列出聊天助手；要让答案有根据，聊天助手还得关联已解析的资料。当前在线账户的列表请求曾返回套餐权限错误，所以这个分支目前是**外部条件受阻**。本步先写一个不会泄漏密钥的门槛检查；权限具备时再按同一文档完成真实委派。

例子：你上传一份“退货期限为 7 天”的资料到自己的 RAGFlow 数据集，并创建关联聊天助手。提问“这份资料说退货期限几天？”预期 `get_assistant_list` 能看到助手、`create_ask_delete` 能获得“7 天”并删除临时会话。没有自己的资料时，不要把模型凭常识说“7 天”算知识库检索成功。

## 文件与依赖

- **新建 `learning/examples/30_ragflow_gate.py`**：只报告 `ready`、`empty`、`blocked` 三种状态，以及助手**名称**；不打印 API Key、原始异常或响应头。它调用正式 `get_ragflow_client()`，所以能反映当前服务。
- **仅在门槛为 `ready` 后新建 `learning/examples/30_ragflow_delegate.py`**：通过 HTTP + WebSocket 检查主图的真实委派、知识库工具和答案。门槛未过时先不要运行它。
- **复用 `learning/examples/20_ragflow_cleanup.py`**：本地模拟成功和失败时清理临时会话。它验证控制流，不证明在线 API 权限。
- **核对 `learning/tools/ragflow_tools.py`**：`get_assistant_list()` 列聊天助手，`create_ask_delete()` 经 `ask_chat_and_cleanup()` 创建、提问、删除临时会话。
- **核对 `learning/agent/main_agent.py` → `build_main_agent()`**：只有 `list_chats(page_size=1)` 返回非空名单时，才注册 `knowledge_base_agent`；改变 RAGFlow 状态后需要重启服务重新建图。
- **依赖**：`ragflow-sdk==0.22.1` 已列在 `learning/requirements.txt`。从外层目录检查 `learning/.venv/bin/python -c 'import ragflow_sdk; print("SDK 可导入")'`；若缺失，运行 `uv pip install --python learning/.venv/bin/python -r learning/requirements.txt`。`RAGFLOW_API_URL`、`RAGFLOW_API_KEY` 只放 `learning/.env`。

本步只新建两个示例脚本；正式代码不修改，所以没有“替换前/替换后”。如果门槛失败，不要为了让文档显示“通过”而绕开 `build_main_agent()` 的条件注册。

## 写入 `learning/examples/30_ragflow_gate.py`

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.ragflow_tools import get_ragflow_client


def main():
    try:
        client = get_ragflow_client()
        chats = client.list_chats(page_size=30)
    except Exception as exc:
        print("状态：blocked")
        print("失败类型：", type(exc).__name__)
        print("请检查配置、网络与账户 API 权限；不输出原始错误和密钥")
        return

    if not chats:
        print("状态：empty；API 可访问，但还没有聊天助手")
        return

    print("状态：ready")
    for chat in chats:
        print("聊天助手：", chat.name)


main()
```

## 变量和三种状态

`client` 是 SDK 客户端对象，手里有访问 API 所需的配置；它本身不是聊天助手。`chats` 是服务器返回的聊天助手列表，可能为空。`exc` 是失败对象，这里只打印类型名，因为异常正文可能含请求地址或其他敏感信息。`blocked` 表示无法完成列表请求，原因要在本地排查；`empty` 表示列表成功但没有可用聊天助手；`ready` 表示至少有一个聊天助手，但还需要实际问答才能证明检索可用。

目录关系也要分清：`learning/updated/` 保存本项目网页上传的文件，不会自动进入 RAGFlow。若要让知识库回答，需在 RAGFlow 中另建数据集、上传资料、等待解析、创建关联数据集的聊天助手。这些动作发生在你自己的 RAGFlow 服务界面或 API，不是本示例脚本做的。

真实路径是：

```text
RAGFlow 配置 → SDK list_chats → build_main_agent 决定是否注册内部知识助手
→ 主图收到知识库问题 → task 委派 → get_assistant_list 选助手
→ create_ask_delete 创建临时会话 → ask → finally 删除临时会话
→ 主图整合答案
```

## 门槛通过后，新建 `learning/examples/30_ragflow_delegate.py`

先在你自己的 RAGFlow 中准备**一份只有你知道内容的测试资料**，等解析完成并与聊天助手关联。把资料里的一个独特词组写进本脚本的 `expected_phrase`，把问题写进 `question`；不要把资料全文或密钥写进脚本。下面的 `EXPECTED_PHRASE` 使用环境变量，避免把具体业务内容固定在教程中。

```python
import asyncio
import json
import os
import uuid

import httpx
from websockets.asyncio.client import connect


async def main():
    expected_phrase = os.getenv("EXPECTED_PHRASE", "").strip()
    if not expected_phrase:
        raise RuntimeError("先设置 EXPECTED_PHRASE 为测试资料中的独特短语")
    port = os.getenv("LEARNING_HOST_PORT", "8001")
    thread_id = str(uuid.uuid4())
    assistants = []
    tools = []
    answer = ""

    async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
        async with connect(f"ws://127.0.0.1:{port}/ws/{thread_id}", proxy=None) as socket:
            response = await client.post(
                f"http://127.0.0.1:{port}/api/task",
                json={
                    "thread_id": thread_id,
                    "query": "请委派内部知识助手，查询测试资料中的专有短语是什么；请先检索，不要凭常识猜。",
                },
            )
            response.raise_for_status()
            async with asyncio.timeout(180):
                while True:
                    event = json.loads(await socket.recv())
                    if event.get("type") != "monitor_event":
                        continue
                    kind = event.get("event")
                    data = event.get("data", {})
                    if kind == "assistant_call":
                        assistants.append(data.get("assistant_name"))
                    elif kind == "tool_start":
                        tools.append(data.get("tool_name"))
                    elif kind == "error":
                        raise RuntimeError(f"知识库任务失败：{data.get('detail')}")
                    elif kind == "task_result":
                        answer = str(data.get("result", ""))
                        break

    assert "内部知识助手" in assistants, assistants
    assert "create_ask_delete" in tools, tools
    assert expected_phrase in answer, "答案没有测试资料中的独特短语"
    print("知识库委派、提问与答案通过；请再到 RAGFlow 核对临时会话已删除")


asyncio.run(main())
```

运行前**重启服务**，使 `build_main_agent()` 重新探测可用助手。从外层目录运行 `EXPECTED_PHRASE='你资料里的独特短语' learning/.venv/bin/python learning/examples/30_ragflow_delegate.py`。`expected_phrase` 只用于本地断言，脚本不打印它；如果业务内容不适合进入终端历史，可在当前终端安全地预先设置环境变量。本实验观察到 `create_ask_delete` 开始，仍要检查答案和临时会话清理，不能把 `tool_start` 当作清理成功。

## 执行与继续条件

在外层目录先运行 `learning/.venv/bin/python learning/examples/30_ragflow_gate.py`，再运行 `learning/.venv/bin/python learning/examples/20_ragflow_cleanup.py`。若输出 `blocked`，记录“外部服务受阻”，本步的**门槛诊断**完成，但**真实知识库问答**仍待验证。若输出 `empty`，先在 RAGFlow 创建数据集与聊天助手。只有 `ready` 后，才运行上面的 `30_ragflow_delegate.py`，观察真实委派、提问、答案与临时会话清理；不要把固定短语直接塞进用户问题让模型照抄。

这里不能假定购买套餐或上传资料已经发生；外部状态改变后再执行真实验收。理解检查：为什么 `ready` 仍不能证明模型读到了知识库？为什么 `finally` 中的删除动作在问答失败时也重要？
