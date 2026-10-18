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
