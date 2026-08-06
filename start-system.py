"""Launch the full local platform without manually entering terminal commands."""

from __future__ import annotations

import subprocess
import sys
import webbrowser
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
START_SCRIPT = PROJECT_ROOT / "scripts" / "start-platform-dev.ps1"
FRONTEND_DEPENDENCIES = PROJECT_ROOT / "frontend" / "node_modules"
BACKEND_MODULES = ("uvicorn", "pydantic_settings", "pika")
FRONTEND_URL = "http://127.0.0.1:5173"


def find_backend_python() -> Path:
    """Match the PowerShell launcher preference for project virtual environments."""
    for relative_path in ("venv/Scripts/python.exe", ".venv/Scripts/python.exe"):
        candidate = PROJECT_ROOT / relative_path
        if candidate.is_file():
            return candidate
    return Path(sys.executable)


def has_backend_dependencies(python_path: Path) -> bool:
    """Avoid installing packages on every launch when the runtime is already ready."""
    command = [str(python_path), "-c", f"import {', '.join(BACKEND_MODULES)}"]
    return subprocess.run(command, check=False, capture_output=True).returncode == 0


def build_start_command() -> list[str]:
    """Build the existing supported platform-start command with only necessary setup flags."""
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(START_SCRIPT),
    ]
    if not has_backend_dependencies(find_backend_python()):
        command.append("-InstallBackendDeps")
    if not FRONTEND_DEPENDENCIES.is_dir():
        command.append("-InstallFrontendDeps")
    return command


def main() -> int:
    """Start backend and frontend, then open the browser only after readiness checks pass."""
    if not START_SCRIPT.is_file():
        print(f"启动脚本不存在：{START_SCRIPT}")
        return 1

    print("正在启动量智硫光，请稍候……")
    result = subprocess.run(build_start_command(), cwd=PROJECT_ROOT, check=False)
    if result.returncode != 0:
        print("\n系统启动失败。请查看 .dev-logs 目录中的日志。")
        return result.returncode

    webbrowser.open(FRONTEND_URL)
    print(f"\n系统已启动，正在打开：{FRONTEND_URL}")
    return 0


if __name__ == "__main__":
    exit_code = main()
    if exit_code != 0:
        input("按 Enter 键关闭此窗口……")
    raise SystemExit(exit_code)
