import sys

from PyQt6.QtWidgets import QApplication

from src.pages.projectBuilder import ProjectBuilderWidget


def main():
    app = QApplication(sys.argv)
    window = ProjectBuilderWidget()
    window.setWindowTitle("Project Builder")
    window.resize(900, 600)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
