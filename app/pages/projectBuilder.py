import os
import os
import time
from pathlib import Path

from functools import partial
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QMessageBox,
    QFileDialog,
    QApplication,
)

from src.utils import FileMng
from src.utils.CacheMng import save_current_project_id
from src.utils.NetUtils import is_connection_error
from app.pages.loadingScreen import LoadingScreen

class ProjectBuildWorker(QThread):
    finished = pyqtSignal(bool, str, str)  # success, message, flowchart_id
    progress = pyqtSignal(str)

    def __init__(self, project_path, description):
        super().__init__()
        self.project_path = project_path
        self.description = description

    def run(self):
        try:
            max_retries = 3
            for attempt in range(1, max_retries + 1):
                try:
                    from src.core.ai_helper import generate_flowchart_from_description
                    ai_data = generate_flowchart_from_description(self.description, self.project_path)
                    break
                except Exception as exc:
                    if not is_connection_error(exc) or attempt >= max_retries:
                        raise
                    self.progress.emit(
                        f"Connection issue. Retrying in 3 seconds... ({attempt}/{max_retries})"
                    )
                    time.sleep(3)

            framework = ai_data.get("framework", "")
            project_root = os.path.abspath(self.project_path)

            from src.core.Flowchart import Flowchart
            flowchart = Flowchart(
                name=os.path.basename(project_root),
                framework=framework,
                project_root=project_root
            )

            flowchart.create_from_ai_response(ai_data)
            flowchart_dict = flowchart.flowchart_to_dictionary()
            flowchart_id = flowchart.flowchart_id

            flowchart.save_to_file(flowchart_id, flowchart_dict)
            FileMng.save_project(flowchart_id, project_root)
            save_current_project_id(flowchart_id)

            self.finished.emit(True, "", flowchart_id)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            self.finished.emit(False, f"Failed to generate flowchart: {exc}", "")

def _apply_theme(widget: QWidget) -> None:
    app_root = Path(__file__).resolve().parents[1]
    style_path = app_root / "style" / "project_builder.qss"
    if style_path.exists():
        widget.setStyleSheet(style_path.read_text(encoding="utf-8"))


def _set_loading_message(loading: LoadingScreen, message: str) -> None:
    if loading:
        loading.set_message(message)


def _handle_project_build_finished(root, loading, hint_label, success, message, _flowchart_id):
    loading.close()
    if success:
        if root._on_project_created:
            root._on_project_created(True)
    else:
        hint_label.setText(message or "Failed to generate flowchart.")
        if root._on_project_created:
            root._on_project_created(False)


def _on_project_browse(root, title_input):
    folder = QFileDialog.getExistingDirectory(root, "Select Project Folder")
    if folder:
        title_input.setText(folder)


