import os
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QMessageBox, QInputDialog, QApplication
from PyQt6.QtGui import QKeySequence, QShortcut, QColor, QTextCursor
from PyQt6.QtCore import Qt, QProcess
from PyQt6.Qsci import (
    QsciLexerPython,
    QsciLexerJavaScript,
    QsciLexerHTML,
    QsciLexerCSS,
    QsciLexerJSON,
    QsciLexerMarkdown,
    QsciLexerCPP,
)
import src.utils.Terminal as Terminal
from app.components.code_editor.toolbar import build_toolbar
from app.components.code_editor.content_splitter import build_content_splitter
from app.components.code_editor.editor_panel import apply_editor_theme
from app.components.code_editor import file_panel as file_panel_actions
from app.components.code_editor.terminal_panel import (
    build_terminal_panel,
    detect_terminal_error,
    set_debug_visible,
)
from app.components.code_editor.page_theme import apply_code_editor_theme


def build_code_editor(flowchart_data=None, on_back_to_canvas=None) -> QWidget:
    """Build the code editor view with improved layout."""

    root = QWidget()
    root.setObjectName("CodeEditorPage")

    main_layout = QVBoxLayout(root)
    main_layout.setContentsMargins(0, 0, 0, 0)
    main_layout.setSpacing(0)

    toolbar, chatbot_btn = build_toolbar(
        root=root,
        flowchart_data=flowchart_data,
        on_back_to_canvas=on_back_to_canvas,
        on_run_project=lambda: on_run_project(root),
        open_terminal_fn=Terminal.open_system_terminal,
    )
    main_layout.addWidget(toolbar)

    (
        content_splitter,
        file_tree,
        file_model,
        code_editor,
        current_file_label,
        find_bar,
        find_input,
        find_prev_btn,
        find_next_btn,
        find_case,
    ) = build_content_splitter(
        on_file_clicked=lambda filename: load_file(root, filename),
        on_save=lambda: save_file(root),
    )
    main_layout.addWidget(content_splitter, stretch=3)

    (
        terminal_container,
        terminal,
        terminal_input,
        terminal_run_btn,
        stop_process_btn,
        terminal_clear_btn,
        terminal_debug_btn,
    ) = build_terminal_panel(
        on_run_command=lambda: execute_terminal_command(root),
        on_clear=lambda: _clear_terminal(root),
        on_debug=lambda: _open_debug_from_terminal(root),
    )
    main_layout.addWidget(terminal_container, stretch=1)

    # Store references
    root.file_tree = file_tree
    root.file_model = file_model
    root.code_editor = code_editor
    root.current_file_label = current_file_label
    root.find_bar = find_bar
    root.find_input = find_input
    root.find_prev_btn = find_prev_btn
    root.find_next_btn = find_next_btn
    root.find_case = find_case
    root.code_lexer = None
    root.terminal = terminal
    root.terminal_input = terminal_input
    root.terminal_run_btn = terminal_run_btn
    root.terminal_clear_btn = terminal_clear_btn
    root.stop_process_btn = stop_process_btn
    root.terminal_debug_btn = terminal_debug_btn
    root.terminal_process = None
    root.last_command_output = ""
    root.content_splitter = content_splitter
    root.flowchart_data = flowchart_data
    root.current_file = None
    root.chatbot_widget = None
    root.chatbot_btn = None
    # Shared terminal module runs commands to completion; no process tracking here.

    terminal_input.returnPressed.connect(lambda: execute_terminal_command(root))
    root.stop_process_btn.clicked.connect(lambda: _stop_terminal_process(root))
    root.find_input.returnPressed.connect(lambda: find_next(root))
    root.find_next_btn.clicked.connect(lambda: find_next(root))
    root.find_prev_btn.clicked.connect(lambda: find_prev(root))
    root.find_case.stateChanged.connect(lambda _: find_next(root, restart=True))

    find_shortcut = QShortcut(QKeySequence.StandardKey.Find, root)
    find_shortcut.activated.connect(lambda: _focus_find(root))
    root.find_shortcut = find_shortcut

    save_shortcut = QShortcut(QKeySequence.StandardKey.Save, root)
    save_shortcut.activated.connect(lambda: save_file(root))
    root.save_shortcut = save_shortcut
    apply_code_editor_theme(root)
    apply_editor_theme(root.code_editor)

    if flowchart_data:
        project_root = flowchart_data.get('project_root', '')
        file_panel_actions.set_project_root(root.file_tree, root.file_model, project_root)

    return root

