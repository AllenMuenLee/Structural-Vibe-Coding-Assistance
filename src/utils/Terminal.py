import subprocess
import os
import platform
from typing import Callable, Optional

from PyQt6.QtCore import QProcess


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


def start_process(
    command: str,
    *,
    cwd: Optional[str] = None,
    parent=None,
    on_output: Optional[Callable[[str], None]] = None,
    on_finished: Optional[Callable[[int, QProcess.ExitStatus], None]] = None,
    on_error: Optional[Callable[[QProcess.ProcessError], None]] = None,
    env_extras: Optional[dict] = None,
) -> QProcess:
    if not command or not isinstance(command, str):
        raise ValueError("command must be a non-empty string")

    process = QProcess(parent)
    process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
    if cwd:
        process.setWorkingDirectory(cwd)

    # Apply environment extras (e.g. PYTHONUNBUFFERED)
    if env_extras:
        from PyQt6.QtCore import QProcessEnvironment
        env = QProcessEnvironment.systemEnvironment()
        for k, v in env_extras.items():
            env.insert(k, v)
        process.setProcessEnvironment(env)

    def _read():
        data = process.readAllStandardOutput()
        if data and on_output:
            on_output(bytes(data).decode(errors="replace"))

    def _finished(exit_code: int, exit_status: QProcess.ExitStatus):
        if on_finished:
            on_finished(exit_code, exit_status)

    def _error(err: QProcess.ProcessError):
        if on_error:
            on_error(err)

    process.readyReadStandardOutput.connect(_read)
    process.finished.connect(_finished)
    process.errorOccurred.connect(_error)

    if os.name == "nt":
        process.setProgram("cmd")
        process.setArguments(["/C", command])
    else:
        process.setProgram("/bin/sh")
        process.setArguments(["-lc", command])

    process.start()
    return process


def stop_process(process: Optional[QProcess]) -> None:
    if process and process.state() != QProcess.ProcessState.NotRunning:
        process.kill()


def open_system_terminal(project_root: str, command: Optional[str] = None) -> None:
    """Open the system terminal in the project directory."""
    system = platform.system()
    if system == "Windows":
        cmd = f'cd /d "{project_root}"'
        if command:
            cmd += f" && {command}"
        QProcess.startDetached("cmd", ["/K", cmd])
        return
    if system == "Darwin":
        script = f'cd "{project_root}"'
        if command:
            script += f" && {command}"
        subprocess.Popen(["osascript", "-e", f'tell application \"Terminal\" to do script \"{script}\"'])
        return
    terminals = ["gnome-terminal", "konsole", "xterm"]
    for term in terminals:
        args = ["--working-directory", project_root]
        if command:
            args += ["--", "bash", "-c", command]
        if QProcess.startDetached(term, args):
            break
