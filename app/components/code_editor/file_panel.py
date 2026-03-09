import os
from PyQt6.QtCore import QDir
from PyQt6.QtGui import QFileSystemModel
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QInputDialog,
    QMessageBox,
    QTreeView,
)

import src.utils.FileMng as FileMng


def build_file_panel(on_file_clicked, on_add_file, on_delete_file):
    file_panel = QWidget()
    file_panel.setObjectName("FilePanel")
    file_layout = QVBoxLayout(file_panel)
    file_layout.setContentsMargins(10, 10, 10, 0)  # No bottom margin

    file_label = QLabel("Files")
    file_label.setObjectName("SectionLabel")
    file_layout.addWidget(file_label)

    actions_row = QHBoxLayout()
    actions_row.setSpacing(6)

    add_btn = QPushButton("Add")
    add_btn.setObjectName("FileActionButton")
    add_btn.setToolTip("Add file")
    add_btn.clicked.connect(on_add_file)

    delete_btn = QPushButton("Delete")
    delete_btn.setObjectName("FileActionButton")
    delete_btn.setToolTip("Delete file")
    delete_btn.clicked.connect(on_delete_file)
    delete_btn.setEnabled(False)

    actions_row.addWidget(add_btn)
    actions_row.addWidget(delete_btn)
    actions_row.addStretch()
    file_layout.addLayout(actions_row)

    file_tree = QTreeView()
    file_tree.setObjectName("FileTree")
    file_tree.setHeaderHidden(True)
    file_tree.setUniformRowHeights(True)

    model = QFileSystemModel()
    model.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot)
    file_tree.setModel(model)
    file_tree.setColumnHidden(1, True)
    file_tree.setColumnHidden(2, True)
    file_tree.setColumnHidden(3, True)

    file_tree.clicked.connect(
        lambda index: _handle_tree_click(file_tree, model, on_file_clicked, index)
    )
    file_layout.addWidget(file_tree)

    file_panel.setMinimumWidth(180)
    file_panel.setMaximumWidth(220)

    return file_panel, file_tree, model, add_btn, delete_btn


def set_project_root(file_tree, model, project_root):
    if not project_root:
        return
    model.setRootPath(project_root)
    file_tree.setRootIndex(model.index(project_root))
    file_tree.setProperty("project_root", project_root)
    file_tree.expandToDepth(1)


def _handle_tree_click(file_tree, model, on_file_clicked, index):
    if model.isDir(index):
        return
    project_root = file_tree.property("project_root") or ""
    file_path = model.filePath(index)
    if project_root:
        file_path = os.path.relpath(file_path, project_root)
    on_file_clicked(file_path)


def add_file(parent, project_root):
    if not project_root:
        QMessageBox.warning(parent, "Error", "Project root not found.")
        return False, "Project root not found.", None

    filename, ok = QInputDialog.getText(
        parent,
        "Add File",
        "Enter file path relative to project root:",
    )
    if not ok or not filename:
        return False, "Cancelled.", None

    filename = filename.strip()
    ok, message, _ = FileMng.add_file_to_project(project_root, filename)
    return ok, message, filename if ok else None


def delete_file(parent, project_root, file_tree, model):
    if not project_root:
        QMessageBox.warning(parent, "Error", "Project root not found.")
        return False, "Project root not found."
    if not file_tree or not model:
        QMessageBox.information(parent, "Select File", "Please select a file to delete.")
        return False, "No file selected."

    index = file_tree.currentIndex()
    if not index.isValid() or model.isDir(index):
        QMessageBox.information(parent, "Select File", "Please select a file to delete.")
        return False, "No file selected."

    filename = os.path.relpath(model.filePath(index), project_root)
    confirm = QMessageBox.question(
        parent,
        "Delete File",
        f"Delete '{filename}' from disk?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    if confirm != QMessageBox.StandardButton.Yes:
        return False, "Cancelled."

    ok, message = FileMng.delete_file_from_project(project_root, filename)
    return ok, message


def update_file_actions(delete_btn, model, index):
    if delete_btn:
        enabled = bool(index and index.isValid())
        if enabled and model and model.isDir(index):
            enabled = False
        delete_btn.setEnabled(enabled)
