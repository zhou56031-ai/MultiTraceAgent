"""在临时目录核对00～06教程快照；模型/搜索均模拟，禁止外部连接。"""
import ast
import os
import re
import runpy
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
DOCS = sorted(ROOT.glob('01_第0*.md'))
SOURCES = [
    (0,'python','import sys\n','examples/check_environment.py'),
    (1,'python','import os\n','agent/llm.py'),
    (1,'python','import sys\n','examples/01_model.py'),
    (2,'python','from langchain_core.tools import tool\n','examples/02_tool_basics.py'),
    (3,'python','import os\n','tools/tavily_tool.py'),
    (3,'python','import sys\n','examples/03_tavily_tool.py'),
    (4,'yaml','main_agent:\n','prompt/prompts.yml'),
    (4,'python','from pathlib import Path\n','agent/prompts.py'),
    (4,'python','import sys\n','examples/04_prompts.py'),
    (5,'python','from agent.prompts import sub_agents_content\n','agent/subagents/network_search_agent.py'),
    (5,'python','import sys\n','examples/05_network_search_agent.py'),
    (6,'python','from deepagents import create_deep_agent\n','agent/main_agent.py'),
    (6,'python','import sys\n','examples/06_main_agent.py'),
]


def extract(text, language, prefix):
    blocks = re.findall(r'```' + re.escape(language) + r'\n(.*?)\n```', text, re.S)
    return next(block + '\n' for block in blocks if block.startswith(prefix))


def worker(project):
    sys.path.insert(0, str(project))
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage

    class FakeModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    def example(name, *arguments):
        with patch.object(sys, 'argv', [name, *arguments]):
            runpy.run_path(str(project/'examples'/name), run_name='__main__')

    with patch('socket.socket.connect', side_effect=RuntimeError('离线验收禁止出网')):
        import agent.llm as llm
        with patch.object(llm, 'model', FakeModel(responses=[AIMessage(content='离线模型回复')])):
            example('01_model.py')
        example('02_tool_basics.py')
        import tools.tavily_tool as search
        response = {'results': [{'title':'模拟资料','url':'https://example.invalid/source','content':'模拟摘要'}]}
        with patch.object(search.client, 'search', return_value=response):
            example('03_tavily_tool.py','plain')
            example('03_tavily_tool.py','tool')
        example('04_prompts.py')
        example('05_network_search_agent.py')
        import agent.main_agent as runtime
        assert {'model','tools'} <= set(runtime.build_main_agent().get_graph().nodes)
        fake = FakeModel(responses=[
            AIMessage(content='', tool_calls=[{'name':'task','args':{'subagent_type':'市场情报助手','description':'模拟搜索'},'id':'delegate'}]),
            AIMessage(content='', tool_calls=[{'name':'internet_search','args':{'query':'模拟资料'},'id':'search'}]),
            AIMessage(content='模拟子助手结果'), AIMessage(content='模拟主助手结果'),
        ])
        with patch.object(runtime,'model',fake), patch.object(search.client,'search',return_value=response):
            example('06_main_agent.py')
        blocks = re.findall(r'~~~python\n(.*?)\n~~~', (ROOT/'02_第07步_会话目录与ContextVar.md').read_text(), re.S)
        context = next(block for block in blocks if block.startswith('from contextvars import'))
        append = next(block for block in blocks if block.startswith('from pathlib import Path\nfrom api.context import'))
        (project/'api/context.py').write_text(context)
        namespace = {'__file__':str(project/'agent/main_agent.py')}
        exec(compile((project/'agent/main_agent.py').read_text()+'\n'+append, 'step7','exec'), namespace)
        assert callable(namespace['run_deep_agent'])
    print('通过：00～06教程语法、导入、真实框架构图与模拟父子委派、第07步追加衔接；未请求真实API')


def main():
    assert len(DOCS) == 7
    with TemporaryDirectory(prefix='learning-foundations-') as directory:
        project = Path(directory)/'learning'
        for name in ('agent','agent/subagents','api','tools','utils','examples'):
            (project/name).mkdir(parents=True, exist_ok=True)
            (project/name/'__init__.py').touch()
        for index, language, prefix, name in SOURCES:
            source = extract(DOCS[index].read_text(), language, prefix)
            if language == 'python':
                ast.parse(source, filename=name)
            target = project/name
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(source)
        values = {'OPENAI_API_KEY':'offline-test-placeholder','TAVILY_API_KEY':'offline-test-placeholder',
                  'OPENAI_BASE_URL':'https://example.invalid/v1','LLM_QWEN_MAX':'offline-test-model'}
        (project/'.env').write_text('\n'.join(f'{key}={value}' for key,value in values.items()))
        environment = os.environ.copy()
        environment.update(values)
        subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker',str(project)],env=environment,check=True)
    print('临时教程项目已清理，未改动成品源码或真实.env；第00步环境脚本仅做语法检查')


if __name__ == '__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--worker':
        worker(Path(sys.argv[2]))
    else:
        main()
