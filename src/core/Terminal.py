import subprocess
from typing import Optional


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
