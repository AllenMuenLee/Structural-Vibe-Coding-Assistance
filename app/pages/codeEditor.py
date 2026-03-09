import os
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QMessageBox, QInputDialog, QApplication
from PyQt6.QtCore import Qt
import src.utils.Terminal as Terminal
from app.components.code_editor.chatbot_widget import ChatbotWidget
from app.components.code_editor.toolbar import build_toolbar
from app.components.code_editor.content_splitter import build_content_splitter
from app.components.code_editor import file_panel as file_panel_actions
from app.components.code_editor.terminal_panel import build_terminal_panel
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
        on_toggle_chatbot=lambda checked: toggle_chatbot(root, checked),
        open_terminal_fn=Terminal.open_system_terminal,
    )
    main_layout.addWidget(toolbar)

    content_splitter, file_tree, file_model, code_editor, current_file_label, add_btn, delete_btn = build_content_splitter(
        on_file_clicked=lambda filename: load_file(root, filename),
        on_save=lambda: save_file(root),
        on_add_file=lambda: on_add_file(root),
        on_delete_file=lambda: on_delete_file(root),
    )
    main_layout.addWidget(content_splitter, stretch=3)

    terminal_container, terminal, terminal_input, stop_process_btn = build_terminal_panel(
        on_run_command=lambda: execute_terminal_command(root)
    )
    main_layout.addWidget(terminal_container, stretch=1)

    # Store references
    root.file_tree = file_tree
    root.file_model = file_model
    root.code_editor = code_editor
    root.current_file_label = current_file_label
    root.file_add_btn = add_btn
    root.file_delete_btn = delete_btn
    root.terminal = terminal
    root.terminal_input = terminal_input
    root.stop_process_btn = stop_process_btn
    root.content_splitter = content_splitter
    root.flowchart_data = flowchart_data
    root.current_file = None
    root.chatbot_widget = None
    root.chatbot_btn = chatbot_btn
    # Shared terminal module runs commands to completion; no process tracking here.

    terminal_input.returnPressed.connect(lambda: execute_terminal_command(root))
    root.file_tree.selectionModel().currentChanged.connect(
        lambda current, previous: file_panel_actions.update_file_actions(
            root.file_delete_btn, root.file_model, current
        )
    )

    apply_code_editor_theme(root)

    if flowchart_data:
        project_root = flowchart_data.get('project_root', '')
        file_panel_actions.set_project_root(root.file_tree, root.file_model, project_root)

    return root

def execute_terminal_command(root):
    """Execute command typed in terminal input."""
    command = root.terminal_input.text().strip()
    
    if not command:
        return
    
    # Clear input
    root.terminal_input.clear()
    
    # Show command in terminal
    root.terminal.append(f"$ {command}")
    
    # Get project root
    project_root = ""
    if root.flowchart_data:
        project_root = root.flowchart_data.get('project_root', '')
    
    # Check if this is a long-running command (like python app.py, npm start, etc.)
    if Terminal.is_long_running_command(command) and not command.endswith('--help') and not command.endswith('--version'):
        root.terminal.append(
            f"⚠️  This looks like a long-running command (web server, etc.).\n"
            f"   The built-in terminal runs to completion and cannot be stopped.\n"
        )

    def on_line(line: str):
        root.terminal.append(line)
        QApplication.processEvents()

    def on_no_output():
        root.terminal.append("✓ Process completed with no output")

    def on_complete():
        root.terminal.append("\n$ Process finished\n")

    def on_error(exc: Exception):
        root.terminal.append(f"Error: {exc}\n")

    Terminal.run_command_async(
        command,
        cwd=project_root if project_root else None,
        on_output_line=on_line,
        on_no_output=on_no_output,
        on_complete=on_complete,
        on_error=on_error,
    )


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
        
        root.code_editor.setPlainText(content)
        root.current_file_label.setText(f"Editing: {filename}")
        root.current_file = file_path
        root.terminal.append(f"$ Opened {filename}")
        
    except Exception as e:
        QMessageBox.critical(root, "Error", f"Failed to load file: {e}")
        root.terminal.append(f"✗ Error loading {filename}: {e}")


def on_add_file(root):
    if not root.flowchart_data:
        QMessageBox.warning(root, "Error", "No project loaded!")
        return

    project_root = root.flowchart_data.get('project_root', '')
    ok, message, filename = file_panel_actions.add_file(root, project_root)
    if ok and filename:
        root.terminal.append(f"$ Created {filename}")
    elif message and message != "Cancelled.":
        QMessageBox.warning(root, "Error", message)


def on_delete_file(root):
    if not root.flowchart_data:
        QMessageBox.warning(root, "Error", "No project loaded!")
        return

    project_root = root.flowchart_data.get('project_root', '')
    ok, message = file_panel_actions.delete_file(
        root, project_root, root.file_tree, root.file_model
    )
    if ok:
        root.terminal.append("$ Deleted file")
    elif message and message != "Cancelled.":
        QMessageBox.warning(root, "Error", message)


def save_file(root):
    """Save the current file."""
    
    if not root.current_file:
        QMessageBox.warning(root, "No File", "No file is currently open.")
        return
    
    try:
        content = root.code_editor.toPlainText()
        
        with open(root.current_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        filename = os.path.basename(root.current_file)
        root.terminal.append(f"✓ Saved {filename}")
        QMessageBox.information(root, "Success", f"File saved: {filename}")
        
    except Exception as e:
        QMessageBox.critical(root, "Error", f"Failed to save file: {e}")
        root.terminal.append(f"✗ Error saving file: {e}")


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
    
    root.terminal.append(f"\n$ Running {main_file}...\n")
    QApplication.processEvents()
    
    try:
        # Determine how to run the file based on extension
        if main_file.endswith('.py'):
            command = f"python {main_file}"
        elif main_file.endswith('.js'):
            command = f"node {main_file}"
        else:
            QMessageBox.warning(root, "Error", "Unsupported file type!")
            return
        
        # Run command
        output = Terminal.run_command(command, cwd=project_root, timeout=30)
        
        # Display output
        if output:
            root.terminal.append(output)
        else:
            root.terminal.append("✓ Process completed with no output")
        
        root.terminal.append("\n$ Process finished\n")
        
    except Exception as e:
        error_msg = str(e)
        root.terminal.append(f"\n✗ Error: {error_msg}\n")

def toggle_chatbot(root, show):
    """Toggle chatbot sidebar."""
    
    if show:
        # Create and show chatbot
        if not root.chatbot_widget:
            root.chatbot_widget = ChatbotWidget(
                root.flowchart_data.get('project_root', ''),
                root.flowchart_data,
                parent=root
            )
            root.content_splitter.addWidget(root.chatbot_widget)
            # Update stretch factors (must be integers!)
            root.content_splitter.setStretchFactor(2, 2)  # Chat
        root.chatbot_widget.show()
    else:
        # Hide chatbot
        if root.chatbot_widget:
            root.chatbot_widget.hide()


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

