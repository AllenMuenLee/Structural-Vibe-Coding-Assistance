import os
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from openai import OpenAI
from dotenv import load_dotenv

import src.utils.FileMng as FileMng
import src.utils.SymbolExt as SymbolExt
from src.utils.NetUtils import extract_retry_seconds, is_rate_limit_error


load_dotenv()

client = OpenAI(
    api_key=os.getenv("NOVA_API_KEY"),
    base_url="https://api.nova.amazon.com/v1",
    default_headers={"Accept-Encoding": "gzip, deflate"},  # Disable zstd
    timeout=90.0
)


LOG_LINE_REGEX = re.compile(r"^\[LOG\]\s+(.+?)\s+-\s+(.+?)\s*->\s*(.+?)\s*:\s*(.+)$")
FILE_BLOCK_REGEX = re.compile(r"\[([^\]]+)\]:?\s*```(?:[a-zA-Z0-9_+-]*)\n(.*?)\n```", re.DOTALL)


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
        prev_flowchart: Dict[str, object],
        curr_flowchart: Dict[str, object],
    ) -> None:
        prev_steps = prev_flowchart.get("steps", {}) if isinstance(prev_flowchart, dict) else {}
        curr_steps = curr_flowchart.get("steps", {}) if isinstance(curr_flowchart, dict) else {}
        if not isinstance(prev_steps, dict):
            prev_steps = {}
        if not isinstance(curr_steps, dict):
            curr_steps = {}

        def _get_children(step_data):
            if not isinstance(step_data, dict):
                return []
            if "chlidren" in step_data:
                return step_data.get("chlidren", []) or []
            return step_data.get("children", []) or []

        all_ids = set(prev_steps.keys()) | set(curr_steps.keys())
        for node_id in all_ids:
            prev = prev_steps.get(node_id, {}) if isinstance(prev_steps.get(node_id, {}), dict) else {}
            curr = curr_steps.get(node_id, {}) if isinstance(curr_steps.get(node_id, {}), dict) else {}
            prev_desc = prev.get("description", "") if isinstance(prev, dict) else ""
            curr_desc = curr.get("description", "") if isinstance(curr, dict) else ""
            prev_files = prev.get("filenames", []) if isinstance(prev, dict) else []
            curr_files = curr.get("filenames", []) if isinstance(curr, dict) else []
            prev_children = _get_children(prev)
            curr_children = _get_children(curr)
            prev_cmds = prev.get("command", []) if isinstance(prev, dict) else []
            curr_cmds = curr.get("command", []) if isinstance(curr, dict) else []
            prev_imports = prev.get("files_to_import", []) if isinstance(prev, dict) else []
            curr_imports = curr.get("files_to_import", []) if isinstance(curr, dict) else []

            def _normalize_list(value):
                if value is None:
                    return []
                if isinstance(value, list):
                    return [str(v) for v in value]
                return [str(value)]

            prev_cmds = _normalize_list(prev_cmds)
            curr_cmds = _normalize_list(curr_cmds)
            prev_imports = _normalize_list(prev_imports)
            curr_imports = _normalize_list(curr_imports)

            prev_desc_full = (
                f"{prev_desc}\n\nCOMMANDS:\n" + "\n".join(prev_cmds) +
                "\n\nFILES_TO_IMPORT:\n" + "\n".join(prev_imports)
            )
            curr_desc_full = (
                f"{curr_desc}\n\nCOMMANDS:\n" + "\n".join(curr_cmds) +
                "\n\nFILES_TO_IMPORT:\n" + "\n".join(curr_imports)
            )

            if (
                prev_desc_full == curr_desc_full
                and prev_files == curr_files
                and prev_children == curr_children
            ):
                if node_id in self.changes:
                    self.changes.pop(node_id, None)
                continue

            self.changes.setdefault(node_id, {})
            self.changes[node_id]["description"] = {"prev": prev_desc_full, "curr": curr_desc_full}
            self.changes[node_id]["files"] = {"prev": prev_files or [], "curr": curr_files or []}
            self.changes[node_id]["children"] = {"prev": prev_children or [], "curr": curr_children or []}

    def add_node_changes(
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

    def update_changes_from_flowchart(self, prev_flowchart: Dict[str, object], curr_flowchart: Dict[str, object]) -> None:
        prev_steps = prev_flowchart.get("steps", {}) if isinstance(prev_flowchart, dict) else {}
        curr_steps = curr_flowchart.get("steps", {}) if isinstance(curr_flowchart, dict) else {}
        if not isinstance(prev_steps, dict):
            prev_steps = {}
        if not isinstance(curr_steps, dict):
            curr_steps = {}

        def _get_children(step_data):
            if not isinstance(step_data, dict):
                return []
            if "chlidren" in step_data:
                return step_data.get("chlidren", []) or []
            return step_data.get("children", []) or []

        all_ids = set(prev_steps.keys()) | set(curr_steps.keys())
        for sid in all_ids:
            prev = prev_steps.get(sid, {}) if isinstance(prev_steps.get(sid, {}), dict) else {}
            curr = curr_steps.get(sid, {}) if isinstance(curr_steps.get(sid, {}), dict) else {}
            prev_desc = prev.get("description", "") if isinstance(prev, dict) else ""
            curr_desc = curr.get("description", "") if isinstance(curr, dict) else ""
            prev_files = prev.get("filenames", []) if isinstance(prev, dict) else []
            curr_files = curr.get("filenames", []) if isinstance(curr, dict) else []
            prev_children = _get_children(prev)
            curr_children = _get_children(curr)

            if prev_desc == curr_desc and prev_files == curr_files and prev_children == curr_children:
                if sid in self.changes:
                    self.changes.pop(sid, None)
                continue

            self.changes.setdefault(sid, {})
            self.changes[sid]["description"] = {"prev": prev_desc, "curr": curr_desc}
            self.changes[sid]["files"] = {"prev": prev_files or [], "curr": curr_files or []}
            self.changes[sid]["children"] = {"prev": prev_children or [], "curr": curr_children or []}

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
        modified_files: set[str] = set()

        print(changes)

        ordered_changes = self._order_changes_children_first(changes, flowchart_data)
        for node_id, change in ordered_changes:
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
            Here is the comparsion of the changed nodes. please generate edits based on this change.
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

            if the file is currently empty or missing, please return your generated code from scratch.
            Please return the full updated file contents for every affected file.
            Use this exact format:

            [FILES]
            [filepath]
            ```
            full file content
            ```
            [filepath]
            ```
            full file content
            ```
            ...

            [LOG]
            [LOG] filepath - previous_name -> current_name: functionality, output format
            ...

            You need to return bracket with FIELS, filepath (like [C:\\Users\\project.py]), and LOG)
            """

            response = None
            for attempt in range(2):
                try:
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
                    break
                except Exception as exc:
                    if is_rate_limit_error(exc) and attempt < 1:
                        retry_seconds = extract_retry_seconds(str(exc))
                        if progress:
                            progress(
                                f"Request per minute exceeded. Retrying in {retry_seconds} seconds..."
                            )
                        time.sleep(retry_seconds)
                        continue
                    raise
            text = response.choices[0].message.content or ""
            edits_text, log_lines = self._split_edits_and_log(text)
            edit_outputs.append(edits_text)
            print(response.choices[0])
            self.edit_log.extend(log_lines)
            for filename, _code in self._parse_file_blocks(edits_text or ""):
                abs_filename = _normalize_path(self.project_root, filename)
                if abs_filename:
                    modified_files.add(abs_filename)

        if flowchart_data:
            parent_edits = self._generate_parent_edits(
                flowchart_data,
                changes,
                modified_files,
                progress,
            )
            if parent_edits:
                edit_outputs.append(parent_edits)
        
        return "\n".join(edit_outputs).strip(), self.edit_log

    def _order_changes_children_first(
        self,
        changes: Dict[str, Dict[str, Dict[str, object]]],
        flowchart_data: Optional[Dict[str, object]] = None,
    ) -> List[tuple]:
        if not changes:
            return []
        steps = (
            flowchart_data.get("steps", {})
            if isinstance(flowchart_data, dict)
            else {}
        )
        if not isinstance(steps, dict) or not steps:
            return list(changes.items())

        def _get_children(step_data):
            if not isinstance(step_data, dict):
                return []
            if "chlidren" in step_data:
                return step_data.get("chlidren", []) or []
            return step_data.get("children", []) or []

        visited = set()
        ordered = []

        def visit(node_id):
            if node_id in visited:
                return
            visited.add(node_id)
            step = steps.get(node_id, {})
            for child_id in _get_children(step):
                if child_id in changes:
                    visit(child_id)
            if node_id in changes:
                ordered.append((node_id, changes[node_id]))

        for node_id in changes.keys():
            visit(node_id)

        return ordered

    def _generate_parent_edits(
        self,
        flowchart_data: Dict[str, object],
        changes: Dict[str, Dict[str, Dict[str, object]]],
        modified_files: Optional[set] = None,
        progress: Optional[callable] = None,
    ) -> str:
        steps = flowchart_data.get("steps", {}) if isinstance(flowchart_data, dict) else {}
        if not isinstance(steps, dict) or not steps:
            return ""
        modified_files = modified_files or set()

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
        seen_parents: set[str] = set()
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
                if parent_id in seen_parents:
                    continue
                parent = steps.get(parent_id, {})
                parent_files = parent.get("filenames", []) if isinstance(parent, dict) else []
                if not parent_files:
                    continue
                skip_parent = False
                for f in parent_files:
                    abs_parent = _normalize_path(self.project_root, f)
                    if abs_parent and abs_parent in modified_files:
                        skip_parent = True
                        break
                if skip_parent:
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
                    "Update the parent node files if needed. Return full file contents."
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

                Return output in this format:

                [FILES]
                [filepath]
                ```
                full file content
                ```
                ...

                You need to return the bracket with the FILES and filepath
                """

                response = None
                for attempt in range(2):
                    try:
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
                        break
                    except Exception as exc:
                        if is_rate_limit_error(exc) and attempt < 1:
                            retry_seconds = extract_retry_seconds(str(exc))
                            if progress:
                                progress(
                                    f"Request per minute exceeded. Retrying in {retry_seconds} seconds..."
                                )
                            time.sleep(retry_seconds)
                            continue
                        raise
                text = response.choices[0].message.content or ""
                edits_text, _log_lines = self._split_edits_and_log(text)
                if edits_text:
                    edits_out.append(edits_text)
                    seen_parents.add(parent_id)
                    for filename, _code in self._parse_file_blocks(edits_text or ""):
                        abs_filename = _normalize_path(self.project_root, filename)
                        if abs_filename:
                            modified_files.add(abs_filename)

        return "\n".join(edits_out).strip()

    def apply_edits(self, edit_string: str) -> None:
        """Apply full-file outputs to disk."""
        files = self._parse_file_blocks(edit_string or "")
        if not files:
            return
        updated_files: List[str] = []
        for filename, code in files:
            abs_filename = _normalize_path(self.project_root, filename)
            if not abs_filename:
                continue
            norm_filename = Path(abs_filename)
            norm_filename.parent.mkdir(parents=True, exist_ok=True)
            with open(abs_filename, "w", encoding="utf-8") as f:
                f.write(code)
            updated_files.append(abs_filename)
        if updated_files:
            self._update_ast_map_for_files(updated_files)

    def _split_edits_and_log(self, text: str) -> Tuple[str, List[Dict[str, str]]]:
        edits_lines: List[str] = []
        log_entries: List[Dict[str, str]] = []
        in_log = False
        for raw in text.splitlines():
            line = raw.strip()
            if line in ("[EDITS]", "[FILES]"):
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

    def _parse_file_blocks(self, text: str) -> List[Tuple[str, str]]:
        files: List[Tuple[str, str]] = []
        if not text:
            return files
        for filename, code in FILE_BLOCK_REGEX.findall(text):
            clean_name = (filename or "").strip()
            if not clean_name:
                continue
            files.append((clean_name, code.rstrip("\n")))
        return files
