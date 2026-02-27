import os
from typing import Optional


def run_command(command: str, cwd: Optional[str] = None, timeout: Optional[int] = None) -> int:
    """
    Run a command in a terminal and block until it completes.
    """
    print(command)
    if not command or not isinstance(command, str):
        raise ValueError("command must be a non-empty string")
    if timeout is not None:
        raise ValueError("timeout is not supported without subprocess")

    prev_cwd = None
    if cwd:
        target_cwd = os.path.abspath(cwd)
        if not os.path.isdir(target_cwd):
            raise FileNotFoundError(f"cwd does not exist: {target_cwd}")
        prev_cwd = os.getcwd()
        os.chdir(target_cwd)
    try:
        return os.system(command)
    finally:
        if prev_cwd is not None:
            os.chdir(prev_cwd)