def execute_terminal_command(root):
    """Execute command typed in terminal input."""
    command = root.terminal_input.text().strip()

    print(command)
    
    if not command:
        return
    
    # Clear input
    root.terminal_input.clear()
    
    # Get project root
    project_root = ""
    if root.flowchart_data:
        project_root = root.flowchart_data.get('project_root', '')

    _run_in_terminal(root, command, project_root if project_root else None)
    root.terminal_input.clear()


def _focus_find(root):
    if root.find_bar:
        root.find_bar.setVisible(True)
    if root.find_input:
        root.find_input.setFocus()
        root.find_input.selectAll()


def _set_editor_lexer(root, filename: str):
    if not root.code_editor:
        return
    _, ext = os.path.splitext(filename)
    ext = ext.lower().lstrip(".")

    lexer = None
    if ext == "py":
        lexer = QsciLexerPython(root.code_editor)
    elif ext in ("js", "jsx", "ts", "tsx"):
        lexer = QsciLexerJavaScript(root.code_editor)
    elif ext in ("html", "htm"):
        lexer = QsciLexerHTML(root.code_editor)
    elif ext in ("css", "scss"):
        lexer = QsciLexerCSS(root.code_editor)
    elif ext == "json":
        lexer = QsciLexerJSON(root.code_editor)
    elif ext in ("md", "markdown"):
        lexer = QsciLexerMarkdown(root.code_editor)
    elif ext in ("c", "cpp", "h", "hpp"):
        lexer = QsciLexerCPP(root.code_editor)

    root.code_editor.setLexer(lexer)
    root.code_lexer = lexer
    
    apply_editor_theme(root.code_editor)
    _apply_lexer_theme(root, lexer)


def _apply_lexer_theme(root, lexer):
    print("apply lexer")
    if not lexer:
        return
    font = getattr(root, "code_editor_font", None) or root.code_editor.font()
    lexer.setDefaultFont(font)
    lexer.setDefaultPaper(QColor("#10141c"))
    lexer.setDefaultColor(QColor("#e7e9ee"))
    try:
        for style in range(128):
            lexer.setPaper(QColor("#10141c"), style)
            lexer.setColor(QColor("#e7e9ee"), style)
            lexer.setFont(font, style)
    except Exception:
        print("error")

    def _set_style(style_attr: str, color: str):
        style = getattr(lexer, style_attr, None)
        if style is not None:
            try:
                lexer.setColor(QColor(color), style)
            except Exception:
                pass

    if isinstance(lexer, QsciLexerPython):
        _set_style("Comment", "#6d6d6d")
        _set_style("CommentBlock", "#6d6d6d")
        _set_style("Number", "#ffca85")
        _set_style("Keyword", "#a277ff")
        _set_style("ClassName", "#82e2ff")
        _set_style("FunctionMethodName", "#82e2ff")
        _set_style("SingleQuotedString", "#61ffca")
        _set_style("DoubleQuotedString", "#61ffca")
        _set_style("TripleSingleQuotedString", "#61ffca")
        _set_style("TripleDoubleQuotedString", "#61ffca")
        _set_style("Decorator", "#a277ff")
        _set_style("Operator", "#edecee")
    elif isinstance(lexer, QsciLexerJavaScript):
        _set_style("Comment", "#6d6d6d")
        _set_style("CommentLine", "#6d6d6d")
        _set_style("CommentDoc", "#6d6d6d")
        _set_style("Number", "#ffca85")
        _set_style("Keyword", "#a277ff")
        _set_style("KeywordSet2", "#a277ff")
        _set_style("ClassName", "#82e2ff")
        _set_style("DoubleQuotedString", "#61ffca")
        _set_style("SingleQuotedString", "#61ffca")
        _set_style("TemplateLiteral", "#61ffca")
        _set_style("Operator", "#edecee")
    elif isinstance(lexer, QsciLexerHTML):
        _set_style("HTMLComment", "#6d6d6d")
        _set_style("HTMLDoubleQuotedString", "#61ffca")
        _set_style("HTMLSingleQuotedString", "#61ffca")
        _set_style("Tag", "#a277ff")
        _set_style("TagEnd", "#a277ff")
        _set_style("Attribute", "#82e2ff")
    elif isinstance(lexer, QsciLexerCSS):
        _set_style("Comment", "#6d6d6d")
        _set_style("Tag", "#a277ff")
        _set_style("ClassSelector", "#82e2ff")
        _set_style("IDSelector", "#82e2ff")
        _set_style("PseudoClass", "#a277ff")
        _set_style("Attribute", "#82e2ff")
        _set_style("Number", "#ffca85")
        _set_style("DoubleQuotedString", "#61ffca")
        _set_style("SingleQuotedString", "#61ffca")
        _set_style("Operator", "#edecee")
    elif isinstance(lexer, QsciLexerJSON):
        _set_style("Property", "#82e2ff")
        _set_style("String", "#61ffca")
        _set_style("Number", "#ffca85")
        _set_style("Operator", "#edecee")
    elif isinstance(lexer, QsciLexerMarkdown):
        _set_style("Header1", "#a277ff")
        _set_style("Header2", "#a277ff")
        _set_style("Header3", "#a277ff")
        _set_style("CodeBlock", "#61ffca")
        _set_style("InlineCode", "#61ffca")
        _set_style("Emphasis", "#82e2ff")
        _set_style("StrongEmphasis", "#82e2ff")
    elif isinstance(lexer, QsciLexerCPP):
        _set_style("Comment", "#6d6d6d")
        _set_style("CommentLine", "#6d6d6d")
        _set_style("Number", "#ffca85")
        _set_style("Keyword", "#a277ff")
        _set_style("String", "#61ffca")
        _set_style("Character", "#61ffca")
        _set_style("Operator", "#edecee")
    # Re-assert editor metrics in case the lexer mutated them.


