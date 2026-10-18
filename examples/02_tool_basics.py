from langchain_core.tools import tool


def calculate_total(price: float, quantity: int) -> float:
    return price * quantity


@tool
def calculate_total_tool(price: float, quantity: int) -> float:
    """根据单价和数量计算商品总价。"""
    return calculate_total(price, quantity)


inputs = {"price": 12.5, "quantity": 3}
plain_result = calculate_total(12.5, 3)
tool_result = calculate_total_tool.invoke(inputs)

print("普通函数：", plain_result)
print("工具类型：", type(calculate_total_tool).__name__)
print("工具名称：", calculate_total_tool.name)
print("工具说明：", calculate_total_tool.description)
print("工具参数：", calculate_total_tool.args)
print("工具调用：", tool_result)

assert plain_result == 37.5
assert tool_result == plain_result
assert set(calculate_total_tool.args) == {"price", "quantity"}
