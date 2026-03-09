from PyQt6.QtGui import QFont, QTextCharFormat, QColor, QSyntaxHighlighter


class PythonHighlighter(QSyntaxHighlighter):
    """Simple syntax highlighter for Python code."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Define highlighting rules
        self.highlighting_rules = []

        # Keywords
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#c678dd"))  # Purple
        keyword_format.setFontWeight(QFont.Weight.Bold)
        keywords = [
            "def",
            "class",
            "import",
            "from",
            "if",
            "else",
            "elif",
            "for",
            "while",
            "return",
            "try",
            "except",
            "with",
            "as",
            "True",
            "False",
            "None",
            "and",
            "or",
            "not",
            "in",
            "is",
            "async",
            "await",
            "break",
            "continue",
            "pass",
            "raise",
        ]
        for word in keywords:
            pattern = f"\\b{word}\\b"
            self.highlighting_rules.append((pattern, keyword_format))

        # Strings
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#98c379"))  # Green
        self.highlighting_rules.append((r'"[^"\\]*(\\.[^"\\]*)*"', string_format))
        self.highlighting_rules.append((r"'[^'\\]*(\\.[^'\\]*)*'", string_format))

        # Comments
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#5c6370"))  # Gray
        self.highlighting_rules.append((r"#[^\n]*", comment_format))

        # Functions
        function_format = QTextCharFormat()
        function_format.setForeground(QColor("#61afef"))  # Blue
        self.highlighting_rules.append((r"\bdef\s+(\w+)", function_format))

        # Numbers
        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#d19a66"))  # Orange
        self.highlighting_rules.append((r"\b[0-9]+\b", number_format))

    def highlightBlock(self, text):
        import re

        for pattern, format_style in self.highlighting_rules:
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), match.end() - match.start(), format_style)