def _find_in_editor(root, forward: bool, restart: bool = False):
    text = root.find_input.text() if root.find_input else ""
    if not text:
        return

    case_sensitive = bool(root.find_case and root.find_case.isChecked())
    whole_word = False
    regex = False
    wrap = True
    show = True

    if restart:
        start_line = 0 if forward else root.code_editor.lines() - 1
        start_index = 0
    else:
        start_line, start_index = root.code_editor.getCursorPosition()

    found = root.code_editor.findFirst(
        text,
        regex,
        case_sensitive,
        whole_word,
        wrap,
        forward,
        start_line,
        start_index,
        show,
    )
    if not found and wrap:
        start_line = 0 if forward else root.code_editor.lines() - 1
        start_index = 0
        root.code_editor.findFirst(
            text,
            regex,
            case_sensitive,
            whole_word,
            wrap,
            forward,
            start_line,
            start_index,
            show,
        )


def find_next(root, restart: bool = False):
    _find_in_editor(root, True, restart)


def find_prev(root):
    _find_in_editor(root, False, False)


def load_file(root, filename):
    """Load a file into the code editor."""
    
    if not root.flowchart_data:
        return
    
    project_root = root.flowchart_data.get('project_root', '')
    file_path = os.path.join(project_root, filename)
    
    if not os.path.exists(file_path):
        QMessageBox.warning(root, "Error", f"File not found: {filename}")
        return
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        root.code_editor.setText(content)
        _set_editor_lexer(root, filename)
        root.current_file_label.setText(f"Editing: {filename}")
        root.current_file = file_path
    except Exception as e:
        QMessageBox.critical(root, "Error", f"Failed to load file: {e}")


