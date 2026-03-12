import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from openai import OpenAI
from dotenv import load_dotenv

import src.utils.FileMng as FileMng
import src.utils.FileEdit as FileEdit
import src.utils.SymbolExt as SymbolExt


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


def _read_file_text(path_value: str) -> str:
    if not path_value or not os.path.exists(path_value):
        return ""
    try:
        with open(path_value, "r", encoding="utf-8") as fh:
            return fh.read()
    except Exception:
        return ""


class CodeEditor:
    def __init__(self, project_root: str):
        self.project_root = os.path.normpath(project_root)
        self.edits: Dict[str, List[List[object]]] = {}
        self.changes: Dict[str, Dict[str, Dict[str, object]]] = {}
        self.edit_log: List[Dict[str, str]] = []

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
        if (prev_des or "") == (curr_des or ""):
            if node_id in self.changes:
                self.changes.pop(node_id, None)
            return
        self.changes.setdefault(node_id, {})
        self.changes[node_id]["description"] = {"prev": prev_des, "curr": curr_des}
        self.changes[node_id]["files"] = {"prev": prev_files or [], "curr": curr_files or []}
        self.changes[node_id]["children"] = {"prev": prev_children or [], "curr": curr_children or []}

    def has_changes(self) -> bool:
        return bool(self.changes)

    def save_and_update(self, text: str) -> None:
        """Save code blocks to files and update ast_map.json."""
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

            self._update_ast_map_for_files([abs_filename])

    def _update_ast_map_for_files(self, files: List[str]) -> None:
        if not files:
            return
        project_id = FileMng.get_project_id_by_root(self.project_root)
        ast_map = FileMng.load_ast_map(project_id) if project_id else None
        if not isinstance(ast_map, dict):
            ast_map = {}

        for path_value in files:
            if not path_value or not os.path.exists(path_value):
                continue
            code = _read_file_text(path_value)
            if code is None:
                continue
            try:
                ast_map[os.path.abspath(path_value)] = SymbolExt.get_ast_map(
                    code, file_path=os.path.abspath(path_value)
                )
            except Exception:
                continue

        if project_id:
            FileMng.save_ast_map(project_id, ast_map)

    def get_file_context(self, file_path: str, code: Optional[str] = None) -> Dict[str, str]:
        """Return file context with full contents."""
        if not file_path:
            return {"file": file_path, "content": "# (no file)"}
        norm_path = _normalize_path(self.project_root, file_path)
        if code is None:
            code = _read_file_text(norm_path)
        if not code:
            return {"file": norm_path, "content": "# (empty or missing file)"}
        return {"file": norm_path, "content": code}

    def generate_edit(
        self,
        changes: Optional[Dict[str, Dict[str, Dict[str, object]]]] = None,
        flowchart_data: Optional[Dict[str, object]] = None,
        progress: Optional[callable] = None,
    ) -> Tuple[str, List[Dict[str, str]]]:
        """Generate edits node-by-node in Debugger.py format and build edit log."""
        changes = changes or self.changes
        edit_outputs: List[str] = []
        self.edit_log = []

        for node_id, change in changes.items():
            if not change:
                continue
            if progress:
                progress(f"Applying edits for node: {node_id}")

            prev_desc = change.get("description", {}).get("prev", "")
            curr_desc = change.get("description", {}).get("curr", "")
            prev_files = change.get("files", {}).get("prev", []) or []
            curr_files = change.get("files", {}).get("curr", []) or []
            prev_children = change.get("children", {}).get("prev", []) or []
            curr_children = change.get("children", {}).get("curr", []) or []

            # If a node was added, generate code via CodeGen for that node.
            if not prev_desc and curr_desc and flowchart_data:
                steps = flowchart_data.get("steps", {}) if isinstance(flowchart_data, dict) else {}
                step_data = steps.get(node_id, {}) if isinstance(steps, dict) else {}
                if isinstance(step_data, dict):
                    try:
                        if progress:
                            progress(f"Generating code for new node: {node_id}")
                        from src.core.CodeGen import CodingAgent
                        agent = CodingAgent(self.project_root)
                        topic = flowchart_data.get("name", "") if isinstance(flowchart_data, dict) else ""
                        raw_code = agent.call_nova(step_data, topic)
                        if raw_code:
                            agent.save_and_update(raw_code)
                        continue
                    except Exception:
                        pass

            related_files = list({*prev_files, *curr_files})
            context_chunks = []
            for f in related_files:
                info = self.get_file_context(f)
                context_chunks.append(
                    f"File: {info['file']}\n```\n{info['content']}\n```"
                )

            context_text = "\n\n".join(context_chunks) if context_chunks else "# (no related files)"
            context_text = _truncate_text(context_text)

            SYSTEM_PROMPT = (
                "You are a code editor. You will receive a node change summary and full file context. "
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

            FILE CONTEXT (FULL CONTENT):
            {context_text}

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
            print(edit_outputs)
            self.edit_log.extend(log_lines)

        if flowchart_data:
            parent_edits = self._generate_parent_edits(flowchart_data, changes, progress)
            if parent_edits:
                edit_outputs.append(parent_edits)

        return "\n".join(edit_outputs).strip(), self.edit_log

    def _generate_parent_edits(
        self,
        flowchart_data: Dict[str, object],
        changes: Dict[str, Dict[str, Dict[str, object]]],
        progress: Optional[callable] = None,
    ) -> str:
        steps = flowchart_data.get("steps", {}) if isinstance(flowchart_data, dict) else {}
        if not isinstance(steps, dict) or not steps:
            return ""

        def _get_children(step_data):
            if not isinstance(step_data, dict):
                return []
            if "chlidren" in step_data:
                return step_data.get("chlidren", []) or []
            return step_data.get("children", []) or []

        parents = {sid: [] for sid in steps.keys()}
        for sid, data in steps.items():
            for cid in _get_children(data):
                if cid in parents:
                    parents[cid].append(sid)

        def collect_parents(start_id):
            out = []
            stack = list(parents.get(start_id, []))
            seen = set()
            while stack:
                pid = stack.pop()
                if pid in seen:
                    continue
                seen.add(pid)
                out.append(pid)
                stack.extend(parents.get(pid, []))
            return out

        edits_out: List[str] = []
        for node_id, change in changes.items():
            if not change:
                continue
            if progress:
                progress(f"Applying parent edits for node: {node_id}")
            prev_files = change.get("files", {}).get("prev", []) or []
            curr_files = change.get("files", {}).get("curr", []) or []
            edited_files = sorted(set(curr_files) | set(prev_files))
            prev_desc = change.get("description", {}).get("prev", "")
            curr_desc = change.get("description", {}).get("curr", "")

            for parent_id in collect_parents(node_id):
                parent = steps.get(parent_id, {})
                parent_files = parent.get("filenames", []) if isinstance(parent, dict) else []
                if not parent_files:
                    continue

                context_chunks = []
                for f in parent_files:
                    info = self.get_file_context(f)
                    context_chunks.append(
                        f"File: {info['file']}\n```\n{info['content']}\n```"
                    )
                context_text = "\n\n".join(context_chunks) if context_chunks else "# (no related files)"
                context_text = _truncate_text(context_text)

                SYSTEM_PROMPT = (
                    "You are a code editor. A child node changed and edited/added files. "
                    "Update the parent node files if needed. Return only Debugger.py edits."
                )

                prompt = f"""
                Parent Node ID: {parent_id}
                Child Node ID: {node_id}

                Child Description Change:
                PREVIOUS: {prev_desc}
                CURRENT: {curr_desc}

                Edited or Referenced Files:
                {edited_files}

                Parent File Context:
                {context_text}

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
                text = response.choices[0].message.content or ""
                edits_text, _log_lines = self._split_edits_and_log(text)
                if edits_text:
                    edits_out.append(edits_text)

        return "\n".join(edits_out).strip()

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

    def apply_edits(self, edit_string: str) -> None:
        """Apply edits to files using FileEdit.apply_edits."""
        edits = self.string_to_edit(edit_string or "")
        for i in edits.keys():
            print(i)
        FileEdit.apply_edits(edits)
        if edits:
            self._update_ast_map_for_files(list(edits.keys()))

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
