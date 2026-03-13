import os
import shutil
from PyQt6.QtCore import QDir, Qt
from PyQt6.QtGui import QFileSystemModel
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QInputDialog,
    QMessageBox,
    QTreeView,
    QAbstractItemView,
    QMenu,
)

import src.utils.FileMng as FileMng


def build_file_panel(on_file_clicked):
    file_panel = QWidget()
    file_panel.setObjectName("FilePanel")
    file_layout = QVBoxLayout(file_panel)
    file_layout.setContentsMargins(10, 10, 10, 0)  # No bottom margin

    file_label = QLabel("Files")
    file_label.setObjectName("SectionLabel")
    file_layout.addWidget(file_label)

    file_tree = QTreeView()
    file_tree.setObjectName("FileTree")
    file_tree.setHeaderHidden(True)
    file_tree.setUniformRowHeights(True)
    file_tree.setEditTriggers(QAbstractItemView.EditTrigger.EditKeyPressed)
    file_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    model = QFileSystemModel()
    model.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot)
    file_tree.setModel(model)
    file_tree.setColumnHidden(1, True)
    file_tree.setColumnHidden(2, True)
    file_tree.setColumnHidden(3, True)

    file_tree.clicked.connect(
        lambda index: _handle_tree_click(file_tree, model, on_file_clicked, index)
    )
    file_tree.customContextMenuRequested.connect(
        lambda pos: _show_file_context_menu(file_tree, model, pos)
    )
    file_layout.addWidget(file_tree)

    file_panel.setMinimumWidth(180)
    file_panel.setMaximumWidth(220)

    return file_panel, file_tree, model


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


def _show_file_context_menu(file_tree, model, pos):
    project_root = file_tree.property("project_root") or ""
    if not project_root:
        return

    index = file_tree.indexAt(pos)
    if not index.isValid():
        index = model.index(project_root)
    if not index.isValid():
        return

    target_path = model.filePath(index)
    target_abs = os.path.abspath(target_path)
    project_root_abs = os.path.abspath(project_root)

    menu = QMenu(file_tree)
    new_file_action = menu.addAction("New File")
    new_folder_action = menu.addAction("New Folder")
    rename_action = menu.addAction("Rename")
    delete_action = menu.addAction("Delete")

    is_root = target_abs == project_root_abs
    if is_root:
        rename_action.setEnabled(False)
        delete_action.setEnabled(False)

    action = menu.exec(file_tree.viewport().mapToGlobal(pos))
    if not action:
        return

    base_dir = target_path if model.isDir(index) else os.path.dirname(target_path)
    rel_base_dir = os.path.relpath(base_dir, project_root_abs)
    if rel_base_dir == ".":
        rel_base_dir = ""

    if action == new_file_action:
        _create_new_file(file_tree, project_root_abs, rel_base_dir)
        _refresh_model(model, project_root_abs)
        return

    if action == new_folder_action:
        _create_new_folder(file_tree, project_root_abs, rel_base_dir)
        _refresh_model(model, project_root_abs)
        return

    if action == rename_action:
        file_tree.edit(index)
        return

    if action == delete_action:
        _delete_path(file_tree, model, project_root_abs, index)
        _refresh_model(model, project_root_abs)


def _create_new_file(parent, project_root, rel_base_dir):
    filename, ok = QInputDialog.getText(
        parent,
        "New File",
        "Enter file name or path:",
    )
    if not ok or not filename:
        return

    rel_path = filename.strip()
    if rel_base_dir:
        rel_path = os.path.join(rel_base_dir, rel_path)

    ok, message, _ = FileMng.add_file_to_project(project_root, rel_path)
    if not ok and message and message != "Cancelled.":
        QMessageBox.warning(parent, "Error", message)


def _create_new_folder(parent, project_root, rel_base_dir):
    folder_name, ok = QInputDialog.getText(
        parent,
        "New Folder",
        "Enter folder name or path:",
    )
    if not ok or not folder_name:
        return

    rel_path = folder_name.strip()
    if rel_base_dir:
        rel_path = os.path.join(rel_base_dir, rel_path)

    project_root_abs = os.path.abspath(project_root)
    folder_path = os.path.abspath(os.path.join(project_root_abs, rel_path))
    if not folder_path.startswith(project_root_abs):
        QMessageBox.warning(parent, "Error", "Invalid folder path.")
        return
    if os.path.exists(folder_path):
        QMessageBox.warning(parent, "Error", "Folder already exists.")
        return

    try:
        os.makedirs(folder_path, exist_ok=False)
    except Exception as exc:
        QMessageBox.warning(parent, "Error", f"Failed to create folder: {exc}")


def _delete_path(parent, model, project_root, index):
    if not index.isValid():
        return

    target_path = model.filePath(index)
    target_abs = os.path.abspath(target_path)
    project_root_abs = os.path.abspath(project_root)

    if not target_abs.startswith(project_root_abs):
        QMessageBox.warning(parent, "Error", "Invalid path.")
        return

    rel_path = os.path.relpath(target_abs, project_root_abs)
    if model.isDir(index):
        confirm = QMessageBox.question(
            parent,
            "Delete Folder",
            f"Delete '{rel_path}' and all contents?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            shutil.rmtree(target_abs)
        except Exception as exc:
            QMessageBox.warning(parent, "Error", f"Failed to delete folder: {exc}")
        return

    confirm = QMessageBox.question(
        parent,
        "Delete File",
        f"Delete '{rel_path}' from disk?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    if confirm != QMessageBox.StandardButton.Yes:
        return

    ok, message = FileMng.delete_file_from_project(project_root_abs, rel_path)
    if not ok and message:
        QMessageBox.warning(parent, "Error", message)


def _refresh_model(model, project_root):
    try:
        model.refresh(model.index(project_root))
    except Exception:
        pass