def save_file(root):
    """Save the current file."""
    
    if not root.current_file:
        QMessageBox.warning(root, "No File", "No file is currently open.")
        return
    
    try:
        content = root.code_editor.text()
        
        with open(root.current_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        filename = os.path.basename(root.current_file)
        QMessageBox.information(root, "Success", f"File saved: {filename}")
        
    except Exception as e:
        QMessageBox.critical(root, "Error", f"Failed to save file: {e}")


def on_run_project(root):
    """Run the project and capture output in terminal."""
    
    if not root.flowchart_data:
        QMessageBox.warning(root, "Error", "No project loaded!")
        return
    
    project_root = root.flowchart_data.get('project_root', '')
    
    # Ask user what to run
    main_file, ok = QInputDialog.getText(
        root, 
        "Run Project", 
        "Enter the main file to run (e.g., main.py):",
        text="main.py"
    )
    
    if not ok or not main_file:
        return
    
    main_file_path = os.path.join(project_root, main_file)
    
    if not os.path.exists(main_file_path):
        QMessageBox.warning(root, "Error", f"File not found: {main_file}")
        return
    
    try:
        # Determine how to run the file based on extension
        if main_file.endswith('.py'):
            command = f"python {main_file}"
        elif main_file.endswith('.js'):
            command = f"node {main_file}"
        else:
            QMessageBox.warning(root, "Error", "Unsupported file type!")
            return
        
        # Show command in input (no custom terminal output)
        if root.terminal_input:
            root.terminal_input.setText(command)

        _run_in_terminal(root, command, project_root)
        
    except Exception:
        pass

def toggle_chatbot(root, show):
    """(Deprecated) Kept for compatibility."""
    return




def _run_in_terminal(root, command: str, cwd: str | None):
    if not command:
        return
    # Prevent overlapping runs.
    if hasattr(root, "terminal_process") and root.terminal_process:
        if root.terminal_process.state() != QProcess.ProcessState.NotRunning:
            return

    def append_output(text: str):
        if text:
            root.last_command_output += text
            root.terminal.moveCursor(QTextCursor.MoveOperation.End)
            root.terminal.insertPlainText(text)
            root.terminal.moveCursor(QTextCursor.MoveOperation.End)
            root.terminal.ensureCursorVisible()
            if detect_terminal_error(text):
                set_debug_visible(root.terminal_debug_btn, True)

    def on_finished(exit_code, exit_status):
        if root.terminal_input:
            root.terminal_input.setEnabled(True)
            root.terminal_input.setPlaceholderText("Type command and press Enter...")
        if root.terminal_run_btn:
            root.terminal_run_btn.setEnabled(True)
        if root.stop_process_btn:
            root.stop_process_btn.hide()
        if exit_code and exit_code != 0:
            set_debug_visible(root.terminal_debug_btn, True)
        root.terminal_process = None

    if root.terminal_input:
        root.terminal_input.setEnabled(True)
        root.terminal_input.setPlaceholderText("Process running — type input and press Enter...")
    if root.terminal_run_btn:
        root.terminal_run_btn.setEnabled(False)
    if root.stop_process_btn:
        root.stop_process_btn.show()

    # Echo the command so it is visible in the terminal.
    root.terminal.moveCursor(QTextCursor.MoveOperation.End)
    root.terminal.insertPlainText(command + "\n")
    root.terminal.moveCursor(QTextCursor.MoveOperation.End)
    root.terminal.ensureCursorVisible()
    root.last_command_output = ""

    root.terminal_process = Terminal.start_process(
        command,
        cwd=cwd,
        parent=root,
        on_output=append_output,
        on_finished=on_finished,
    )


def _clear_terminal(root):
    if root.terminal:
        root.terminal.clear()
    root.last_command_output = ""
    set_debug_visible(root.terminal_debug_btn, False)


def _open_debug_from_terminal(root):
    if not root.terminal:
        return
    toggle_chatbot(root, True)
    if root.chatbot_widget:
        output = (root.last_command_output or "").strip()
        root.chatbot_widget.set_mode("debug")
        if output:
            root.chatbot_widget.set_input_text(
                "Please debug this terminal output:\n\n" + output
            )
        else:
            QMessageBox.information(
                root,
                "No Terminal Output",
                "No output was captured after the last command.",
            )


def _stop_terminal_process(root):
    if hasattr(root, "terminal_process") and root.terminal_process:
        Terminal.stop_process(root.terminal_process)


class CodeEditorWidget(QWidget):
    """Main code editor widget wrapper."""
    
    def __init__(self, flowchart_data=None, on_back_to_canvas=None):
        super().__init__()
        self.setObjectName("CodeEditorWidget")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        editor_widget = build_code_editor(flowchart_data, on_back_to_canvas)
        layout.addWidget(editor_widget)
        
        # Store reference to editor widget for cleanup
        self.editor_widget = editor_widget
    
    def closeEvent(self, event):
        """Clean up running processes when closing."""
        # Clean up worker threads
        if hasattr(self.editor_widget, 'ai_worker'):
            try:
                self.editor_widget.ai_worker.terminate()
                self.editor_widget.ai_worker.wait(1000)
            except:
                pass
        
        # Clean up chatbot
        if hasattr(self.editor_widget, 'chatbot_widget') and self.editor_widget.chatbot_widget:
            try:
                self.editor_widget.chatbot_widget.close()
            except:
                pass
        
        super().closeEvent(event)








