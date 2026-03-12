import os
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QMessageBox,
)
from src.utils.CacheMng import load_cache, save_cache


def _apply_theme(widget: QWidget) -> None:
    style_path = Path(__file__).resolve().parent.parent / "style" / "settings.qss"
    if style_path.exists():
        widget.setStyleSheet(style_path.read_text(encoding="utf-8"))


def _env_path() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def _get_api_key() -> str:
    key = os.getenv("NOVA_API_KEY", "").strip()
    if key:
        return key
    env_path = _env_path()
    if not env_path.exists():
        return ""
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("NOVA_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        return ""
    return ""


def _save_api_key(key: str) -> None:
    env_path = _env_path()
    lines = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    updated = False
    for idx, line in enumerate(lines):
        if line.strip().startswith("NOVA_API_KEY="):
            lines[idx] = f"NOVA_API_KEY={key}"
            updated = True
            break
    if not updated:
        lines.append(f"NOVA_API_KEY={key}")
    env_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    os.environ["NOVA_API_KEY"] = key


class SettingsWidget(QWidget):
    def __init__(self, on_back=None):
        super().__init__()
        self.setObjectName("SettingsPage")
        self._on_back = on_back
        _apply_theme(self)

        app_font = QFont("IBM Plex Sans", 10)
        if app_font.family() == "IBM Plex Sans":
            self.setFont(app_font)
        else:
            self.setFont(QFont("Segoe UI", 10))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 32, 32, 32)
        outer.setSpacing(24)

        back_row = QHBoxLayout()
        back_row.setSpacing(12)
        back_btn = QPushButton("Back")
        back_btn.setObjectName("BackButton")
        back_btn.setEnabled(on_back is not None)
        back_btn.clicked.connect(self._handle_back)
        back_row.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        back_row.addStretch()
        outer.addLayout(back_row)

        header = QVBoxLayout()
        header.setSpacing(6)
        title = QLabel("Settings")
        title.setObjectName("SettingsTitle")
        subtitle = QLabel("Configure your API key to enable AI features.")
        subtitle.setObjectName("SettingsSubtitle")
        header.addWidget(title)
        header.addWidget(subtitle)
        outer.addLayout(header)

        card = QFrame()
        card.setObjectName("SettingsCard")
        shadow = QGraphicsDropShadowEffect(blurRadius=20, xOffset=0, yOffset=8)
        shadow.setColor(QColor(0, 0, 0, 30))
        card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(12)

        key_label = QLabel("API Key")
        key_label.setObjectName("SettingsLabel")
        self.key_input = QLineEdit()
        self.key_input.setObjectName("SettingsInput")
        self.key_input.setPlaceholderText("Enter your NOVA_API_KEY")
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.hint_label = QLabel("")
        self.hint_label.setObjectName("SettingsHint")

        self.limit_label = QLabel("")
        self.limit_label.setObjectName("SettingsWarning")

        save_btn = QPushButton("Save")
        save_btn.setObjectName("PrimaryButton")
        save_btn.clicked.connect(self._save_key)

        card_layout.addWidget(key_label)
        card_layout.addWidget(self.key_input)
        card_layout.addWidget(self.hint_label)
        card_layout.addWidget(self.limit_label)
        card_layout.addWidget(save_btn, alignment=Qt.AlignmentFlag.AlignRight)

        outer.addWidget(card)
        outer.addStretch(1)

        self._refresh()

    def _refresh(self):
        key = _get_api_key()
        if not key:
            self.hint_label.setText("API key is not set.")
        else:
            self.hint_label.setText("API key is set.")
        cache = load_cache()
        if cache.get("api_daily_limit_exceeded"):
            msg = cache.get("api_daily_limit_message", "")
            if msg:
                self.limit_label.setText("Daily limit exceeded: " + msg)
            else:
                self.limit_label.setText("Daily limit exceeded for the current API key.")
        else:
            self.limit_label.setText("")

    def _save_key(self):
        key = self.key_input.text().strip()
        if not key:
            QMessageBox.warning(self, "Invalid Key", "API key cannot be empty.")
            return
        _save_api_key(key)
        cache = load_cache()
        if cache.get("api_daily_limit_exceeded"):
            cache["api_daily_limit_exceeded"] = False
            cache["api_daily_limit_message"] = ""
            save_cache(cache)
        self.key_input.clear()
        self._refresh()
        QMessageBox.information(self, "Saved", "API key saved.")

    def _handle_back(self):
        if not _get_api_key():
            QMessageBox.warning(
                self,
                "API Key Required",
                "Your API key is not set. Please add it before leaving Settings.",
            )
            return
        if self._on_back:
            self._on_back()

    def showEvent(self, event):
        super().showEvent(event)
        if not _get_api_key():
            QMessageBox.warning(
                self,
                "API Key Required",
                "Your API key is not set. Please add it in Settings.",
            )
        self._refresh()
