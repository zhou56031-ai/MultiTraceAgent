from pathlib import Path

import yaml


def load_yaml(file_path: Path) -> dict:
    with file_path.open("r", encoding="utf-8") as stream: #-r代表读取文件，encoding="utf-8"指定文件编码为UTF-8
        data = yaml.safe_load(stream)

    if not isinstance(data, dict):
        raise ValueError("提示词文件的顶层必须是键值表")

    return data


project_root = Path(__file__).resolve().parent.parent
yaml_file_path = project_root / "prompt" / "prompts.yml"

prompt_yaml_content = load_yaml(yaml_file_path)
main_agent_content = prompt_yaml_content["main_agent"]
sub_agents_content = prompt_yaml_content["sub_agents"]