from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QLineEdit,
    QPushButton,
)


def detect_terminal_error(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    keywords = [
        "traceback",
        "exception",
        "error",
        "fatal",
        "segmentation fault",
        "panic",
        "stack trace",
        "unhandled",
        "syntaxerror",
        "typeerror",
        "referenceerror",
        "nameerror",
        "indexerror",
        "keyerror",
        "attributeerror",
        "module not found",
        "cannot find module",
        "enoent",
        "epipe",
        "npm err!",
        "build failed",
        "compilation failed",
        "linker error",
        "undefined reference",
    ]
    return any(k in lowered for k in keywords)


def set_debug_visible(debug_btn: QPushButton, show: bool) -> None:
    if not debug_btn:
        return
    debug_btn.setVisible(bool(show))


def build_terminal_panel(*, on_clear=None, on_run_command=None, on_stop=None, on_debug=None):
    terminal_container = QWidget()
    terminal_container.setObjectName("TerminalContainer")
    terminal_layout = QVBoxLayout(terminal_container)
    terminal_layout.setContentsMargins(10, 8, 10, 8)
    terminal_layout.setSpacing(5)

    terminal_header = QHBoxLayout()

    terminal_label = QLabel("Terminal")
    terminal_label.setObjectName("TerminalLabel")
    terminal_header.addWidget(terminal_label)

    terminal_header.addStretch()

    debug_btn = QPushButton("Debug")
    debug_btn.setObjectName("TerminalDebugButton")
    debug_btn.setToolTip("Send terminal errors to debugger")
    if on_debug:
        debug_btn.clicked.connect(on_debug)
    debug_btn.hide()
    terminal_header.addWidget(debug_btn)

    clear_terminal_btn = QPushButton("Clear")
    clear_terminal_btn.setObjectName("TerminalClearButton")
    clear_terminal_btn.setToolTip("Clear terminal")
    terminal_header.addWidget(clear_terminal_btn)

    terminal_layout.addLayout(terminal_header)

    terminal = QTextEdit()
    terminal.setObjectName("Terminal")
    terminal.setReadOnly(True)
    terminal.setMaximumHeight(120)
    terminal_layout.addWidget(terminal)

    if on_clear:
        clear_terminal_btn.clicked.connect(on_clear)
    else:
        clear_terminal_btn.clicked.connect(terminal.clear)

    terminal_input_layout = QHBoxLayout()

    terminal_prompt = QLabel(">")
    terminal_prompt.setObjectName("TerminalPrompt")
    terminal_input_layout.addWidget(terminal_prompt)

    terminal_input = QLineEdit()
    terminal_input.setObjectName("TerminalInput")
    terminal_input.setPlaceholderText("Type command and press Enter...")
    terminal_input_layout.addWidget(terminal_input)

    run_command_btn = QPushButton("Run")
    run_command_btn.setObjectName("TerminalRunButton")
    run_command_btn.setToolTip("Run command")
    if on_run_command:
        run_command_btn.clicked.connect(on_run_command)
    terminal_input_layout.addWidget(run_command_btn)

    stop_process_btn = QPushButton("Stop")
    stop_process_btn.setObjectName("TerminalStopButton")
    stop_process_btn.setToolTip("Stop")
    if on_stop:
        stop_process_btn.clicked.connect(on_stop)
    stop_process_btn.hide()
    terminal_input_layout.addWidget(stop_process_btn)

    terminal_layout.addLayout(terminal_input_layout)

    return (
        terminal_container,
        terminal,
        terminal_input,
        run_command_btn,
        stop_process_btn,
        clear_terminal_btn,
        debug_btn,
    )
