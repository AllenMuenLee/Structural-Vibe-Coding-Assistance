import html
import re

from PyQt6.QtCore import QThread
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QLabel

from app.components.code_editor.ai_chat_worker import AIChatWorker


class ChatbotWidget(QWidget):
    """Chatbot sidebar widget with AI integration."""

    def __init__(self, project_root, flowchart_data, parent=None):
        super().__init__(parent)
        self.project_root = project_root
        self.flowchart_data = flowchart_data
        self.conversation_history = []
        self.current_worker = None
        self.worker_thread = None

        self.setObjectName("ChatbotWidget")
        from PyQt6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        header = QHBoxLayout()
        title = QLabel("AI Assistant")
        title.setObjectName("ChatTitle")
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        self.chat_history = QTextEdit()
        self.chat_history.setObjectName("ChatHistory")
        self.chat_history.setReadOnly(True)
        layout.addWidget(self.chat_history)

        self.mode = "general"
        self.mode_menu = QWidget()
        self.mode_menu.setObjectName("ModeMenu")
        mode_menu_layout = QHBoxLayout(self.mode_menu)
        mode_menu_layout.setContentsMargins(0, 0, 0, 0)
        mode_menu_layout.setSpacing(6)

        self.mode_debug_btn = QPushButton("Debug")
        self.mode_debug_btn.setObjectName("ModeButton")
        self.mode_debug_btn.clicked.connect(lambda: self.set_mode("debug"))
        mode_menu_layout.addWidget(self.mode_debug_btn)

        self.mode_flow_btn = QPushButton("Flowchart")
        self.mode_flow_btn.setObjectName("ModeButton")
        self.mode_flow_btn.clicked.connect(lambda: self.set_mode("flowchart"))
        mode_menu_layout.addWidget(self.mode_flow_btn)

        self.mode_general_btn = QPushButton("General")
        self.mode_general_btn.setObjectName("ModeButton")
        self.mode_general_btn.clicked.connect(lambda: self.set_mode("general"))
        mode_menu_layout.addWidget(self.mode_general_btn)

        self.mode_menu.setVisible(False)
        layout.addWidget(self.mode_menu)

        input_layout = QHBoxLayout()

        self.plus_btn = QPushButton("+")
        self.plus_btn.setObjectName("ChatPlusButton")
        self.plus_btn.setToolTip("Choose mode")
        self.plus_btn.clicked.connect(self._toggle_mode_menu)
        input_layout.addWidget(self.plus_btn)

        self.input_field = QTextEdit()
        self.input_field.setObjectName("ChatInput")
        self.input_field.setMaximumHeight(70)
        self.input_field.setPlaceholderText("Ask about your code...")
        input_layout.addWidget(self.input_field)

        self.send_btn = QPushButton("Send")
        self.send_btn.setObjectName("ChatSendButton")
        self.send_btn.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_btn)

        layout.addLayout(input_layout)

        self.mode_tag = QLabel("Selected: General")
        self.mode_tag.setObjectName("ModeTag")
        layout.addWidget(self.mode_tag)

        self._welcome_shown = False
        self.destroyed.connect(lambda _=None: self._stop_worker())

    def showEvent(self, event):
        """Show welcome message when chat is first opened."""
        super().showEvent(event)
        if not self._welcome_shown:
            self._welcome_shown = True
            self._append_ai(
                "Hello! I'm your AI coding assistant. I can help you with:\n"
                "- Understanding your code structure\n"
                "- Debugging issues\n"
                "- Updating flowcharts\n"
                "- Suggesting improvements\n"
                "- Answering questions about your project\n\n"
                "How can I help you today?"
            )

    def closeEvent(self, event):
        """Clean up threads when widget is closed."""
        self._stop_worker()
        super().closeEvent(event)

    def _stop_worker(self):
        if self.current_worker:
            self.current_worker.request_stop()
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait(1500)  # Wait up to 1.5 seconds
            if self.worker_thread.isRunning():
                self.worker_thread.terminate()
                self.worker_thread.wait(1000)
        self.current_worker = None
        self.worker_thread = None

    def send_message(self):
        message = self.input_field.toPlainText().strip()
        if not message or self.current_worker:
            return

        self._append_user(message)
        self.input_field.clear()
        self.send_btn.setEnabled(False)

        self._append_ai("_Thinking..._")

        self.current_worker = AIChatWorker(
            self.project_root,
            self.flowchart_data,
            message,
            self.conversation_history,
            self.mode,
        )
        self.worker_thread = QThread(self)
        self.current_worker.moveToThread(self.worker_thread)

        worker = self.current_worker
        thread = self.worker_thread

        def on_finished(response):
            cursor = self.chat_history.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            cursor.select(cursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.deletePreviousChar()

            self._append_ai(response)

            self.conversation_history.append({"role": "user", "content": message})
            self.conversation_history.append({"role": "assistant", "content": response})

            self.send_btn.setEnabled(True)
            self.current_worker = None
            self.worker_thread = None

        worker.finished.connect(on_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.started.connect(worker.run)
        thread.start()

    def _append_user(self, message: str) -> None:
        formatted = self._format_message(message)
        self.chat_history.append(
            f"<b>You</b><br>{formatted}<br>"
        )

    def _append_ai(self, message: str) -> None:
        formatted = self._format_message(message)
        self.chat_history.append(
            f"<b>AI</b><br>{formatted}<br>"
        )

    def _format_message(self, text: str) -> str:
        parts = []
        last = 0
        for match in re.finditer(r"```([a-zA-Z0-9_+-]*)\n(.*?)```", text, re.S):
            parts.append(self._format_plain(text[last:match.start()]))
            code = html.escape(match.group(2).rstrip("\n"))
            parts.append(f"<pre><code>{code}</code></pre>")
            last = match.end()
        parts.append(self._format_plain(text[last:]))
        return "".join(parts)

    def _format_plain(self, text: str) -> str:
        if not text:
            return ""
        lines = text.splitlines()
        out = []
        in_ul = False
        in_ol = False

        def close_lists():
            nonlocal in_ul, in_ol
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if in_ol:
                out.append("</ol>")
                in_ol = False

        for line in lines:
            if not line.strip():
                close_lists()
                out.append("<br>")
                continue

            if line.startswith("### "):
                close_lists()
                out.append(
                    "<div style='font-weight:600;margin:6px 0 2px 0;'>"
                    f"{self._format_inline(line[4:])}</div>"
                )
                continue
            if line.startswith("## "):
                close_lists()
                out.append(
                    "<div style='font-weight:600;margin:8px 0 2px 0;'>"
                    f"{self._format_inline(line[3:])}</div>"
                )
                continue
            if line.startswith("# "):
                close_lists()
                out.append(
                    "<div style='font-weight:700;margin:10px 0 4px 0;'>"
                    f"{self._format_inline(line[2:])}</div>"
                )
                continue

            if re.match(r"\d+\.\s+", line):
                if not in_ol:
                    close_lists()
                    out.append("<ol style='margin:6px 0 6px 18px;'>")
                    in_ol = True
                item = re.sub(r"^\d+\.\s+", "", line)
                out.append(f"<li>{self._format_inline(item)}</li>")
                continue

            if line.lstrip().startswith(("- ", "* ")):
                if not in_ul:
                    close_lists()
                    out.append("<ul style='margin:6px 0 6px 18px;'>")
                    in_ul = True
                item = line.lstrip()[2:]
                out.append(f"<li>{self._format_inline(item)}</li>")
                continue

            close_lists()
            out.append(f"{self._format_inline(line)}<br>")

        close_lists()
        return "".join(out)

    def _format_inline(self, text: str) -> str:
        escaped = html.escape(text)
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
        escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
        escaped = re.sub(r"_([^_]+)_", r"<i>\1</i>", escaped)
        return escaped

    def _toggle_mode_menu(self):
        self.mode_menu.setVisible(not self.mode_menu.isVisible())

    def set_mode(self, mode: str):
        if not mode:
            return
        self.mode = mode
        label = {
            "debug": "Debug",
            "flowchart": "Flowchart",
            "general": "General",
        }.get(mode, mode.title())
        self.mode_tag.setText(f"Selected: {label}")
        self.mode_menu.setVisible(False)

    def set_input_text(self, text: str):
        self.input_field.setPlainText(text)
        self.input_field.setFocus()