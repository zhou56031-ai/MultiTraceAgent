"""模拟搜索响应，实际执行工具和Markdown写入；无真实API调用。"""
import asyncio
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 本实验会模拟 client.search；占位值只供客户端初始化，不请求外部 API。
os.environ["TAVILY_API_KEY"] = "offline-test-placeholder"

from api.context import set_session_context, set_thread_context, reset_session_context
from api.evidence import EvidenceRegistry, set_evidence, reset_evidence, append_source_references
from tools.tavily_tool import internet_search, client
from tools.markdown_tools import generate_markdown
from deepagents import create_deep_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from agent.subagents.network_search_agent import network_search_agent


class ToolAwareFakeModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


async def main():
    registry = EvidenceRegistry()
    token = set_evidence(registry)
    try:
        response = {"results": [
            {"title": "示例来源", "url": "https://example.org/reference", "content": "模拟摘要，不是全文"},
            {"title": "不可用链接", "url": "javascript:alert(1)", "content": "不登记"},
        ]}
        with patch.object(client, "search", return_value=response):
            # 同步工具进入线程后仍取得同一登记册。
            results = await asyncio.gather(*[
                asyncio.to_thread(internet_search.invoke, {"query": "模拟搜索"}) for _ in range(3)
            ])
            # 真正运行deepagents父子图，确认框架内部工具线程也能登记到当前册。
            fake = ToolAwareFakeModel(responses=[
                AIMessage(content="", tool_calls=[{"name": "task", "args": {"subagent_type": "市场情报助手", "description": "模拟搜索"}, "id": "delegate"}]),
                AIMessage(content="", tool_calls=[{"name": "internet_search", "args": {"query": "模拟搜索"}, "id": "search"}]),
                AIMessage(content="子助手模拟引用 [S1]"),
                AIMessage(content="主助手模拟引用 [S1]"),
            ])
            graph = create_deep_agent(model=fake, tools=[], system_prompt="模拟委派实验", subagents=[network_search_agent])
            state = await graph.ainvoke({"messages": [{"role": "user", "content": "请委派搜索"}]})
            assert "[S1]" in state["messages"][-1].content
        assert all(result["results"][0]["source_id"] == "S1" for result in results)
        assert len(registry.snapshot()) == 1
        assert all(len(result["results"]) == 1 for result in results)
        with TemporaryDirectory() as directory:
            path_token = set_session_context(directory)
            thread_token = set_thread_context("evidence-example")
            try:
                generate_markdown.invoke({"filename": "报告", "content": "# 练习\n\n这是模拟结论 [S1]。"})
                saved = (Path(directory) / "报告.md").read_text()
                assert "[S1]" in saved and "https://example.org/reference" in saved
                assert append_source_references(saved) == saved, "重建来源附录不能反复追加"
                assert "模拟摘要" not in str(registry.snapshot()), "账本不保存原始长正文"
            finally:
                reset_session_context(path_token, thread_token)
    finally:
        reset_evidence(token)
    print("通过：并行工具与真实框架父子图共享登记册、来源去重、危险URL排除、报告来源附录；模型与搜索响应为模拟")


if __name__ == "__main__":
    asyncio.run(main())
