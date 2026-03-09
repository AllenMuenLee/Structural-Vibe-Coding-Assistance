def apply_code_editor_theme(root):
    from pathlib import Path

    style_path = Path(__file__).resolve().parents[2] / "style" / "code_editor.qss"
    if style_path.exists():
        root.setStyleSheet(style_path.read_text(encoding="utf-8"))
