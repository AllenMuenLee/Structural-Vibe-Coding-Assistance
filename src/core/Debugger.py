import json
import os
from openai import OpenAI
from dotenv import load_dotenv
import src.utils.FileEdit as FileEdit
import re

load_dotenv()

client = OpenAI(
    api_key=os.getenv("NOVA_API_KEY"),
    base_url="https://api.nova.amazon.com/v1"
)

class debugger:
    def __init__(self, project_name):
        self.project_name = project_name
        self.edits = {}
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
            temperature=0.1,
            max_tokens=5000,
            stream=False
        )

        return response.choices[0].message.content

    def parse_error_files(self, ai_response):
        for line in ai_response.splitlines():
            if ' - #' in line:
                parts = line.split(' - #')
                if len(parts) == 2:
                    filename = parts[0].strip()
                    line_number = parts[1].strip()
                    if filename not in self.error_files:
                        self.error_files[filename] = []
                    self.error_files[filename].append(line_number)

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

        SYSTEM_PROMPT = "You are a debug expert, and your job is to identify the error and provide the correct fix for the error."
        responses = []

        for entry in context_entries:
            prompt = f"""
            the error message is: 
            {error_message}

            Context Code (single file + focus lines):
            File path: {entry['file']}
            Focus lines: {entry['focus_lines']}
            Code:
            {entry['code']}

            Please generate the edit for this error message, don't provide conversation, and you must provide correct spacing
            return in this format:
            if you want to edit: 
                [Edit] filepath - #line number
                ```
                Code
                ```
            if you want to insert:
                [Insert] filepath - #line number
                ```
                Code
                ```
            if you want to delete: 
                [Delete] filepath - #line number

            Make sure the filepath is an absolute path
            Example:
            [Insert] c://users//documents//example.py - #12
                ```
                print(example_function(a, b))
                ```
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

    def string_to_edit(self, edit_string):
        self.edits = {}
        lines = edit_string.splitlines()

        print(lines)

        if not lines:
            return

        if (lines[0] == "```"):
            lines = lines[1:]

        current = None
        in_code = False

        curr = []
        file_path = None

        for raw in lines:
            line = raw.strip()
            print("line:", line)
            if not in_code:
                exp = r"\[(Edit|Insert|Delete)\] (.+?) - #(\d+)"
                match = re.match(exp, line)
                if match:
                    action = match.group(1)
                    file_path = match.group(2)
                    line_number = int(match.group(3))
                    if file_path not in self.edits:
                        self.edits[file_path] = []
                    self.edits[file_path].append([
                        action,
                        line_number,
                        ""
                    ])
                    continue

            if line == "```":
                in_code = not in_code
                if not in_code and curr and file_path and file_path in self.edits:
                    self.edits[file_path][-1][2] = "\n".join(curr)
                    curr = []
                continue
            elif in_code:
                curr.append(line)

    def fix(self):
        FileEdit.apply_edits(self.edits)
