import json
import os
from pathlib import Path

from PyQt6.QtCore import Qt
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
)

from src.utils import FileMng
from src.core.ai_helper import generate_flowchart_from_description
from src.core.Flowchart import Flowchart
from src.utils.CacheMng import save_current_project_id
from src.pages.loadingScreen import LoadingScreen

def _apply_theme(widget: QWidget) -> None:
    style_path = Path(__file__).resolve().parents[1] / "style" / "project_builder.qss"
    if style_path.exists():
        widget.setStyleSheet(style_path.read_text(encoding="utf-8"))


def build_project_builder() -> QWidget:
    root = QWidget()
    root.setObjectName("ProjectBuilderRoot")
    _apply_theme(root)

    app_font = QFont("Inter", 10)
    if app_font.family() == "Inter":
        root.setFont(app_font)
    else:
        root.setFont(QFont("Segoe UI", 10))

    outer = QVBoxLayout(root)
    outer.setContentsMargins(32, 32, 32, 32)
    outer.setSpacing(24)

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
    create_button = QPushButton("Create Project")
    create_button.setObjectName("PrimaryButton")
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

    def on_browse():
        folder = QFileDialog.getExistingDirectory(root, "Select Project Folder")
        if folder:
            title_input.setText(folder)

    def on_create():
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
        hint_label.setText("Generating flowchart...")
        loading = LoadingScreen(root, message="Generating your flowchart. Please wait...")
        loading.show()
        root.repaint()
        try:
            ai_data = generate_flowchart_from_description(desc, project_path)
            framework = ai_data.get("framework", "")
            project_root = os.path.abspath(project_path)

            my_flowchart = Flowchart(name=os.path.basename(project_root), framework=framework, project_path=project_root)
            my_flowchart.create_from_ai_response(ai_data)

            flowchart_id = my_flowchart.flowchart_id
            
            my_flowchart.save_to_file(flowchart_id)
            FileMng.save_project(flowchart_id, project_root)
            save_current_project_id(flowchart_id)

            
        except Exception as exc:
            hint_label.setText(f"Failed to generate flowchart: {exc}")
        finally:
            loading.close()

    browse_button.clicked.connect(on_browse)
    create_button.clicked.connect(on_create)

    return root


class ProjectBuilderWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(build_project_builder())
