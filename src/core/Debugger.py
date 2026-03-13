import json
import os
from openai import OpenAI
from dotenv import load_dotenv
import re
from pathlib import Path

load_dotenv()

client = OpenAI(
    api_key=os.getenv("NOVA_API_KEY"),
    base_url="https://api.nova.amazon.com/v1",
    default_headers={"Accept-Encoding": "gzip, deflate"},  # Disable zstd
    timeout=90.0
)

class debugger:
    def __init__(self, project_name):
        self.project_name = project_name
        self.error_files = {}

    def extract_error(self, user_input, ast_tag):
        """
        Use Nova to read the user message + AST tags and list all likely files to inspect.
        Returns the same format as extract_error_nova:
        filepath - #line number
        ...
        """
        SYSTEM_PROMPT = (
            "You are a debugger extractor. Given a issue description, which can be a terminal message or user description, and AST tags, "
            "identify all likely files to inspect. Return ONLY the file paths and line "
            "numbers in the specified format."
        )
        prompt = f"""
        Error description/message:
        {user_input}

        AST tags (by file):
        {json.dumps(ast_tag, indent=2)}

        Please list out all files that need to be inspect and make potential changes.

        Return in this exact format (one per line):
        filepath - #line number
        ...

        The line number should be where the AI should focus its attention for the fix.
        If line numbers are unknown, choose the most relevant symbol line from AST tags.
        If you are unsure, still list the most likely files.
        """

        response = client.chat.completions.create(
            model="nova-pro-v1",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=3000,
            stream=False
        )

        return response.choices[0].message.content

    def parse_error_files(self, ai_response):
        for line in ai_response.splitlines():
            if ' - ' in line:
                parts = line.split(' - ')
                if (not parts):
                    pats = line.split(' - #')
                if len(parts) == 2:
                    filename = parts[0].strip()
                    line_number = parts[1].strip()
                    if filename not in self.error_files:
                        self.error_files[filename] = []
                    self.error_files[filename].append(line_number)

        print(self.error_files)

    def get_context(self, filelist):
        context = []
        for f, lines in filelist.items():
            code_info = self.get_full_code(f)
            focus_lines = ", ".join(str(l) for l in (lines or [])) or "(unknown)"
            context.append(
                {
                    "file": code_info["file"],
                    "focus_lines": focus_lines,
                    "code": code_info["code"],
                }
            )
        return context


    def generate_edits(self, error_message):
        context_entries = self.get_context(self.error_files)
        if not context_entries:
            return ""

        SYSTEM_PROMPT = (
            "You are a debug expert. Return full updated file contents for the files you change. "
            "Do not return edit commands."
        )
        responses = []

        for entry in context_entries:
            print(entry['file'])
            prompt = f"""
            the error message is: 
            {error_message}

            Context Code (single file + focus lines):
            File path (only generate modification for this code): {entry['file']}
            Focus lines: {entry['focus_lines']}
            Code:
            {entry['code']}

            Please return the full updated file contents for this file.
            Use this format:
            [filepath]
            ```
            full file content
            ```

            Make sure the filepath is an absolute path.
            """

            response = client.chat.completions.create(
                model="nova-pro-v1",
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": prompt
                    },
                ],
                temperature=0.1,
                max_tokens=3000,
            )

            responses.append(response.choices[0].message.content)

        return "\n\n".join(responses)

    def get_full_code(self, file_path, code=None):
        """Return full code for a file."""
        if not file_path:
            return {"file": file_path, "code": "# (no file)"}
        abs_path = os.path.abspath(file_path)
        if code is None and os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as fh:
                    code = fh.read()
            except Exception:
                code = None
        if not code:
            return {"file": abs_path, "code": "# (empty or missing file)"}
        return {"file": abs_path, "code": code}

    def _parse_file_blocks(self, text):
        pattern = r"\[([^\]]+)\]:?\s*```(?:[a-zA-Z0-9_+-]*)\n(.*?)\n```"
        matches = re.findall(pattern, text or "", re.DOTALL)
        out = []
        for filename, code in matches:
            clean_name = (filename or "").strip()
            if clean_name:
                out.append((clean_name, code.rstrip("\n")))
        return out

    def save_generated_files(self, generated_text):
        files = self._parse_file_blocks(generated_text or "")
        for filename, code in files:
            abs_path = os.path.abspath(filename)
            Path(abs_path).parent.mkdir(parents=True, exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as fh:
                fh.write(code)

    def find_parent_nodes(self, flowchart_data, impacted_files):
        steps = flowchart_data.get("steps", {}) if isinstance(flowchart_data, dict) else {}
        if not isinstance(steps, dict):
            return [], ""

        impacted_set = {os.path.normpath(p) for p in (impacted_files or [])}
        impacted_steps = []
        for sid, step in steps.items():
            if not isinstance(step, dict):
                continue
            filenames = step.get("filenames", []) or []
            resolved = [os.path.normpath(f) for f in filenames]
            if any(p in impacted_set for p in resolved):
                impacted_steps.append(sid)

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

        parent_ids = []
        seen = set()
        for child_id in impacted_steps:
            for pid in parents.get(child_id, []):
                if pid not in seen:
                    seen.add(pid)
                    parent_ids.append(pid)

        summary_lines = []
        if impacted_steps:
            summary_lines.append("Child nodes updated: " + ", ".join(impacted_steps))
        if impacted_files:
            summary_lines.append("Files updated: " + ", ".join(impacted_files))
        summary = "\n".join(summary_lines) if summary_lines else "(no changes detected)"
        return parent_ids, summary

    def generate_parent_updates(self, flowchart_data, parent_ids, child_summary):
        steps = flowchart_data.get("steps", {}) if isinstance(flowchart_data, dict) else {}
        if not isinstance(steps, dict):
            return ""

        responses = []
        SYSTEM_PROMPT = (
            "You are a code editor. A child node changed. "
            "Update the parent node files if needed. Return full file contents."
        )

        for parent_id in (parent_ids or []):
            parent = steps.get(parent_id, {})
            parent_files = parent.get("filenames", []) if isinstance(parent, dict) else []
            if not parent_files:
                continue

            context_chunks = []
            for f in parent_files:
                info = self.get_full_code(f)
                context_chunks.append(
                    f"File: {info['file']}\n```\n{info['code']}\n```"
                )
            context_text = "\n\n".join(context_chunks) if context_chunks else "# (no related files)"

            prompt = f"""
            Parent Node ID: {parent_id}

            Child Change Summary:
            {child_summary}

            Parent File Context:
            {context_text}

            According to the child change, please generate edit if need to. if no edit needed to be done, please return absolute nothing.

            Return output in this format:
            [filepath]
            ```
            full file content
            ```
            """

            response = client.chat.completions.create(
                model="nova-pro-v1",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=3000,
            )

            responses.append(response.choices[0].message.content)

        return "\n\n".join(responses)
