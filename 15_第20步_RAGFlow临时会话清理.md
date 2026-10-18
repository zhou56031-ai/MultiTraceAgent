# 第 20 步：知识库提问失败，也要收好临时会话

## 本步要解决的问题

第 16 步的知识库工具会在 RAGFlow 创建一段临时聊天会话，问完后删除。若提问中途报错、网络断开或删除本身失败，要分别说清“答案怎样了”“会话是否清理”。这和打电话相似：通话内容没听清，也不能忘记挂断；挂断失败，不能说通话已正常结束。

本步用**假聊天助手**模拟成功和提问异常，不调用真实 RAGFlow，也不需要 API 额度。真实接入是否成功仍由第 16 步的真实服务验收决定。

## 文件与依赖

- **修改 learning/tools/ragflow_tools.py**：在 `get_ragflow_client()` 后、`@tool def create_ask_delete()` 前新增 `ask_chat_and_cleanup()`，把“创建—提问—删除”的资源生命周期集中起来。再让原工具调用这个函数。`get_assistant_list()` 和配置读取不改。
- **新建 learning/examples/20_ragflow_cleanup.py**：用假对象验证成功与异常两条路都调用删除。示例是验证入口，不接入真实服务。
- **learning/requirements.txt** 无新增包；继续使用已有 `ragflow-sdk==0.22.1`。在外层目录执行 `learning/.venv/bin/python -c 'import ragflow_sdk; print("SDK 可导入")'` 即可检查。若缺包，执行 `uv pip install --python learning/.venv/bin/python ragflow-sdk==0.22.1`。
- 这一步不修改 `learning/.env`，不把密钥或知识库正文写进实验输出。

## 1. 新增普通函数：谁负责创建，谁负责删除

在 **learning/tools/ragflow_tools.py** 的 `create_ask_delete` 之前加入：

~~~python
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
~~~

`chat` 是上一步 `list_chats(name=...)` 选出的聊天助手对象，不是名字字符串。`question` 是本次用户问题。`session=None` 表示还没创建；创建成功才有 `session.id` 能用于删除。`question_failed` 记住提问是否已抛异常：如果已经失败，清理时又失败，保留原始提问异常交给外层，同时用 monitor 报告清理失败；若提问成功但清理失败，则让清理错误向上抛，不能假装整个操作完整成功。

`finally` 是本函数的“离场动作”：`return` 正要把答案交出去时也会先执行它；`session.ask` 抛错后也会执行它。`monitor.report_error` 仅报告清理问题，它本身没有再次删除会话。这里把 `part.content` 当成逐次更新的完整回答；若你使用的 RAGFlow 版本返回增量片段，需按真实返回行为调整拼接，不能只看变量名猜测。

| 变量 | 创建前 | 成功提问后 | 提问失败后 |
| --- | --- | --- | --- |
| `session` | `None` | 指向临时会话对象 | 若创建已成功，仍指向该对象 |
| `answer` | 尚未赋值 | 最后一段完整回答 | 可能只有部分回答 |
| `question_failed` | `False` | `False` | `True` |
| 删除动作 | 不执行 | `finally` 删除 `session.id` | `finally` 仍尝试删除 |

## 2. 修改原有工具的调用位置

在 **learning/tools/ragflow_tools.py** 中，找到现有 `@tool def create_ask_delete(...)`，把**整个函数**替换成以下完整版本：

~~~python
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
~~~

新版本**没有旧函数末尾的 `finally` 清理块**，否则会重复删除。`create_ask_delete` 负责找助手并把回答/错误转成工具文字；`ask_chat_and_cleanup` 负责一次真实 RAGFlow 会话的创建与清理。`monitor.report_tool` 只包含助手名，不把可能含内部资料的 `question` 放进网页事件。发生异常时只回异常类型，避免服务响应正文或密钥进入工具输出。若你需要更多调试信息，应另做经脱敏的内部日志。

完整顺序：模型调用工具 → 查到“售后助手”对象 → `ask_chat_and_cleanup(chat, "如何退款")` → 创建会话 S → 提问 → 删除 S → 答案返回模型。工具返回答案不代表模型已复述给用户；它还要经过主子智能体执行图。

## 3. 新建 learning/examples/20_ragflow_cleanup.py

~~~python
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.ragflow_tools import ask_chat_and_cleanup


class FakeSession:
    id = "temporary-S"

    def __init__(self, fail: bool):
        self.fail = fail

    def ask(self, question: str, stream: bool):
        if self.fail:
            raise RuntimeError("模拟提问失败")
        yield SimpleNamespace(content="退款期限是七天")


class FakeChat:
    def __init__(self, fail: bool):
        self.fail = fail
        self.deleted = []

    def create_session(self, name: str):
        return FakeSession(self.fail)

    def delete_sessions(self, ids: list[str]):
        self.deleted.extend(ids)


success = FakeChat(fail=False)
assert "七天" in ask_chat_and_cleanup(success, "如何退款")
assert success.deleted == ["temporary-S"]

failure = FakeChat(fail=True)
try:
    ask_chat_and_cleanup(failure, "如何退款")
except RuntimeError:
    pass
else:
    raise AssertionError("预期提问失败")
assert failure.deleted == ["temporary-S"]
print("成功和提问失败两条路线都清理了临时会话")
~~~

在外层目录运行 `learning/.venv/bin/python learning/examples/20_ragflow_cleanup.py`。这证明的是**本地清理逻辑**，没有证明真实 RAGFlow API 有权限或远端确实删除成功。理解检查：如果 `create_session` 自身失败，为什么不能调用 `delete_sessions(ids=[session.id])`？下一步追踪整个 Agent 任务的成功、失败和取消。

