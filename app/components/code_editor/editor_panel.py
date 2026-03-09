from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit, QPushButton

from app.components.code_editor.python_highlighter import PythonHighlighter


def build_editor_panel(on_save):
    editor_panel = QWidget()
    editor_layout = QVBoxLayout(editor_panel)
    editor_layout.setContentsMargins(10, 10, 10, 0)  # No bottom margin

    current_file_label = QLabel("No file selected")
    current_file_label.setObjectName("CurrentFileLabel")
    editor_layout.addWidget(current_file_label)

    code_editor = QTextEdit()
    code_editor.setObjectName("CodeEditor")
    PythonHighlighter(code_editor.document())
    editor_layout.addWidget(code_editor)

    save_btn = QPushButton("Save")
    save_btn.setObjectName("SaveButton")
    save_btn.setToolTip("Save file")
    save_btn.clicked.connect(on_save)
    editor_layout.addWidget(save_btn)

    return editor_panel, code_editor, current_file_label
