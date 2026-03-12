import os
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QMessageBox,
    QFileDialog,
    QApplication,
)

import src.utils.FileMng as FileMng
from src.core.AstFlowchartGen import AstFlowchartGenerator
from src.core.Flowchart import Flowchart
from src.utils.CacheMng import save_current_project_id
from app.pages.loadingScreen import LoadingScreen


class ProjectImportWorker(QThread):
    finished = pyqtSignal(bool, str, str)  # success, message, flowchart_id
    progress = pyqtSignal(str)

    def __init__(self, project_root):
        super().__init__()
        self.project_root = project_root

    def run(self):
        def is_connection_error(exc: Exception) -> bool:
            msg = str(exc).lower()
            return (
                "apiconnectionerror" in msg
                or "connection error" in msg
                or "decodingerror" in msg
                or "decompressobj" in msg
            )

        try:
            max_retries = 3
            for attempt in range(1, max_retries + 1):
                try:
                    generator = AstFlowchartGenerator(self.project_root)
                    flowchart_data = generator.generate_all()
                    break
                except Exception as exc:
                    if not is_connection_error(exc) or attempt >= max_retries:
                        raise
                    self.progress.emit(
                        f"Connection issue. Retrying in 3 seconds... ({attempt}/{max_retries})"
                    )
                    import time
                    time.sleep(3)

            if not flowchart_data:
                self.finished.emit(False, "Failed to generate flowchart.", "")
                return

            framework = flowchart_data.get("framework", "")
            flowchart = Flowchart(
                name=os.path.basename(self.project_root),
                framework=framework,
                project_root=self.project_root,
            )
            flowchart.create_from_ai_response(flowchart_data)
            flowchart_dict = flowchart.flowchart_to_dictionary()
            flowchart_id = flowchart.flowchart_id

            flowchart.save_to_file(flowchart_id, flowchart_dict)
            FileMng.save_project(flowchart_id, self.project_root)
            save_current_project_id(flowchart_id)
            self.finished.emit(True, "", flowchart_id)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            self.finished.emit(False, f"Failed to import project: {exc}", "")


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

        import_btn = QPushButton("Import Project")
        import_btn.setObjectName("DashboardButton")
        import_btn.clicked.connect(self._import_project)
        actions.addWidget(import_btn)

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

    def _import_project(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Project Folder")
        if not folder:
            return

        project_root = os.path.abspath(folder)
        existing = FileMng.load_projects()
        for project in existing:
            if os.path.abspath(project.get("project_root", "")) == project_root:
                QMessageBox.information(
                    self,
                    "Already Added",
                    "This project is already in your list.",
                )
                return

        loading = LoadingScreen(self, message="Importing project. Please wait...")
        loading.show()
        QApplication.processEvents()
        self.repaint()

        worker = ProjectImportWorker(project_root)
        worker.progress.connect(lambda msg: loading.set_message(msg))

        def on_finished(success, message, flowchart_id):
            loading.close()
            if not success:
                QMessageBox.warning(self, "Error", message or "Failed to import project.")
                return
            self.refresh_projects()
            if self._on_open_project:
                self._on_open_project(flowchart_id)

        worker.finished.connect(on_finished)
        worker.start()
        self._import_worker = worker
