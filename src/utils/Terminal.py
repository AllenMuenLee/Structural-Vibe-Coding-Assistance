import subprocess
import threading
from typing import Callable, Optional


def run_command(command: str, cwd: Optional[str] = None, timeout: Optional[int] = None) -> str:
    """
    Run a command in a terminal and block until it completes, returning output.
    """
    if not command or not isinstance(command, str):
        raise ValueError("command must be a non-empty string")
    completed = subprocess.run(
        command,
        shell=True,
        cwd=cwd,
        timeout=timeout,
        capture_output=True,
        text=True,
    )
    return (completed.stdout or "") + (completed.stderr or "")


LONG_RUNNING_PREFIXES = (
    "python",
    "python3",
    "node",
    "npm",
    "flask",
    "django",
    "uvicorn",
)


def is_long_running_command(command: str) -> bool:
    if not command or not isinstance(command, str):
        return False
    return any(command.startswith(prefix) for prefix in LONG_RUNNING_PREFIXES)


def run_command_async(
    command: str,
    *,
    cwd: Optional[str] = None,
    timeout: Optional[int] = None,
    on_output_line: Optional[Callable[[str], None]] = None,
    on_no_output: Optional[Callable[[], None]] = None,
    on_complete: Optional[Callable[[], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> threading.Thread:
    def _runner():
        try:
            output = run_command(command, cwd=cwd, timeout=timeout)
            if output:
                if on_output_line:
                    for line in output.splitlines():
                        on_output_line(line)
            else:
                if on_no_output:
                    on_no_output()
            if on_complete:
                on_complete()
        except Exception as exc:
            if on_error:
                on_error(exc)

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    return thread


def open_system_terminal(project_root: str, command: Optional[str] = None) -> None:
    """Open the system terminal in the project directory."""
    import platform

    system = platform.system()

    try:
        if system == "Darwin":  # macOS
            script = f'cd "{project_root}"'
            if command:
                script += f" && {command}"
            subprocess.Popen(
                ["osascript", "-e", f'tell application "Terminal" to do script "{script}"']
            )
        elif system == "Windows":
            subprocess.Popen(["cmd", "/K", f'cd /d "{project_root}"'])
        else:  # Linux
            terminals = ["gnome-terminal", "konsole", "xterm"]
            for term in terminals:
                try:
                    subprocess.Popen([term, "--working-directory", project_root])
                    break
                except Exception:
                    continue
    except Exception as exc:
        print(f"Failed to open terminal: {exc}")
