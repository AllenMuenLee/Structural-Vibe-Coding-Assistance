import sys
import os
import json
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QStackedWidget, QSplitter, QPushButton
from PyQt6.QtCore import Qt, QTimer


from app.pages.dashboard import DashboardWidget
from app.pages.projectBuilder import ProjectBuilderWidget
from app.pages.settings import SettingsWidget
from app.pages.canva import CanvaWidget, update_generate_button
from app.pages.codeEditor import CodeEditorWidget, record_editor_diff
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

    splitter = QSplitter()
    splitter.setOrientation(Qt.Orientation.Horizontal)

    chat_widget = {"instance": None}
    chat_visible = {"value": False}

    def _reload_canvas_if_any():
        if stacked.count() > 3:
            canvas_widget = stacked.widget(3)
            if isinstance(canvas_widget, CanvaWidget):
                canvas_widget.reload_flowchart()
                if getattr(canvas_widget, "canvas_widget", None):
                    try:
                        from src.utils.CacheMng import load_cache, save_cache
                        cache = load_cache()
                        if cache.get("flowchart_last_updated"):
                            prev_text = cache.get("flowchart_last_prev")
                            curr_text = cache.get("flowchart_last_curr")
                            engine = getattr(canvas_widget.canvas_widget, "code_editor_engine", None)
                            if engine and prev_text is not None and curr_text is not None:
                                try:
                                    import json as _json
                                    prev_flowchart = _json.loads(prev_text) if prev_text else {}
                                    curr_flowchart = _json.loads(curr_text) if curr_text else {}
                                    engine.add_changes(prev_flowchart, curr_flowchart)
                                except Exception:
                                    pass
                            cache["flowchart_last_updated"] = False
                            save_cache(cache)
                    except Exception:
                        pass
                    update_generate_button(canvas_widget.canvas_widget)

    def _on_chat_message():
        current = stacked.currentWidget()
        if isinstance(current, CodeEditorWidget):
            record_editor_diff(current.editor_widget)

    def _build_chat_widget():
        if splitter.count() > 1:
            try:
                old = splitter.widget(0)
                old.setParent(None)
                old.deleteLater()
            except Exception:
                pass
        chat_widget["instance"] = None
        flowchart_data = load_flowchart_data() or {}
        project_root = flowchart_data.get("project_root", "") if isinstance(flowchart_data, dict) else ""
        widget = ChatbotWidget(
            project_root,
            flowchart_data,
            parent=splitter,
            on_user_message=_on_chat_message,
            on_response=_reload_canvas_if_any,
            on_close=lambda: _set_chat_visible(False),
        )
        chat_widget["instance"] = widget
        splitter.insertWidget(0, widget)

    def _set_chat_visible(visible: bool):
        chat_visible["value"] = bool(visible)
        if not chat_visible["value"]:
            if splitter.count() > 1:
                w = splitter.widget(0)
                splitter.widget(0).setParent(None)
                w.deleteLater()
            chat_widget["instance"] = None
        else:
            _build_chat_widget()
        ai_btn.setVisible(not chat_visible["value"])
        _sync_splitter_state()
        try:
            ai_btn.setChecked(chat_visible["value"])
        except Exception:
            pass

    def _sync_splitter_state():
        if not chat_visible["value"]:
            splitter.setSizes([0, 1])
        else:
            splitter.setSizes([320, 880])

    splitter.addWidget(stacked)
    _sync_splitter_state()

    layout.addWidget(splitter)
    stacked.setCurrentIndex(0)

    ai_btn = QPushButton("AI", window)
    ai_btn.setObjectName("GlobalFloatingAIButton")
    ai_btn.setCheckable(True)
    ai_btn.setToolTip("AI chat")
    ai_btn.setFixedSize(56, 56)
    ai_btn.setStyleSheet(
        "QPushButton { background: #2f6fed; color: #ffffff; border: none; border-radius: 28px; "
        "font-weight: 700; font-size: 13px; }"
        "QPushButton:hover { background: #3a7bff; }"
        "QPushButton:checked { background: #1f56c9; }"
    )
    ai_btn.clicked.connect(lambda checked: _set_chat_visible(checked))
    ai_btn.hide()

    def _reposition_ai_btn():
        margin = 20
        ai_btn.move(margin, max(margin, window.height() - ai_btn.height() - margin))
        if ai_btn.isVisible():
            ai_btn.raise_()

    orig_resize = window.resizeEvent

    def _on_resize(event):
        if callable(orig_resize):
            orig_resize(event)
        _reposition_ai_btn()

    window.resizeEvent = _on_resize
    QTimer.singleShot(0, _reposition_ai_btn)

    def _toggle_chat_for_page(index):
        # Hide on dashboard (index 0)
        if index == 0:
            _set_chat_visible(False)
            ai_btn.setVisible(False)
        else:
            ai_btn.setVisible(not chat_visible["value"])
            ai_btn.raise_()
            ai_btn.setChecked(chat_visible["value"])

    stacked.currentChanged.connect(_toggle_chat_for_page)

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
