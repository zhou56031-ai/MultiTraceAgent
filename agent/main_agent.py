import asyncio
import os
import shutil
from pathlib import Path
from contextlib import asynccontextmanager

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from deepagents import create_deep_agent

from agent.llm import model
from agent.prompts import main_agent_content
from agent.subagents.network_search_agent import network_search_agent
from agent.subagents.number_agent import number_agent
from api.monitor import monitor
from api.evidence import (
    EvidenceRegistry, append_source_references, get_evidence, reset_evidence, set_evidence,
)
from tools.markdown_tools import generate_markdown
from tools.upload_file_read_tool import read_file_content

def build_main_agent(checkpointer=None):
    # 搜索和数字助手都不依赖额外业务服务，启动时放进名单
    subagents = [network_search_agent, number_agent]

    # 三项数据库配置都有值，才尝试启用数据库助手
    if all(
        os.getenv(key)
        for key in ("MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE")
    ):
        from mysql.connector import Error, connect
        from tools.db_tools import get_db_config

        try:
            # 这里只测试能否连接；真正查订单由数据库工具完成
            with connect(**get_db_config()) as conn:
                from agent.subagents.database_query_agent import database_query_agent

                subagents.append(database_query_agent)
        except (Error, RuntimeError, ValueError) as exc:
            print(f"数据库助手未启用：{type(exc).__name__}")

    # 只有 RAGFlow 确实能列出聊天助手，才把知识库助手交给主智能体
    try:
        from tools.ragflow_tools import get_ragflow_client

        chats = get_ragflow_client().list_chats(page_size=1)
        if chats:
            from agent.subagents.knowledge_base_agent import knowledge_base_agent

            subagents.append(knowledge_base_agent)
        else:
            print("知识库助手未启用：RAGFlow 中没有可用的聊天助手")
    except Exception as exc:
        # 只记录可确认的原因，不输出可能包含密钥的原始异常正文
        if isinstance(exc, RuntimeError) and str(exc) == "缺少 RAGFlow 配置":
            reason = "缺少 RAGFlow 配置"
        elif "upgrade to a starter or pro plan" in str(exc).lower():
            reason = "在线账户当前套餐没有 API 调用权限"
        else:
            reason = f"探测失败（{type(exc).__name__}）"
        print(f"知识库助手未启用：{reason}")

    assistant_descriptions = "\n".join(
        f"{index}. {agent['name']} — {' '.join(agent['description'].split())}"
        for index, agent in enumerate(subagents, start=1)
    )

    tools = [generate_markdown, read_file_content]
    pdf_capability = "当前未注册 PDF 工具；若用户要求 PDF，说明目前无法转换。"
    try:
        from tools.pdf_tools import convert_md_to_pdf
    except (ImportError, OSError) as exc:
        print(f"PDF 工具未启用：{type(exc).__name__}")
    else:
        tools.append(convert_md_to_pdf)
        pdf_capability = "当前可生成 PDF：先生成 Markdown，再调用 convert_md_to_pdf。"

    system_prompt = (
        main_agent_content["system_prompt"]
        .replace("{available_subagents}", assistant_descriptions)
        .replace("{pdf_capability}", pdf_capability)
    )

    # 把最终名单交给主智能体
    return create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        subagents=subagents,
        checkpointer=checkpointer,
    )

from api.context import (
    reset_session_context, set_session_context, set_thread_context,
)

project_root_path = Path(__file__).resolve().parent.parent


async def run_deep_agent(task_query: str, session_id: str, *, report_outcome: bool = True) -> str:
    session_dir = project_root_path / "output" / f"session_{session_id}"
    session_dir.mkdir(parents=True, exist_ok=True)
    uploaded_dir = project_root_path / "updated" / f"session_{session_id}"
    uploaded_names = []
    if uploaded_dir.is_dir():
        for source in uploaded_dir.iterdir():#列举所有文件和目录
            if source.is_file():
                shutil.copy2(source, session_dir / source.name)
                uploaded_names.append(source.name)

    question_for_agent = task_query
    if uploaded_names:
        names = "、".join(uploaded_names)
        question_for_agent += (
            f"\n当前会话上传了这些文件：{names}。"
            "请先用 read_file_content 读取相关文本文件，再回答。"
            "读取工具的 filename 只传文件名。"
        )

    session_token = set_session_context(str(session_dir))
    thread_token = set_thread_context(session_id)
    evidence_token = set_evidence(EvidenceRegistry()) if get_evidence() is None else None
    try:
        if main_agent is None:
            raise RuntimeError("智能体尚未初始化")

        config = {"configurable": {"thread_id": session_id}}
        monitor.report_session_dir(str(session_dir))
        final_answer = ""
        try:
            async for update in main_agent.astream(
                {"messages": [{"role": "user", "content": question_for_agent}]},
                config=config,
                stream_mode="updates",
            ):
                for node_name, state in update.items():
                    if node_name != "model" or not isinstance(state, dict):
                        continue
                    messages = state.get("messages", [])
                    messages = getattr(messages, "value", messages)
                    if not isinstance(messages, list) or not messages:
                        continue
                    last = messages[-1]
                    calls = getattr(last, "tool_calls", []) or []
                    for call in calls:
                        if call["name"] == "task":
                            monitor.report_assistant(
                                call["args"]["subagent_type"],
                                call["args"]["description"],
                            )
                    if not calls and getattr(last, "content", None):
                        final_answer = str(last.content)
                        
            if not final_answer:
                raise RuntimeError("主智能体结束但没有文字结果")
            final_answer = append_source_references(final_answer)
            if report_outcome:
                monitor.report_task_result(final_answer)
            return final_answer

        except asyncio.CancelledError:
            if report_outcome:
                monitor.report_task_cancelled()
            raise
        except Exception as exc:
            if report_outcome:
                monitor.report_error(type(exc).__name__)
            raise

    finally:
        if evidence_token is not None:
            reset_evidence(evidence_token)
        reset_session_context(session_token, thread_token)


checkpoint_db_path = project_root_path / "data" / "checkpoints.db"
main_agent = None


@asynccontextmanager
async def agent_runtime():
    global main_agent
    checkpoint_db_path.parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(
        str(checkpoint_db_path)
    ) as checkpointer:
        main_agent = build_main_agent(checkpointer)
        try:
            yield main_agent
        finally:
            main_agent = None
