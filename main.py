import sys
import os
import json
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QStackedWidget, QPushButton
from PyQt6.QtCore import QTimer, Qt, QPoint
from PyQt6.QtGui import QCursor


class DraggableAIButton(QPushButton):
    """Floating AI button that can be freely dragged around its parent window."""

    DRAG_THRESHOLD = 6  # pixels of movement before we treat it as a drag

    def __init__(self, parent=None):
        super().__init__("AI", parent)
        self._drag_start_global = QPoint()
        self._drag_start_local = QPoint()
        self._is_dragging = False

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_global = event.globalPosition().toPoint()
            self._drag_start_local = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._is_dragging = False
        event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self._drag_start_global
            if not self._is_dragging and delta.manhattanLength() > self.DRAG_THRESHOLD:
                self._is_dragging = True
                self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))

            if self._is_dragging:
                parent = self.parent()
                new_pos = event.globalPosition().toPoint() - self._drag_start_local
                # Clamp within parent bounds
                max_x = parent.width() - self.width()
                max_y = parent.height() - self.height()
                new_pos.setX(max(0, min(max_x, new_pos.x())))
                new_pos.setY(max(0, min(max_y, new_pos.y())))
                self.move(new_pos)
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            if not self._is_dragging:
                # Treat as a normal click — toggle checked state and emit
                self.setChecked(not self.isChecked())
                self.clicked.emit(self.isChecked())
            self._is_dragging = False
        event.accept()

from app.pages.dashboard import DashboardWidget
from app.pages.projectBuilder import ProjectBuilderWidget
from app.pages.settings import SettingsWidget
from app.pages.canva import CanvaWidget
from app.pages.codeEditor import CodeEditorWidget
from app.components.code_editor.chatbot_widget import ChatbotWidget
from src.utils.CacheMng import load_cache, save_current_project_id


