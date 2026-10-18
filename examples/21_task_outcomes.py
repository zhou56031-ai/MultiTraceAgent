import asyncio
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from langchain_core.messages import AIMessage
import agent.main_agent as runtime


class FakeGraph:
    async def astream(self, *args, **kwargs):
        yield {"model": {"messages": [AIMessage(content="阶段文字")]}}
        yield {"model": {"messages": [AIMessage(content="正式答案")]}}


class FakeCancelledGraph:
    async def astream(self, *args, **kwargs):
        if False:
            yield {}
        raise asyncio.CancelledError()


async def main():
    with TemporaryDirectory() as directory:
        with patch.object(runtime, "project_root_path", Path(directory)):
            with patch.object(runtime, "main_agent", FakeGraph()):
                with patch.object(runtime.monitor, "report_task_result") as report:
                    answer = await runtime.run_deep_agent("请回答", "A")
                    assert answer == "正式答案"
                    report.assert_called_once_with("正式答案")
            with patch.object(runtime, "main_agent", FakeCancelledGraph()):
                with patch.object(runtime.monitor, "report_task_cancelled") as cancelled:
                    try:
                        await runtime.run_deep_agent("等待中的任务", "B")
                    except asyncio.CancelledError:
                        pass
                    else:
                        raise AssertionError("取消应向上抛出")
                    cancelled.assert_called_once()
    print("图结束只报告一次结果；取消事件也已报告")


asyncio.run(main())
