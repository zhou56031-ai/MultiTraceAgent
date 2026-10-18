import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
python_path = sys.executable
python_version = sys.version.split()[0]
environment_path = Path(sys.prefix)
using_project_env = environment_path == project_root / ".venv"

print("项目目录：", project_root)
print("Python 程序：", python_path)
print("Python 版本：", python_version)
print("环境目录：", environment_path)
print("使用本项目环境：", using_project_env)
