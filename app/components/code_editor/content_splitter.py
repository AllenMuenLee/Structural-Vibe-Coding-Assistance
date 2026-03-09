from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSplitter

from app.components.code_editor.file_panel import build_file_panel
from app.components.code_editor.editor_panel import build_editor_panel


def build_content_splitter(*, on_file_clicked, on_save, on_add_file, on_delete_file):
    content_splitter = QSplitter(Qt.Orientation.Horizontal)

    file_panel, file_tree, file_model, add_btn, delete_btn = build_file_panel(
        on_file_clicked, on_add_file, on_delete_file
    )
    editor_panel, code_editor, current_file_label = build_editor_panel(on_save)

    content_splitter.addWidget(file_panel)
    content_splitter.addWidget(editor_panel)

    content_splitter.setStretchFactor(0, 1)  # File browser
    content_splitter.setStretchFactor(1, 4)  # Editor (bigger)

    return content_splitter, file_tree, file_model, code_editor, current_file_label, add_btn, delete_btn
