import os
import time
from functools import partial
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
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
from src.utils.NetUtils import is_connection_error
from src.utils.CacheMng import save_current_project_id
from app.pages.loadingScreen import LoadingScreen


def _set_loading_message(loading: LoadingScreen, message: str) -> None:
    if loading:
        loading.set_message(message)


class ProjectImportWorker(QThread):
    finished = pyqtSignal(bool, str, str)  # success, message, flowchart_id
    progress = pyqtSignal(str)

    def __init__(self, project_root):
        super().__init__()
        self.project_root = project_root

    def run(self):
        try:
            max_retries = 3
            for attempt in range(1, max_retries + 1):
                try:
                    from src.core.AstFlowchartGen import AstFlowchartGenerator
                    generator = AstFlowchartGenerator(self.project_root)
                    flowchart_data = generator.generate_all()
                    break
                except Exception as exc:
                    if not is_connection_error(exc) or attempt >= max_retries:
                        raise
                    self.progress.emit(
                        f"Connection issue. Retrying in 3 seconds... ({attempt}/{max_retries})"
                    )
                    time.sleep(3)

            if not flowchart_data:
                self.finished.emit(False, "Failed to generate flowchart.", "")
                return

            from src.core.Flowchart import Flowchart
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
            message = f"Failed to import project: {exc}"
            msg_lower = str(exc).lower()
            if "api key" in msg_lower or "nova_api_key" in msg_lower or "openai client" in msg_lower:
                message = f"{message}\nHint: Add your API key in Settings."
            self.finished.emit(False, message, "")


class DashboardWidget(QWidget):
    def __init__(self, on_new_project=None, on_open_project=None, on_open_settings=None):
        super().__init__()
        self.setObjectName("DashboardPage")
        self._on_new_project = on_new_project
        self._on_open_project = on_open_project
        self._on_open_settings = on_open_settings

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

        settings_btn = QPushButton("Settings")
        settings_btn.setObjectName("DashboardButton")
        settings_btn.clicked.connect(self._open_settings)
        actions.addWidget(settings_btn)
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
        QTimer.singleShot(0, lambda: self._ensure_api_key(show_dialog=True))

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
        if not self._ensure_api_key(show_dialog=True):
            return
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
        if not self._ensure_api_key(show_dialog=True):
            return
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
        if not self._ensure_api_key(show_dialog=True):
            return
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
        self._import_loading = loading

        worker = ProjectImportWorker(project_root)
        worker.progress.connect(partial(_set_loading_message, loading))
        worker.finished.connect(self._handle_import_finished)
        worker.start()
        self._import_worker = worker

    def _handle_import_finished(self, success, message, flowchart_id):
        loading = getattr(self, "_import_loading", None)
        if loading:
            loading.close()
        if not success:
            QMessageBox.warning(self, "Error", message or "Failed to import project.")
            return
        self.refresh_projects()
        if self._on_open_project:
            self._on_open_project(flowchart_id)

    def _env_path(self) -> Path:
        return Path(__file__).resolve().parents[2] / ".env"

    def _get_api_key(self) -> str:
        key = os.getenv("NOVA_API_KEY", "").strip()
        if key:
            return key
        env_path = self._env_path()
        if not env_path.exists():
            return ""
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("NOVA_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            return ""
        return ""

    def _ensure_api_key(self, show_dialog: bool = False) -> bool:
        if self._get_api_key():
            return True
        QMessageBox.warning(
            self,
            "API Key Required",
            "Your API key is not set. Please add it in Settings.",
        )
        if show_dialog:
            self._open_settings()
        return False

    def _open_settings(self):
        if self._on_open_settings:
            self._on_open_settings()
