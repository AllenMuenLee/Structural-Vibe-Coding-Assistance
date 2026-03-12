import os

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot


class AIChatWorker(QObject):
    """Worker object for AI chat responses (runs inside a QThread)."""

    finished = pyqtSignal(str)

    def __init__(self, project_root, flowchart_data, user_message, conversation_history, mode="general"):
        super().__init__()
        self.project_root = project_root
        self.flowchart_data = flowchart_data
        self.user_message = user_message
        self.conversation_history = conversation_history
        self.mode = mode
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True

    @pyqtSlot()
    def run(self):
        try:
            if self._stop_requested:
                return
            from openai import OpenAI
            from dotenv import load_dotenv
            import src.utils.SymbolExt as SymbolExt
            import src.utils.FileMng as FileMng

            load_dotenv()

            client = OpenAI(
                api_key=os.getenv("NOVA_API_KEY"),
                base_url="https://api.nova.amazon.com/v1",
                timeout=60.0,
            )

            ast_map = {}
            project_id = FileMng.get_project_id_by_root(self.project_root)
            if project_id:
                cached = FileMng.load_ast_map(project_id)
                if cached:
                    ast_map = {os.path.abspath(k): v for k, v in cached.items()}
            if not ast_map:
                ast_map = SymbolExt.initialize_ast_map(self.project_root, ast_map)
                if project_id:
                    FileMng.save_ast_map(project_id, ast_map)

            if self._stop_requested:
                return

            if self.mode == "debug":
                from src.core.Debugger import debugger
                from src.utils.CacheMng import load_cache, save_cache
                dbg = debugger(self.project_root)

                cache = load_cache()
                pending = cache.get("debug_parent_pending")
                if pending:
                    user_answer = (self.user_message or "").strip().lower()
                    if user_answer in ("yes", "y", "sure", "ok", "okay"):
                        flowchart_data = self.flowchart_data or {}
                        if not flowchart_data:
                            cache["debug_parent_pending"] = None
                            save_cache(cache)
                            self.finished.emit("No flowchart data available for parent updates.")
                            return
                        parent_ids = pending.get("parent_ids", [])
                        child_summary = pending.get("child_summary", "")
                        edits = dbg.generate_parent_updates(flowchart_data, parent_ids, child_summary)
                        edits_text = (edits or "").strip()
                        if edits_text:
                            try:
                                dbg.save_generated_files(edits)
                            except Exception as exc:
                                edits_text += f"\n\n(Note: failed to apply edits automatically: {exc})"
                        response = (
                            "Parent update result:\n"
                            f"{edits_text or '(no parent updates generated)'}"
                        )
                        cache["debug_parent_pending"] = None
                        save_cache(cache)
                        self.finished.emit(response)
                        return
                    if user_answer in ("no", "n", "nope"):
                        cache["debug_parent_pending"] = None
                        save_cache(cache)
                        self.finished.emit("No parent updates generated.")
                        return

                extracted = dbg.extract_error(self.user_message, ast_map)
                dbg.parse_error_files(extracted)
                edits = dbg.generate_edits(self.user_message)
                edits_text = (edits or "").strip()
                response = (
                    "Extracted files:\n"
                    f"{extracted}\n\n"
                    "Proposed edits:\n"
                    f"{edits_text or '(no edits generated)'}"
                )
                if edits_text:
                    try:
                        dbg.save_generated_files(edits)
                    except Exception as exc:
                        response += f"\n\n(Note: failed to apply edits automatically: {exc})"

                # Ask about parent nodes if flowchart data is available.
                parent_prompt = ""
                if self.flowchart_data and edits_text:
                    impacted_files = [f for f, _c in dbg._parse_file_blocks(edits_text)]
                    parent_ids, child_summary = dbg.find_parent_nodes(self.flowchart_data, impacted_files)
                    if parent_ids:
                        parent_prompt = (
                            "\n\nParent nodes that may need updates:\n"
                            + "\n".join(f"- {pid}" for pid in parent_ids)
                            + "\n\nChange summary:\n"
                            + child_summary
                            + "\n\nDo you want to update parent nodes? Reply Yes or No."
                        )
                        cache["debug_parent_pending"] = {
                            "parent_ids": parent_ids,
                            "child_summary": child_summary,
                        }
                        save_cache(cache)

                if parent_prompt:
                    response += parent_prompt
                self.finished.emit(response)
                return

            context_lines = []
            for file_path, symbols in ast_map.items():
                rel_path = os.path.relpath(file_path, self.project_root)
                context_lines.append(f"\n## File: {rel_path}")

                if symbols:
                    for symbol in symbols[:10]:
                        context_lines.append(
                            f"- [{symbol.get('kind', 'symbol')}] "
                            f"{symbol.get('name', '?')} "
                            f"(line {symbol.get('line', '?')})"
                        )

            context = "\n".join(context_lines)

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

            messages.extend(self.conversation_history)
            messages.append({"role": "user", "content": self.user_message})

            max_retries = 2
            for attempt in range(max_retries):
                if self._stop_requested:
                    return
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
                        import time
                        time.sleep(1)
                        continue
                    raise api_error

        except Exception as e:
            import traceback
            import re
            from src.utils.CacheMng import load_cache, save_cache

            traceback.print_exc()
            error_msg = str(e)
            lower_msg = error_msg.lower()

            def _extract_retry_after(text: str) -> int:
                if not text:
                    return 0
                match = re.search(r"retry[- ]after[: ]+(\d+)", text, re.IGNORECASE)
                if match:
                    try:
                        return int(match.group(1))
                    except Exception:
                        return 0
                match = re.search(r"retry in (\d+) seconds", text, re.IGNORECASE)
                if match:
                    try:
                        return int(match.group(1))
                    except Exception:
                        return 0
                return 0

            if "DecodingError" in error_msg or "decompressobj" in error_msg:
                self.finished.emit(
                    "Connection issue with AI service. This is usually temporary.\n\n"
                    "Try again in a moment, or ask a simpler question."
                )
            elif "daily limit" in lower_msg or "quota" in lower_msg:
                cache = load_cache()
                cache["api_daily_limit_exceeded"] = True
                cache["api_daily_limit_message"] = error_msg
                save_cache(cache)
                self.finished.emit(
                    "Daily limit exceeded for your API key. "
                    "Please update the key in Settings."
                )
            elif "429" in lower_msg or "rate limit" in lower_msg:
                retry_seconds = _extract_retry_after(error_msg) or 10
                self.finished.emit(f"Rate limit exceeded. Retry in {retry_seconds} seconds.")
            elif "timeout" in error_msg.lower():
                self.finished.emit(
                    "Request timed out. The AI service is taking too long to respond.\n\n"
                    "Try a shorter question."
                )
            else:
                self.finished.emit(f"Error: {error_msg}")
