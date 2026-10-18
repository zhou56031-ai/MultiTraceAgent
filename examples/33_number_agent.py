"""直接验证正式数字工具及子助手配置，不调用模型。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.subagents.number_agent import number_agent
from tools.number_tools import sum_numbers


def main() -> None:
    cases = (
        ("10,20,30", "数量=3；合计=60；平均值=20"),
        (" -10, 0, 10 ", "数量=3；合计=0；平均值=0"),
        ("5", "数量=1；合计=5；平均值=5"),
        ("1,2", "数量=2；合计=3；平均值=1.5"),
        (",".join(["1"] * 20), "数量=20；合计=20；平均值=1"),
        ("10,abc,30", "错误：每一项都必须是整数"),
        ("1.5,2", "错误：每一项都必须是整数"),
        ("", "错误：请提供 1 到 20 个用英文逗号分隔的整数"),
        ("10,", "错误：请提供 1 到 20 个用英文逗号分隔的整数"),
        (",".join(["1"] * 21), "错误：请提供 1 到 20 个用英文逗号分隔的整数"),
        ("1" + "0" * 400, "错误：整数过大，无法计算平均值，请缩小数值"),
    )
    for numbers, expected in cases:
        actual = sum_numbers.invoke({"numbers": numbers})
        assert actual == expected, (numbers, actual)

    assert number_agent["name"] == "数字统计助手"
    assert sum_numbers in number_agent["tools"]
    print(f"数字工具的 {len(cases)} 组输入与子助手配置通过")


if __name__ == "__main__":
    main()
