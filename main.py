import sys
import os
import json
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QStackedWidget

from app.pages.dashboard import DashboardWidget
from app.pages.projectBuilder import ProjectBuilderWidget
from app.pages.settings import SettingsWidget
from app.pages.canva import CanvaWidget
from app.pages.codeEditor import CodeEditorWidget
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

    layout.addWidget(stacked)
    stacked.setCurrentIndex(0)

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
