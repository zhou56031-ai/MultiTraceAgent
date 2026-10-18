"""只报告文件/行号/风险类型，不打印密钥。默认检查可发布文件，--staged检查暂存区。"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRET_PATTERNS = [
    ("疑似模型API凭据", re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9._-]{20,}")),
    ("疑似Tavily凭据", re.compile(r"\btvly-[A-Za-z0-9_-]{20,}")),
    ("疑似RAGFlow凭据", re.compile(r"\bragflow-[A-Za-z0-9_-]{20,}")),
    ("疑似GitHub凭据", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})")),
    ("私钥", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
]
FORBIDDEN_PARTS = {".venv", "__pycache__", "node_modules", "data", "updated", "output"}


def git(*arguments: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *arguments])


def local_secrets() -> list[str]:
    """只在内存比较本地已知凭据，不把凭据输出或保存到报告。"""
    values = []
    for name in (".env", ".mysql-root.env"):
        path = ROOT / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator and not key.lstrip().startswith("#") and re.search(r"KEY|PASSWORD|TOKEN|SECRET", key.upper()):
                secret = value.strip().strip("\"'")
                if len(secret) >= 8:
                    values.append(secret)
    return values


def inspect(path: str, data: bytes, secrets: list[str]) -> list[str]:
    issues = []
    parts = Path(path).parts
    filename = Path(path).name
    if any(part in FORBIDDEN_PARTS for part in parts) or (
        filename != ".env.example" and (filename == ".env" or filename.startswith(".env.") or filename == ".mysql-root.env")
    ) or filename.endswith((".pem", ".key", ".db", ".db-wal", ".db-shm", ".sqlite", ".sqlite3", ".log")):
        issues.append(f"{path}：本地配置/运行数据不应发布")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return issues
    for number, line in enumerate(text.splitlines(), 1):
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                issues.append(f"{path}:{number}：{label}")
        if any(secret in line for secret in secrets):
            issues.append(f"{path}:{number}：包含本机已知凭据")
    return issues


def main():
    if "--self-test" in sys.argv:
        assert inspect(".env", b"test", [])
        assert inspect("data/tasks.db", b"test", [])
        assert inspect("README.md", ("sk-" + "X" * 32).encode(), [])
        assert inspect("agent/config.py", b"known-secret-value", ["known-secret-value"])
        assert not inspect(".env.example", b"OPENAI_API_KEY=replace_with_your_key", [])
        print("发布检查器自测通过：配置/运行数据拒绝、凭据模式与已知值检测、模板允许")
        return
    staged = "--staged" in sys.argv
    if staged:
        paths = git("diff", "--cached", "--name-only", "--diff-filter=ACM", "-z").decode().split("\0")
    else:
        paths = git("ls-files", "--cached", "--others", "--exclude-standard", "-z").decode().split("\0")
    paths = sorted(set(filter(None, paths)))
    if not paths:
        print("暂无暂存文件；先暂存待提交的文件，再执行 --staged" if staged else "未找到可发布文件")
        raise SystemExit(1)
    secrets = local_secrets()
    issues = []
    for path in paths:
        source = ROOT / path
        if staged:
            data = git("show", ":" + path)
        elif source.is_symlink():
            issues.append(f"{path}：符号链接需人工确认目标")
            continue
        elif source.is_file():
            data = source.read_bytes()
        else:
            continue
        issues.extend(inspect(path, data, secrets))
    for issue in issues:
        print(issue)
    if issues:
        raise SystemExit(f"未通过：{len(issues)} 项需处理；未输出凭据内容")
    print(f"通过：检查 {len(paths)} 个{'暂存' if staged else '可发布'}文件，未发现规则匹配或本机已知凭据。仍需人工审查图片与差异；这不是完整历史扫描。")


if __name__ == "__main__":
    main()
