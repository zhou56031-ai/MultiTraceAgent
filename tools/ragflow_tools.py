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

def ask_chat_and_cleanup(chat, question: str) -> str:
    """向已选中的聊天助手提问，并删除本次创建的临时会话。"""
    session = None
    question_failed = False
    try:
        session = chat.create_session(name="learning_temp")
        answer = ""
        for part in session.ask(question=question, stream=True):
            answer = part.content or answer
        return answer or "助手没有返回文字"
    except Exception:
        question_failed = True
        raise
    finally:
        if session is not None:
            try:
                chat.delete_sessions(ids=[session.id])
            except Exception as exc:
                monitor.report_error(
                    f"RAGFlow 临时会话清理失败：{type(exc).__name__}"
                )
                if not question_failed:
                    raise
 


@tool
def create_ask_delete(chat_name: str, question: str) -> str:
    """向指定 RAGFlow 聊天助手提问，结束后删除临时会话。"""
    monitor.report_tool("create_ask_delete", {"chat_name": chat_name})
    try:
        client = get_ragflow_client()
        chats = client.list_chats(name=chat_name)
        chat = next((item for item in chats if item.name == chat_name), None)
        if chat is None:
            return f"没有找到助手：{chat_name}"
        return ask_chat_and_cleanup(chat, question)
    except Exception as exc:
        return f"知识库提问失败：{type(exc).__name__}"

