# 第 16 步：让知识库助手读取 RAGFlow 中的内部资料

## 本步解决什么问题

数据库适合回答“订单金额是多少”，公开搜索适合回答“网上有什么新闻”。公司内部的运营手册与复盘文档则交给知识库助手。一次具体任务是：“A 会话想知道内部《售后 SOP》如何处理退款。”子助手先列出 RAGFlow 的聊天助手及其知识库，再选一个助手创建临时会话、提问、删除临时会话，把答案交还主智能体。

RAGFlow 是外部服务。本步有两个独立验收：代码能正确构建工具；真实服务已配置时，能列出助手并完成一次实际提问。没有服务时要让主智能体继续使用已完成的搜索、文件与数据库能力，不编造知识库结果。

## 文件与配置

在 `learning/requirements.txt` 增加 `ragflow-sdk==0.22.1`。新建 `learning/agent/rag_config.py`、`learning/tools/ragflow_tools.py`、`learning/agent/subagents/knowledge_base_agent.py`、`learning/examples/16_ragflow.py`；修改 `learning/agent/main_agent.py` 的助手注册逻辑。`learning/.env` 仅在你有真实服务时配置 `RAGFLOW_API_URL` 和 `RAGFLOW_API_KEY`，不要把值写进文档或示例。

## 先弄清每个文件为什么存在

**`agent/rag_config.py`：统一找到 RAGFlow 服务。**工具和启动探测都需要同一组服务地址及凭据，因此在这里从 learning 的 `.env` 读取并检查，再返回给调用者。它只处理配置，不向服务提问；若没有配置，就明确报缺少条件，不让其他代码悄悄使用空地址。

**`tools/ragflow_tools.py`：实际向 RAGFlow 发送请求。**`get_assistant_list` 找到服务中有哪些聊天助手及关联知识库；`create_ask_delete` 选中一个助手，创建临时会话，提问，最后删除临时会话。这些是子智能体真正持有的两件工具。项目里的 `thread_id=A` 用来识别网页与本地检查点；这里临时创建的 RAGFlow `session.id` 是外部服务的一次提问会话，两者不是同一个编号。

**`agent/subagents/knowledge_base_agent.py`：知识库助手的岗位卡。**它从 `prompt/prompts.yml` 取得这位助手的名称、能力说明和操作指令，再把上面两个工具装进去。主智能体依据能力说明决定是否委派；子智能体依据操作指令先列助手、再选合适的知识库提问。单有岗位卡不代表外部服务已经连接成功。

**`agent/main_agent.py`：控制是否注册这位助手。**构图前它检查配置并实际探测服务；只有列到可用聊天助手时，才把岗位卡加入 `subagents`。这样用户询问内部 SOP 时，主模型只会在真实具备能力的情况下委派知识库助手；未配置时仍可运行前面的搜索与文件功能。`requirements.txt` 中的 SDK 只是通信工具包，不能替代 RAGFlow 服务本身。

**`examples/16_ragflow.py`：先验证服务，再验证 Agent。**它先直接调用列表工具，确认真的看见你的助手；填入准确名称后再调用提问工具，并检查临时会话是否清理。只有这层通过，才进入主智能体委派的完整演示。示例不参与正式服务；`.env` 的真实密钥也不应该打印在测试输出里。

实际调用路线：用户问“内部售后 SOP 如何退款” → 主图委派知识库助手 → 它经 `ragflow_tools.py` 找到合适聊天助手 → 在 RAGFlow 创建临时会话并提问 → 回答返回主图 → 临时会话清理 → 主图回答用户。本地 A 会话的目录和 SQLite 记录保持独立。

### 1. agent/rag_config.py：把配置读取集中到一处

~~~python
import os
from pathlib import Path
from dotenv import load_dotenv


def get_ragflow_config() -> tuple[str, str]:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    api_key = os.getenv("RAGFLOW_API_KEY")
    base_url = os.getenv("RAGFLOW_API_URL")
    if not api_key or not base_url:
        raise RuntimeError("缺少 RAGFlow 配置")
    return api_key, base_url
~~~

`get_ragflow_config` 由工具或启动探测函数调用。`api_key` 是访问凭据，`base_url` 是服务地址；返回值是二元组，两项都为字符串。函数本身只读配置，不连接服务。`load_dotenv` 指向 learning 的 `.env`，避免终端从别的目录启动时读错配置。

### 2. tools/ragflow_tools.py：创建客户端与列出助手

~~~python
from langchain_core.tools import tool
from ragflow_sdk import RAGFlow

from agent.rag_config import get_ragflow_config
from api.monitor import monitor


def get_ragflow_client() -> RAGFlow:
    api_key, base_url = get_ragflow_config()
    return RAGFlow(api_key=api_key, base_url=base_url)


@tool
def get_assistant_list() -> str:
    """列出 RAGFlow 中可用的聊天助手及关联知识库。"""
    monitor.report_tool("get_assistant_list", {})
    try:
        chats = get_ragflow_client().list_chats(page_size=30)
        if not chats:
            return "没有可用的知识库聊天助手"
        lines = []
        for chat in chats:
            datasets = getattr(chat, "datasets", []) or []
            names = [
                item.get("name", "") if isinstance(item, dict)
                else getattr(item, "name", "")
                for item in datasets
            ]
            lines.append(
                f"助手：{chat.name}；说明：{chat.description}；"
                f"知识库：{'、'.join(names)}"
            )
        return "\n".join(lines)
    except Exception as exc:
        return f"查询 RAGFlow 助手失败：{exc}"
