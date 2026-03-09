import os
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QMessageBox,
)

import src.utils.FileMng as FileMng


class DashboardWidget(QWidget):
    def __init__(self, on_new_project=None, on_open_project=None):
        super().__init__()
        self.setObjectName("DashboardPage")
        self._on_new_project = on_new_project
        self._on_open_project = on_open_project

        style_path = Path(__file__).resolve().parent.parent / "style" / "dashboard.qss"
        if style_path.exists():
            self.setStyleSheet(style_path.read_text(encoding="utf-8"))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QVBoxLayout()
        title = QLabel("Dashboard")
        title.setObjectName("DashboardTitle")
        subtitle = QLabel("Select a project to continue or create a new one.")
        subtitle.setObjectName("DashboardSubtitle")
        header.addWidget(title)
        header.addWidget(subtitle)
        layout.addLayout(header)

        self.project_list = QListWidget()
        self.project_list.setObjectName("ProjectList")
        self.project_list.itemDoubleClicked.connect(self._open_selected_project)
        layout.addWidget(self.project_list, stretch=1)

        actions = QHBoxLayout()
        actions.addStretch()

        open_btn = QPushButton("Open Project")
        open_btn.setObjectName("DashboardButton")
        open_btn.clicked.connect(self._open_selected_project)
        actions.addWidget(open_btn)

        delete_btn = QPushButton("Delete Project")
        delete_btn.setObjectName("DashboardButton")
        delete_btn.clicked.connect(self._delete_selected_project)
        actions.addWidget(delete_btn)

        new_btn = QPushButton("New Project")
        new_btn.setObjectName("DashboardPrimary")
        new_btn.clicked.connect(self._create_new_project)
        actions.addWidget(new_btn)

        layout.addLayout(actions)

        self.refresh_projects()

    def refresh_projects(self):
        self.project_list.clear()
        projects = FileMng.load_projects()
        for project in projects:
            project_root = project.get("project_root", "")
            name = os.path.basename(project_root) if project_root else project.get("id", "Unknown")
            item_text = f"{name}  —  {project_root}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, project)
            self.project_list.addItem(item)

    def _open_selected_project(self):
        item = self.project_list.currentItem()
        if not item:
            QMessageBox.information(self, "Select Project", "Please select a project.")
            return
        project = item.data(Qt.ItemDataRole.UserRole) or {}
        project_id = project.get("id")
        if not project_id:
            QMessageBox.warning(self, "Error", "Invalid project entry.")
            return
        if self._on_open_project:
            self._on_open_project(project_id)

    def _create_new_project(self):
        if self._on_new_project:
            self._on_new_project()

    def _delete_selected_project(self):
        item = self.project_list.currentItem()
        if not item:
            QMessageBox.information(self, "Select Project", "Please select a project.")
            return
        project = item.data(Qt.ItemDataRole.UserRole) or {}
        project_id = project.get("id")
        if not project_id:
            QMessageBox.warning(self, "Error", "Invalid project entry.")
            return
        confirm = QMessageBox.question(
            self,
            "Delete Project",
            "Delete this project from the list? This will not delete files on disk.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        if FileMng.delete_project(project_id):
            self.refresh_projects()
        else:
            QMessageBox.warning(self, "Error", "Failed to delete project.")
