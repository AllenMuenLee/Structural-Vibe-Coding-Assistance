import os

from PyQt6.QtCore import QThread, pyqtSignal


class AIChatWorker(QThread):
    """Worker thread for AI chat responses."""

    finished = pyqtSignal(str)

    def __init__(self, project_root, flowchart_data, user_message, conversation_history, mode="general"):
        super().__init__()
        self.project_root = project_root
        self.flowchart_data = flowchart_data
        self.user_message = user_message
        self.conversation_history = conversation_history
        self.mode = mode

    def run(self):
        try:
            from openai import OpenAI
            from dotenv import load_dotenv
            import src.utils.SymbolExt as SymbolExt

            load_dotenv()

            # Create client with timeout settings
            client = OpenAI(
                api_key=os.getenv("NOVA_API_KEY"),
                base_url="https://api.nova.amazon.com/v1",
                timeout=60.0,  # 60 second timeout
            )

            # Get project context
            ast_map = {}
            ast_map = SymbolExt.initialize_ast_map(self.project_root, ast_map)

            if self.mode == "debug":
                from src.core.Debugger import debugger
                dbg = debugger(self.project_root)
                extracted = dbg.extract_error(self.user_message, ast_map)
                dbg.parse_error_files(extracted)
                edits = dbg.generate_edits(self.user_message)
                dbg.string_to_edit(edits)
                dbg.fix()
                response = (
                    "Extracted files:\n"
                    f"{extracted}\n\n"
                    "Proposed edits:\n"
                    f"{edits}"
                )
                self.finished.emit(response)
                return

            # Build context from project files
            context_lines = []
            for file_path, symbols in ast_map.items():
                rel_path = os.path.relpath(file_path, self.project_root)
                context_lines.append(f"\n## File: {rel_path}")

                if symbols:
                    for symbol in symbols[:10]:  # Limit to first 10 symbols per file
                        context_lines.append(
                            f"- [{symbol.get('kind', 'symbol')}] "
                            f"{symbol.get('name', '?')} "
                            f"(line {symbol.get('line', '?')})"
                        )

            context = "\n".join(context_lines)

            # Build conversation with context
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a helpful coding assistant. You have access to the "
                        "user's project structure and code.\n\n"
                        "PROJECT CONTEXT:\n"
                        f"{context}\n\n"
                        "FLOWCHART:\n"
                        f"Name: {self.flowchart_data.get('name', 'Unknown')}\n"
                        f"Framework: {self.flowchart_data.get('framework', 'Unknown')}\n"
                        f"Steps: {len(self.flowchart_data.get('steps', {}))}\n\n"
                        "Answer the user's questions about their code, help debug issues, "
                        "and provide suggestions.\n"
                        "Be concise and helpful. Reference specific files and functions when relevant."
                    ),
                }
            ]

            # Add conversation history
            messages.extend(self.conversation_history)

            # Add current user message
            messages.append({"role": "user", "content": self.user_message})

            # Call AI with retry logic
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    response = client.chat.completions.create(
                        model="nova-pro-v1",
                        messages=messages,
                        temperature=0.7,
                        max_tokens=1000,
                    )

                    ai_response = response.choices[0].message.content
                    self.finished.emit(ai_response)
                    return

                except Exception as api_error:
                    if attempt < max_retries - 1:
                        # Wait and retry
                        import time

                        time.sleep(1)
                        continue
                    raise api_error

        except Exception as e:
            import traceback

            traceback.print_exc()
            error_msg = str(e)

            # Provide helpful error message
            if "DecodingError" in error_msg or "decompressobj" in error_msg:
                self.finished.emit(
                    "Connection issue with AI service. This is usually temporary.\n\n"
                    "Try again in a moment, or ask a simpler question."
                )
            elif "timeout" in error_msg.lower():
                self.finished.emit(
                    "Request timed out. The AI service is taking too long to respond.\n\n"
                    "Try a shorter question."
                )
            else:
                self.finished.emit(f"Error: {error_msg}")