~~~

`get_ragflow_client` 每次从配置创建 SDK 客户端，返回 `RAGFlow` 对象；创建对象不等于服务一定在线。`list_chats` 才真正请求服务。`chats` 是聊天助手对象列表，`chat.datasets` 是它关联的知识库信息。代码兼容数据项为字典或对象两种形状。`lines` 收集供模型阅读的说明文字；没有助手时返回明确结果。`monitor.report_tool` 报告开始，不执行网络请求。

### 3. 提问后一定清理临时会话

继续修改 `learning/tools/ragflow_tools.py`：在已有 `get_assistant_list()` 后增加：

~~~python
@tool
def create_ask_delete(chat_name: str, question: str) -> str:
    """向指定 RAGFlow 聊天助手提问，结束后删除临时会话。"""
    monitor.report_tool(
        "create_ask_delete", {"chat_name": chat_name, "question": question}
    )
    chat = None
    session = None
    try:
        client = get_ragflow_client()
        chats = client.list_chats(name=chat_name)
        chat = next((item for item in chats if item.name == chat_name), None)
        if chat is None:
            return f"没有找到助手：{chat_name}"

        session = chat.create_session(name="learning_temp")
        answer = ""
        for part in session.ask(question=question, stream=True):
            answer = part.content or answer
        return answer or "助手没有返回文字"
    except Exception as exc:
        return f"知识库提问失败：{exc}"
    finally:
        if chat is not None and session is not None:
            try:
                chat.delete_sessions(ids=[session.id])
            except Exception as cleanup_error:
                print(f"临时会话清理失败：{cleanup_error}")
~~~

`chat_name` 来自前一步列出的助手名称，`question` 是这次具体问题。`list_chats(name=...)` 查找候选，`next(...)` 选名字完全相同的助手。`session` 是本次在 RAGFlow 创建的临时对话对象；`session.ask(..., stream=True)` 逐段得到回答对象，`part.content` 是文字。这里把 `answer` 更新为最新的完整内容；如果服务返回的是增量片段，应根据实际服务行为调整拼接方式，不能未经检查就假定。`finally` 在成功、提问失败或函数提前返回时都尝试删除已创建的临时会话。`session=None` 时表示尚未创建，不需删除。

删除会话是清理外部资源，不会删除你的知识库文档。清理失败会打印错误；当前工具仍可能返回提问答案，所以排错时要同时看服务器日志。第 17 步可把这类失败变成结构化通知。

### 4. 子助手配置与按实际服务注册

`agent/subagents/knowledge_base_agent.py`：

~~~python
from agent.prompts import sub_agents_content
from tools.ragflow_tools import get_assistant_list, create_ask_delete

config = sub_agents_content["ragflow"]
knowledge_base_agent = {
    "name": config["name"],
    "description": config["description"],
    "system_prompt": config["system_prompt"],
    "tools": [get_assistant_list, create_ask_delete],
}
~~~

修改 `learning/agent/main_agent.py` 的 `build_main_agent()`：找到第 15 步写在 `create_deep_agent(...)` 之前的 `subagents` 列表和数据库助手追加代码；在它们之后、`create_deep_agent(...)` 之前增加下面的 RAGFlow 服务探测与助手追加代码：

~~~python
try:
    from tools.ragflow_tools import get_ragflow_client
    chats = get_ragflow_client().list_chats(page_size=1)
    if chats:
        from agent.subagents.knowledge_base_agent import knowledge_base_agent
        subagents.append(knowledge_base_agent)
except Exception:
    pass  # 未配置或服务不可用：保持现有助手名单
~~~

实践中应记录不含密钥的失败原因。`chats` 为空说明服务可访问但没有可用聊天助手，也先不注册。重新构建执行图时才重新探测；服务中途变化不会自动刷新当前图。修改 `learning/prompt/prompts.yml` 的主助手能力描述，并在 `learning/agent/main_agent.py` 的 `build_main_agent()` 中按实际名单生成提示词，不要永久写死“三个助手”。

### 5. examples/16_ragflow.py：两层验收

~~~python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.ragflow_tools import get_assistant_list, create_ask_delete

print(get_assistant_list.invoke({}))
# 只有上一步确实列出你的真实助手后，再填入它的准确名字：
# print(create_ask_delete.invoke({
#     "chat_name": "实际助手名称",
#     "question": "售后 SOP 如何处理退款？",
# }))
~~~

在外层目录运行：

~~~bash
learning/.venv/bin/python learning/examples/16_ragflow.py
~~~

先确认列表来自真实 RAGFlow 服务，再启用第二段提问，最后从服务端核对临时会话已删除。主智能体的最终验收是看到它通过 `task` 委派知识库助手并拿到真实答案。没有服务时，本步记录“知识库分支未连接/未验证”，不影响前面已通过的基础链路。本文件是教学文档，尚未替你创建正式实现或宣称真实服务已通过。