def _on_project_create(root, title_input, desc_input, hint_label):
    project_path = title_input.text().strip()
    desc = desc_input.toPlainText().strip()

    missing = []
    if not project_path:
        missing.append("project path")
    if not desc:
        missing.append("project description")

    if missing:
        hint_label.setText("Please provide " + " and ".join(missing) + ".")
        return

    if not os.path.exists(project_path):
        reply = QMessageBox.question(
            root,
            "Create Folder",
            "That folder doesn't exist. Create it now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            hint_label.setText("Project creation cancelled.")
            return
        try:
            os.makedirs(project_path, exist_ok=True)
        except Exception as exc:
            hint_label.setText(f"Failed to create folder: {exc}")
            return
    elif not os.path.isdir(project_path):
        hint_label.setText("Project path must be a folder.")
        return

    hint_label.setText("Generating flowchart...")
    loading = LoadingScreen(root, message="Generating your flowchart. Please wait...")
    loading.show()
    QApplication.processEvents()
    root.repaint()

    worker = ProjectBuildWorker(project_path, desc)
    worker.progress.connect(partial(_set_loading_message, loading))
    worker.finished.connect(partial(_handle_project_build_finished, root, loading, hint_label))
    worker.start()
    root._build_worker = worker


def _on_project_create_manually(root, title_input, hint_label):
    project_path = title_input.text().strip()
    if not project_path:
        hint_label.setText("Please provide a project path.")
        return
    if not os.path.exists(project_path):
        os.makedirs(project_path, exist_ok=True)
    from src.core.Step import Step
    from src.core.Flowchart import Flowchart
    project_root = os.path.abspath(project_path)
    flowchart = Flowchart(name=os.path.basename(project_root), framework="", project_root=project_root)
    placeholder = Step(
        id="step1",
        description="Describe this step",
        filenames=[],
        files_to_import=[],
        command=[],
        children=[],
    )
    flowchart.add_step(placeholder)
    flowchart.set_start("step1")
    flowchart_dict = flowchart.flowchart_to_dictionary()
    flowchart.save_to_file(flowchart.flowchart_id, flowchart_dict)
    FileMng.save_project(flowchart.flowchart_id, project_root)
    save_current_project_id(flowchart.flowchart_id)
    if root._on_project_created:
        root._on_project_created(True)


def build_project_builder(on_project_created=None, on_back=None) -> QWidget:
    root = QWidget()
    root.setObjectName("ProjectBuilderRoot")
    _apply_theme(root)
    root._on_project_created = on_project_created

    app_font = QFont("IBM Plex Sans", 10)
    if app_font.family() == "IBM Plex Sans":
        root.setFont(app_font)
    else:
        root.setFont(QFont("Segoe UI", 10))

    outer = QVBoxLayout(root)
    outer.setContentsMargins(32, 32, 32, 32)
    outer.setSpacing(24)

    back_row = QHBoxLayout()
    back_row.setSpacing(12)
    back_btn = QPushButton("Back")
    back_btn.setObjectName("BackButton")
    back_btn.setEnabled(on_back is not None)
    back_btn.clicked.connect(lambda: on_back() if on_back else None)
    back_row.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignLeft)
    back_row.addStretch()
    outer.addLayout(back_row)

    header = QVBoxLayout()
    header.setSpacing(6)
    title = QLabel("Project Builder")
    title.setObjectName("Title")
    subtitle = QLabel("Create a new project with a clear name and description.")
    subtitle.setObjectName("Subtitle")
    header.addWidget(title)
    header.addWidget(subtitle)

    outer.addLayout(header)

    card = QFrame()
    card.setObjectName("Card")
    shadow = QGraphicsDropShadowEffect(blurRadius=20, xOffset=0, yOffset=8)
    shadow.setColor(QColor(0, 0, 0, 30))
    card.setGraphicsEffect(shadow)

    card_layout = QVBoxLayout(card)
    card_layout.setContentsMargins(20, 20, 20, 20)
    card_layout.setSpacing(16)

    title_label = QLabel("Project Path")
    title_label.setObjectName("FieldLabel")
    title_input = QLineEdit()
    title_input.setPlaceholderText("Select or enter a project folder")
    title_input.setObjectName("TitleInput")

    browse_button = QPushButton("Browse")
    browse_button.setObjectName("BrowseButton")
    browse_button.setToolTip("Browse")
    browse_button.setCursor(Qt.CursorShape.PointingHandCursor)

    path_row = QHBoxLayout()
    path_row.setSpacing(8)
    path_row.addWidget(title_input, 1)
    path_row.addWidget(browse_button)

    desc_label = QLabel("Project Description")
    desc_label.setObjectName("FieldLabel")
    desc_input = QTextEdit()
    desc_input.setPlaceholderText("Describe your project goals and features.")
    desc_input.setObjectName("DescriptionInput")
    desc_input.setFixedHeight(120)

    hint_label = QLabel("")
    hint_label.setObjectName("Hint")
    hint_label.setWordWrap(True)

    button_row = QHBoxLayout()
    button_row.addStretch(1)
    manual_button = QPushButton("Create Manually")
    manual_button.setObjectName("SecondaryButton")
    manual_button.setToolTip("Build your own flowchart without AI")
    manual_button.setCursor(Qt.CursorShape.PointingHandCursor)
    button_row.addWidget(manual_button)
    create_button = QPushButton("Create Project")
    create_button.setObjectName("PrimaryButton")
    create_button.setToolTip("Create project")
    create_button.setCursor(Qt.CursorShape.PointingHandCursor)
    button_row.addWidget(create_button)

    card_layout.addWidget(title_label)
    card_layout.addLayout(path_row)
    card_layout.addWidget(desc_label)
    card_layout.addWidget(desc_input)
    card_layout.addWidget(hint_label)
    card_layout.addLayout(button_row)

    outer.addWidget(card)
    outer.addStretch(1)

    browse_button.clicked.connect(partial(_on_project_browse, root, title_input))
    create_button.clicked.connect(partial(_on_project_create, root, title_input, desc_input, hint_label))
    manual_button.clicked.connect(partial(_on_project_create_manually, root, title_input, hint_label))

    return root


class ProjectBuilderWidget(QWidget):
    def __init__(self, on_project_created=None, on_back=None):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(build_project_builder(on_project_created=on_project_created, on_back=on_back))
