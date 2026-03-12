from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QPushButton


def attach_floating_ai_button(root, on_toggle):
    if getattr(root, "floating_ai_btn", None):
        return
    btn = QPushButton("AI", root)
    btn.setObjectName("FloatingAIButton")
    btn.setToolTip("AI chat")
    btn.setCheckable(True)
    btn.clicked.connect(lambda checked: on_toggle(checked))
    btn.setFixedSize(56, 56)
    btn.raise_()
    root.floating_ai_btn = btn

    def _reposition():
        margin = 20
        btn.move(margin, max(margin, root.height() - btn.height() - margin))
        btn.raise_()

    orig_resize = root.resizeEvent

    def _on_resize(event):
        if callable(orig_resize):
            orig_resize(event)
        _reposition()

    root.resizeEvent = _on_resize
    QTimer.singleShot(0, _reposition)
