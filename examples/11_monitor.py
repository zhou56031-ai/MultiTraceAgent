import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.monitor import monitor, ToolMonitor

event = monitor.report_tool("演示工具", {"filename": "A.md"})
print("事件类型：", event["event"])
print("共享对象：", monitor is __import__("api.monitor", fromlist=["monitor"]).monitor)
print("另建对象：", monitor is ToolMonitor())