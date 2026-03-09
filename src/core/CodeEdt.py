import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from openai import OpenAI
from dotenv import load_dotenv

import src.utils.SymbolExt as SymbolExt
import src.utils.FileMng as FileMng


load_dotenv()

client = OpenAI(
    api_key=os.getenv("NOVA_API_KEY"),
    base_url="https://api.nova.amazon.com/v1",
)


EDIT_LINE_REGEX = re.compile(r"\[(Edit|Insert|Delete)\] (.+?) - #(\d+)")
LOG_LINE_REGEX = re.compile(r"^\[LOG\]\s+(.+?)\s+-\s+(.+?)\s*->\s*(.+?)\s*:\s*(.+)$")


def _normalize_path(project_root: str, path_value: str) -> str:
    if not path_value:
        return path_value
    if os.path.isabs(path_value):
        return os.path.normpath(path_value)
    return os.path.normpath(os.path.join(project_root, path_value))


def _truncate_text(text: str, max_chars: int = 12000) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n# (truncated)"


class CodeEditor:
    def __init__(self, project_root: str):
        self.project_root = os.path.normpath(project_root)
        self.edits: Dict[str, List[List[object]]] = {}
        self.changes: Dict[str, Dict[str, Dict[str, object]]] = {}
        self.edit_log: List[Dict[str, str]] = []
        self.ast_map: Dict[str, List[dict]] = {}

        if not self._load_ast_map():
            self.ast_map = SymbolExt.initialize_ast_map(self.project_root, self.ast_map)
            self._save_ast_map()

    def add_changes(
        self,
        node_id: str,
        prev_des: str,
        curr_des: str,
        prev_files: List[str],
        curr_files: List[str],
        prev_children: List[str],
        curr_children: List[str],
    ) -> None:
        self.changes.setdefault(node_id, {})
        self.changes[node_id]["description"] = {"prev": prev_des, "curr": curr_des}
        self.changes[node_id]["files"] = {"prev": prev_files or [], "curr": curr_files or []}
        self.changes[node_id]["children"] = {"prev": prev_children or [], "curr": curr_children or []}

    def has_changes(self) -> bool:
        return bool(self.changes)

    def _save_ast_map(self) -> None:
        ast_map_path = os.path.join(self.project_root, "ast_map.json")
        normalized = {os.path.abspath(k): v for k, v in self.ast_map.items()}
        FileMng.save_json(normalized, ast_map_path)

    def _load_ast_map(self) -> bool:
        ast_map_path = os.path.join(self.project_root, "ast_map.json")
        if not os.path.exists(ast_map_path):
            return False
        try:
            raw_map = FileMng.load_json(ast_map_path)
            self.ast_map = {os.path.abspath(k): v for k, v in raw_map.items()}
            return True
        except Exception:
            return False

    def save_and_update(self, text: str) -> None:
        """Save code blocks to files and update AST map (same as CodeGen)."""
        pattern = r"\[([^\]]+)\]:?\s*```(?:[a-zA-Z0-9_+-]*)\n(.*?)\n```"
        matches = re.findall(pattern, text, re.DOTALL)

        for filename, code in matches:
            abs_filename = _normalize_path(self.project_root, filename)
            norm_filename = Path(abs_filename)
            norm_filename.parent.mkdir(parents=True, exist_ok=True)

            if os.path.exists(abs_filename):
                with open(abs_filename, "r", encoding="utf-8") as f:
                    existing_code = f.read()
                if code.strip() in existing_code:
                    continue
                with open(abs_filename, "a", encoding="utf-8") as f:
                    f.write("\n\n")
                    f.write(code)
            else:
                with open(abs_filename, "w", encoding="utf-8") as f:
                    f.write(code)

            with open(abs_filename, "r", encoding="utf-8") as f:
                full_code = f.read()

            self.ast_map[str(norm_filename)] = SymbolExt.get_ast_map(
                full_code, file_path=str(norm_filename)
            )
            self._save_ast_map()

    def get_ast(self, file_path: str, code: Optional[str] = None) -> Dict[str, str]:
        """Return full AST tree for a file (not just tags)."""
        if not file_path:
            return {"file": file_path, "ast": "# (no file)"}
        norm_path = _normalize_path(self.project_root, file_path)
        if code is None and os.path.exists(norm_path):
            try:
                with open(norm_path, "r", encoding="utf-8") as fh:
                    code = fh.read()
            except Exception:
                code = None
        if not code:
            return {"file": norm_path, "ast": "# (empty or missing file)"}
        ast_tree = SymbolExt.get_ast_tree(code, norm_path)
        return {"file": norm_path, "ast": ast_tree}

    def generate_edit(self, changes: Optional[Dict[str, Dict[str, Dict[str, object]]]] = None) -> Tuple[str, List[Dict[str, str]]]:
        """Generate edits node-by-node in Debugger.py format and build edit log."""
        changes = changes or self.changes
        edit_outputs: List[str] = []
        self.edit_log = []

        for node_id, change in changes.items():
            if not change:
                continue

            prev_desc = change.get("description", {}).get("prev", "")
            curr_desc = change.get("description", {}).get("curr", "")
            prev_files = change.get("files", {}).get("prev", []) or []
            curr_files = change.get("files", {}).get("curr", []) or []
            prev_children = change.get("children", {}).get("prev", []) or []
            curr_children = change.get("children", {}).get("curr", []) or []

            related_files = list({*prev_files, *curr_files})
            ast_chunks = []
            for f in related_files:
                ast_info = self.get_ast(f)
                ast_chunks.append(f"File: {ast_info['file']}\n{ast_info['ast']}")

            context_ast = "\n\n".join(ast_chunks) if ast_chunks else "# (no related files)"
            context_ast = _truncate_text(context_ast)

            SYSTEM_PROMPT = (
                "You are a code editor. You will receive a node change summary and full AST context. "
                "Generate edits in the exact Debugger.py format and also produce a rename/log summary."
            )

            prompt = f"""
            Node ID: {node_id}

            PREVIOUS DESCRIPTION:
            {prev_desc}

            CURRENT DESCRIPTION:
            {curr_desc}

            PREVIOUS FILES:
            {prev_files}

            CURRENT FILES:
            {curr_files}

            PREVIOUS CHILDREN:
            {prev_children}

            CURRENT CHILDREN:
            {curr_children}

            AST CONTEXT (FULL TREE):
            {context_ast}

            Return output with two sections:

            [EDITS]
            [Edit] filepath - #line number
            ```
            Code
            ```
            [Insert] filepath - #line number
            ```
            Code
            ```
            [Delete] filepath - #line number

            [LOG]
            [LOG] filepath - previous_name -> current_name: functionality, output format
            ...
            """

            response = client.chat.completions.create(
                model="nova-pro-v1",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=2000,
                stream=False,
            )
            text = response.choices[0].message.content or ""
            edits_text, log_lines = self._split_edits_and_log(text)
            edit_outputs.append(edits_text)
            self.edit_log.extend(log_lines)

        return "\n".join(edit_outputs).strip(), self.edit_log

    def adapt_changes(self, files: Optional[List[str]] = None) -> str:
        """Use edit log + AST to generate follow-up edits across files."""
        target_files = files or self._collect_project_files()
        if not target_files:
            return ""

        edits_out: List[str] = []
        for file_path in target_files:
            ast_info = self.get_ast(file_path)
            related_logs = [e for e in self.edit_log if e.get("file") == file_path]
            log_text = "\n".join(
                f"[LOG] {e['file']} - {e['prev']} -> {e['curr']}: {e['detail']}"
                for e in related_logs
            )
            log_text = log_text or "# (no log entries for this file)"

            SYSTEM_PROMPT = (
                "You are a code editor. Using the AST and the edit log, "
                "generate follow-up edits in Debugger.py format."
            )

            prompt = f"""
            FILE: {ast_info['file']}
            AST:
            {_truncate_text(ast_info['ast'])}

            EDIT LOG:
            {log_text}

            Return edits in this format:
            [Edit] filepath - #line number
            ```
            Code
            ```
            [Insert] filepath - #line number
            ```
            Code
            ```
            [Delete] filepath - #line number
            """

            response = client.chat.completions.create(
                model="nova-pro-v1",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=2000,
                stream=False,
            )
            edits_out.append(response.choices[0].message.content or "")

        return "\n".join(edits_out).strip()

    def _collect_project_files(self) -> List[str]:
        exts = {".py", ".js", ".jsx", ".ts", ".tsx"}
        collected: List[str] = []
        for dirpath, _dirnames, filenames in os.walk(self.project_root):
            for filename in filenames:
                if os.path.splitext(filename)[1].lower() in exts:
                    collected.append(os.path.join(dirpath, filename))
        return sorted(set(collected))

    def string_to_edit(self, edit_string: str) -> Dict[str, List[List[object]]]:
        """Parse edit string to internal edits dict."""
        self.edits = {}
        lines = edit_string.splitlines()
        if lines and lines[0].strip() == "```":
            lines = lines[1:]

        in_code = False
        curr_code: List[str] = []
        curr_file = ""
        for raw in lines:
            line = raw.rstrip()
            if not in_code:
                match = EDIT_LINE_REGEX.match(line.strip())
                if match:
                    action = match.group(1)
                    file_path = match.group(2)
                    line_number = int(match.group(3))
                    curr_file = file_path
                    self.edits.setdefault(file_path, []).append([action, line_number, ""])
                    continue
            if line.strip() == "```":
                in_code = not in_code
                if not in_code and curr_code and curr_file:
                    self.edits[curr_file][-1][2] = "\n".join(curr_code)
                    curr_code = []
                continue
            if in_code:
                curr_code.append(line)

        return self.edits

    def _split_edits_and_log(self, text: str) -> Tuple[str, List[Dict[str, str]]]:
        edits_lines: List[str] = []
        log_entries: List[Dict[str, str]] = []
        in_log = False
        for raw in text.splitlines():
            line = raw.strip()
            if line == "[EDITS]":
                in_log = False
                continue
            if line == "[LOG]":
                in_log = True
                continue
            if in_log:
                match = LOG_LINE_REGEX.match(line)
                if match:
                    log_entries.append({
                        "file": match.group(1).strip(),
                        "prev": match.group(2).strip(),
                        "curr": match.group(3).strip(),
                        "detail": match.group(4).strip(),
                    })
                continue
            edits_lines.append(raw)

        return "\n".join(edits_lines).strip(), log_entries
