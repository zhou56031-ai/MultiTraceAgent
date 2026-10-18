from langchain_core.tools import tool

from api.monitor import monitor


@tool
def sum_numbers(numbers: str) -> str:
    """统计用英文逗号分隔的整数，返回数量、合计和平均值。"""
    monitor.report_tool("sum_numbers", {"item_count_hint": numbers.count(",") + 1})
    try:
        parts = [part.strip() for part in numbers.split(",")]
        if not 1 <= len(parts) <= 20 or any(not part for part in parts):
            return "错误：请提供 1 到 20 个用英文逗号分隔的整数"
        values = [int(part) for part in parts]
    except ValueError:
        return "错误：每一项都必须是整数"

    total = sum(values)
    try:
        average = total / len(values)
    except OverflowError:
        return "错误：整数过大，无法计算平均值，请缩小数值"
    return f"数量={len(values)}；合计={total}；平均值={average:g}"
