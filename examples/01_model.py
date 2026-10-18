import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from agent.llm import model

question = "请用一句话解释什么是多智能体协作。"
reply = model.invoke(question)

print("问题：", question)
print("回答：", reply.content)
assert reply.content, "模型没有返回非空内容"
