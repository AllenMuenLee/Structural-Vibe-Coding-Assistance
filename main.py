import sys
import os
import json
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QStackedWidget, QSplitter, QPushButton
from PyQt6.QtCore import Qt, QTimer, QEvent, QPoint, QObject

from app.pages.dashboard import DashboardWidget
from app.pages.projectBuilder import ProjectBuilderWidget
from app.pages.settings import SettingsWidget
from app.pages.canva import CanvaWidget, update_generate_button
from app.pages.codeEditor import CodeEditorWidget, record_editor_diff
from app.components.code_editor.chatbot_widget import ChatbotWidget
from src.utils.CacheMng import load_cache, save_cache, save_current_project_id


class AppController(QObject):
    def __init__(self):
        super().__init__()
        self.app = QApplication(sys.argv)
        self.window = QWidget()
        self.window.setWindowTitle("Vibe Coding App")
        self.window.resize(1200, 800)

        self.layout = QVBoxLayout(self.window)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.stacked = QStackedWidget()
        self.splitter = QSplitter()
        self.splitter.setOrientation(Qt.Orientation.Horizontal)

        self.chat_widget = None
        self.chat_visible = False
        self.ai_btn = None
        self._ai_dragging = False
        self._ai_drag_offset = QPoint(0, 0)
        self._orig_resize = None

        self._build_pages()
        self._build_splitter()
        self._build_ai_button()
        self._connect_signals()

        self.layout.addWidget(self.splitter)
        self.stacked.setCurrentIndex(0)

    def run(self):
        self.window.show()
        sys.exit(self.app.exec())

    def load_flowchart_data(self):
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

    def show_canvas(self):
        if self.stacked.count() > 3:
            old_canvas = self.stacked.widget(3)
            self.stacked.removeWidget(old_canvas)
            old_canvas.deleteLater()

        canvas = CanvaWidget(on_back=self.on_back_to_dashboard)
        canvas.on_code_generated = self.on_code_generated
        self.stacked.insertWidget(3, canvas)
        self.stacked.setCurrentIndex(3)

    def on_project_created(self, success):
        if success:
            print("? Project created, navigating to Canvas...")
            self.show_canvas()

    def on_code_generated(self):
        print("? Code generated, navigating to Editor...")
        flowchart_data = self.load_flowchart_data()
        if not flowchart_data:
            print("? Warning: Could not load flowchart data for editor")
            return

        if self.stacked.count() > 4:
            old_editor = self.stacked.widget(4)
            self.stacked.removeWidget(old_editor)
            old_editor.deleteLater()

        editor = CodeEditorWidget(flowchart_data, self.on_back_to_canvas)
        self.stacked.insertWidget(4, editor)
        self.stacked.setCurrentIndex(4)

    def on_back_to_canvas(self):
        print("? Returning to Canvas...")
        self.show_canvas()

    def on_new_project(self):
        self.stacked.setCurrentIndex(1)

    def on_back_to_dashboard(self):
        self.stacked.setCurrentIndex(0)

    def on_open_settings(self):
        self.stacked.setCurrentIndex(2)

    def on_open_project(self, project_id):
        save_current_project_id(project_id)
        self.show_canvas()

    def _build_pages(self):
        dashboard = DashboardWidget(
            on_new_project=self.on_new_project,
            on_open_project=self.on_open_project,
            on_open_settings=self.on_open_settings,
        )
        builder = ProjectBuilderWidget(
            on_project_created=self.on_project_created,
            on_back=self.on_back_to_dashboard,
        )
        settings = SettingsWidget(on_back=self.on_back_to_dashboard)

        self.stacked.addWidget(dashboard)  # Index 0
        self.stacked.addWidget(builder)    # Index 1
        self.stacked.addWidget(settings)   # Index 2

    def _build_splitter(self):
        self.splitter.addWidget(self.stacked)
        self._sync_splitter_state()

    def _build_ai_button(self):
        self.ai_btn = QPushButton("AI", self.window)
        self.ai_btn.setObjectName("GlobalFloatingAIButton")
        self.ai_btn.setCheckable(True)
        self.ai_btn.setToolTip("AI chat")
        self.ai_btn.setFixedSize(56, 56)
        self.ai_btn.setStyleSheet(
            "QPushButton { background: #2f6fed; color: #ffffff; border: none; border-radius: 28px; "
            "font-weight: 700; font-size: 13px; }"
            "QPushButton:hover { background: #3a7bff; }"
            "QPushButton:checked { background: #1f56c9; }"
        )
        self.ai_btn.clicked.connect(self._on_ai_clicked)
        self.ai_btn.installEventFilter(self)
        self.ai_btn.hide()

        self._orig_resize = self.window.resizeEvent
        self.window.resizeEvent = self._on_resize
        QTimer.singleShot(0, self._reposition_ai_btn)

    def _connect_signals(self):
        self.stacked.currentChanged.connect(self._toggle_chat_for_page)

    def _reload_canvas_if_any(self):
        if self.stacked.count() > 3:
            canvas_widget = self.stacked.widget(3)
            if isinstance(canvas_widget, CanvaWidget):
                canvas_widget.reload_flowchart()
                if getattr(canvas_widget, "canvas_widget", None):
                    try:
                        cache = load_cache()
                        if cache.get("flowchart_last_updated"):
                            prev_text = cache.get("flowchart_last_prev")
                            curr_text = cache.get("flowchart_last_curr")
                            engine = getattr(canvas_widget.canvas_widget, "code_editor_engine", None)
                            if engine and prev_text is not None and curr_text is not None:
                                try:
                                    prev_flowchart = json.loads(prev_text) if prev_text else {}
                                    curr_flowchart = json.loads(curr_text) if curr_text else {}
                                    engine.add_changes(prev_flowchart, curr_flowchart)
                                except Exception:
                                    pass
                            cache["flowchart_last_updated"] = False
                            save_cache(cache)
                    except Exception:
                        pass
                    update_generate_button(canvas_widget.canvas_widget)

    def _on_chat_message(self):
        current = self.stacked.currentWidget()
        if isinstance(current, CodeEditorWidget):
            record_editor_diff(current.editor_widget)

    def _build_chat_widget(self):
        if self.splitter.count() > 1:
            try:
                old = self.splitter.widget(0)
                old.setParent(None)
                old.deleteLater()
            except Exception:
                pass
        self.chat_widget = None
        flowchart_data = self.load_flowchart_data() or {}
        project_root = flowchart_data.get("project_root", "") if isinstance(flowchart_data, dict) else ""
        widget = ChatbotWidget(
            project_root,
            flowchart_data,
            parent=self.splitter,
            on_user_message=self._on_chat_message,
            on_response=self._reload_canvas_if_any,
            on_close=self._handle_chat_close,
        )
        self.chat_widget = widget
        self.splitter.insertWidget(0, widget)

    def _set_chat_visible(self, visible: bool):
        self.chat_visible = bool(visible)
        if not self.chat_visible:
            if self.splitter.count() > 1:
                w = self.splitter.widget(0)
                self.splitter.widget(0).setParent(None)
                w.deleteLater()
            self.chat_widget = None
        else:
            self._build_chat_widget()
        self.ai_btn.setVisible(not self.chat_visible)
        self._sync_splitter_state()
        try:
            self.ai_btn.setChecked(self.chat_visible)
        except Exception:
            pass

    def _sync_splitter_state(self):
        if not self.chat_visible:
            self.splitter.setSizes([0, 1])
        else:
            self.splitter.setSizes([320, 880])

    def _handle_chat_close(self):
        self._set_chat_visible(False)

    def _on_ai_clicked(self, checked):
        self._set_chat_visible(checked)

    def _reposition_ai_btn(self):
        margin = 20
        self.ai_btn.move(margin, max(margin, self.window.height() - self.ai_btn.height() - margin))
        if self.ai_btn.isVisible():
            self.ai_btn.raise_()

    def _on_resize(self, event):
        if callable(self._orig_resize):
            self._orig_resize(event)
        self._reposition_ai_btn()

    def _toggle_chat_for_page(self, index):
        if index == 0:
            self._set_chat_visible(False)
            self.ai_btn.setVisible(False)
        else:
            self.ai_btn.setVisible(not self.chat_visible)
            self.ai_btn.raise_()
            self.ai_btn.setChecked(self.chat_visible)

    def eventFilter(self, obj, event):
        if obj is self.ai_btn:
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._ai_dragging = True
                self._ai_drag_offset = event.position().toPoint()
                return True
            if event.type() == QEvent.Type.MouseMove and self._ai_dragging:
                pos = event.globalPosition().toPoint() - self.window.pos() - self._ai_drag_offset
                max_x = max(0, self.window.width() - self.ai_btn.width())
                max_y = max(0, self.window.height() - self.ai_btn.height())
                new_x = max(0, min(pos.x(), max_x))
                new_y = max(0, min(pos.y(), max_y))
                self.ai_btn.move(new_x, new_y)
                return True
            if event.type() == QEvent.Type.MouseButtonRelease and self._ai_dragging:
                self._ai_dragging = False
                return True
        return super().eventFilter(obj, event)


def main():
    controller = AppController()
    controller.run()


if __name__ == "__main__":
    main()