def main():
    app = QApplication(sys.argv)
    window = QWidget()
    window.setWindowTitle("Vibe Coding App")
    window.resize(1200, 800)

    layout = QVBoxLayout(window)
    layout.setContentsMargins(0, 0, 0, 0)

    stacked = QStackedWidget()

    def load_flowchart_data():
        cache = load_cache()
        project_id = cache.get("current_project_id")
        if not project_id:
            return None

        appdata_root = os.path.join(os.getenv("APPDATA", ""), "SVCA")
        flowchart_path = os.path.join(appdata_root, f"{project_id}.flowchart.json")

        if os.path.exists(flowchart_path):
            try:
                with open(flowchart_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading flowchart: {e}")
        return None

    def show_canvas():
        if stacked.count() > 3:
            old_canvas = stacked.widget(3)
            stacked.removeWidget(old_canvas)
            old_canvas.deleteLater()

        canvas = CanvaWidget(on_back=on_back_to_dashboard)
        canvas.on_code_generated = on_code_generated
        stacked.insertWidget(3, canvas)
        stacked.setCurrentIndex(3)

    def on_project_created(success):
        if success:
            print("? Project created, navigating to Canvas...")
            _build_chat_widget()
            show_canvas()

    def on_code_generated():
        print("? Code generated, navigating to Editor...")
        flowchart_data = load_flowchart_data()
        if not flowchart_data:
            print("? Warning: Could not load flowchart data for editor")
            return

        if stacked.count() > 4:
            old_editor = stacked.widget(4)
            stacked.removeWidget(old_editor)
            old_editor.deleteLater()

        editor = CodeEditorWidget(flowchart_data, on_back_to_canvas)
        stacked.insertWidget(4, editor)
        stacked.setCurrentIndex(4)
        _build_chat_widget()

    def on_back_to_canvas():
        print("? Returning to Canvas...")
        show_canvas()

    def on_new_project():
        stacked.setCurrentIndex(1)

    def on_back_to_dashboard():
        stacked.setCurrentIndex(0)

    def on_open_settings():
        stacked.setCurrentIndex(2)

    def on_open_project(project_id):
        save_current_project_id(project_id)
        _build_chat_widget()
        show_canvas()

    dashboard = DashboardWidget(
        on_new_project=on_new_project,
        on_open_project=on_open_project,
        on_open_settings=on_open_settings,
    )
    builder = ProjectBuilderWidget(on_project_created=on_project_created, on_back=on_back_to_dashboard)
    settings = SettingsWidget(on_back=on_back_to_dashboard)

    stacked.addWidget(dashboard)  # Index 0
    stacked.addWidget(builder)    # Index 1
    stacked.addWidget(settings)   # Index 2

    layout.addWidget(stacked)
    stacked.setCurrentIndex(0)

    chat_overlay = QWidget(window)
    chat_overlay.setObjectName("GlobalChatOverlay")
    chat_overlay.setAutoFillBackground(True)
    chat_overlay.setStyleSheet("""
        QWidget#GlobalChatOverlay {
            background-color: #1e2233;
            border: 1.5px solid #3a4460;
            border-radius: 12px;
        }
        QLabel#ChatTitle {
            color: #e8eaf6;
            font-size: 15px;
            font-weight: 700;
            padding: 4px 0;
        }
        QTextEdit#ChatHistory {
            background-color: #151827;
            color: #c9cfe8;
            border: 1px solid #2a3250;
            border-radius: 8px;
            padding: 8px;
            font-size: 13px;
            selection-background-color: #2f6fed;
        }
        QTextEdit#ChatInput {
            background-color: #151827;
            color: #c9cfe8;
            border: 1px solid #2a3250;
            border-radius: 6px;
            padding: 6px;
            font-size: 13px;
        }
        QTextEdit#ChatInput:focus {
            border: 1px solid #2f6fed;
        }
        QPushButton#ChatSendButton {
            background-color: #2f6fed;
            color: #ffffff;
            border: none;
            border-radius: 6px;
            padding: 6px 14px;
            font-weight: 600;
            font-size: 13px;
        }
        QPushButton#ChatSendButton:hover   { background-color: #3a7bff; }
        QPushButton#ChatSendButton:pressed  { background-color: #1f56c9; }
        QPushButton#ChatSendButton:disabled { background-color: #2a3250; color: #5a6280; }
        QPushButton#ChatPlusButton {
            background-color: #252a40;
            color: #8899cc;
            border: 1px solid #3a4460;
            border-radius: 6px;
            padding: 4px 10px;
            font-size: 16px;
            font-weight: 700;
        }
        QPushButton#ChatPlusButton:hover { background-color: #2f3650; color: #c9cfe8; }
        QPushButton#ModeButton {
            background-color: #252a40;
            color: #8899cc;
            border: 1px solid #3a4460;
            border-radius: 5px;
            padding: 4px 10px;
            font-size: 12px;
        }
        QPushButton#ModeButton:hover { background-color: #2f3650; color: #e8eaf6; }
        QWidget#ModeMenu { background: transparent; }
        QLabel#ModeTag {
            color: #5a7acc;
            font-size: 11px;
            padding: 2px 0;
        }
    """)
    chat_overlay_layout = QVBoxLayout(chat_overlay)
    chat_overlay_layout.setContentsMargins(12, 12, 12, 12)
    chat_overlay_layout.setSpacing(8)
    chat_overlay.hide()

    chat_widget = {"instance": None}

    def _build_chat_widget():
        if chat_widget["instance"]:
            chat_widget["instance"].setParent(None)
        flowchart_data = load_flowchart_data() or {}
        project_root = flowchart_data.get("project_root", "") if isinstance(flowchart_data, dict) else ""
        widget = ChatbotWidget(project_root, flowchart_data, parent=chat_overlay)
        chat_overlay_layout.addWidget(widget)
        chat_widget["instance"] = widget

    def _toggle_chat_overlay(show=None):
        if show is None:
            show = not chat_overlay.isVisible()
        if show and chat_widget["instance"] is None:
            _build_chat_widget()
        chat_overlay.setVisible(bool(show))
        if show:
            chat_overlay.raise_()
            ai_btn.setChecked(True)
        else:
            ai_btn.setChecked(False)

    ai_btn = DraggableAIButton(window)
    ai_btn.setObjectName("GlobalFloatingAIButton")
    ai_btn.setCheckable(True)
    ai_btn.setToolTip("AI chat — drag to reposition")
    ai_btn.setFixedSize(56, 56)
    ai_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    ai_btn.setStyleSheet(
        "QPushButton { background: #2f6fed; color: #ffffff; border: none; border-radius: 28px; "
        "font-weight: 700; font-size: 13px; }"
        "QPushButton:hover { background: #3a7bff; }"
        "QPushButton:checked { background: #1f56c9; }"
    )
    ai_btn.clicked.connect(lambda checked: _toggle_chat_overlay(checked))
    ai_btn.hide()  # Hidden by default; shown only on Flowchart (3) and CodeEditor (4)

    # Pages where the AI button should be visible
    AI_BUTTON_PAGES = {3, 4}

    def _on_page_changed(index):
        visible = index in AI_BUTTON_PAGES
        ai_btn.setVisible(visible)
        if not visible:
            # Also hide the chat overlay when leaving AI-enabled pages
            _toggle_chat_overlay(show=False)
        else:
            ai_btn.raise_()

    stacked.currentChanged.connect(_on_page_changed)

    _btn_initial_pos_set = [False]

    def _reposition_overlay():
        margin = 20
        # On first show, place the button at the default bottom-left corner.
        # On subsequent resizes, just clamp the current position to stay within bounds.
        if not _btn_initial_pos_set[0]:
            ai_btn.move(margin, max(margin, window.height() - ai_btn.height() - margin))
            _btn_initial_pos_set[0] = True
        else:
            cur = ai_btn.pos()
            max_x = window.width() - ai_btn.width() - margin
            max_y = window.height() - ai_btn.height() - margin
            ai_btn.move(
                max(margin, min(cur.x(), max_x)),
                max(margin, min(cur.y(), max_y)),
            )
        overlay_w = 380
        overlay_h = 620
        chat_overlay.setGeometry(
            max(margin, window.width() - overlay_w - margin),
            margin,
            overlay_w,
            min(overlay_h, window.height() - (margin * 2)),
        )
        chat_overlay.raise_()
        if ai_btn.isVisible():
            ai_btn.raise_()

    orig_resize = window.resizeEvent

    def _on_resize(event):
        if callable(orig_resize):
            orig_resize(event)
        _reposition_overlay()

    window.resizeEvent = _on_resize
    QTimer.singleShot(0, _reposition_overlay)

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()