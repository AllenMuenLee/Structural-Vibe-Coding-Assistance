import json
import os
from openai import OpenAI
from dotenv import load_dotenv
from src.utils.AstEmbedding import AstRagTable
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

    def extract_error_nova(self, error_message):
        SYSTEM_PROMPT = "You are a debugger extracter, and your job is to extract the functions and files mentioned in the error message, and return in the given format."
        prompt = f"""
        The error message is:
        {error_message}

        Analyze this error message and extract the following information:
        1. The file path where the error occurred.
        2. The line number of the error.

        return in this format:

        filepath - #line number
        ...
        """

        response = client.chat.completions.create(
            model="nova-2-lite-v1",
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
            max_tokens=2000,
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
        context = ""
        for f in filelist.keys():
            for l in filelist[f]:
                result = self.get_ast(f, int(l))
                context += json.dumps(result, indent=2)
                context += "\n"
        return context


    def generate_edits(self, error_message):
        context_ast = self.get_context(self.error_files)

        SYSTEM_PROMPT = "You are a debug expert, and your job is to identify the error and provide the correct fix for the error."
        prompt = f"""
        the error message is: 
        {error_message}

        Context AST:
        {context_ast}

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

        Example:
        [Insert] example.py - #12
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
            max_tokens=2000,
            stream=False
        )

        return response.choices[0].message.content

    def get_ast(self, file_path, line_number, code=None):
        if not file_path or not isinstance(line_number, int):
            return {"file": file_path, "line": line_number, "query": "", "matches": []}

        if code is None and os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as fh:
                    code = fh.read()
            except Exception:
                code = None
        if not code:
            return {"file": file_path, "line": line_number, "query": "", "matches": []}

        lines = code.splitlines()
        if 1 <= line_number <= len(lines):
            query = lines[line_number - 1].strip()
        else:
            query = ""
        if not query:
            query = code[:2000]

        table = AstRagTable(persist_dir=None)
        table.add_code(code, file_path)
        matches = table.search(query, top_k=5)
        return {"file": file_path, "line": line_number, "query": query, "matches": matches}

    def string_to_edit(self, edit_string):
        self.edits = {}
        lines = edit_string.splitlines()

        print(lines)
        
        if (lines[0] == "```"):
            lines = lines[1:]

        current = None
        in_code = False

        curr = []

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
                if not in_code and curr:
                    self.edits[file_path][-1][2] = "\n".join(curr)
                    curr = []
                continue
            elif in_code:
                curr.append(line)

    def edit(self, lines, content, line_n):
        print("editing")
        lines[line_n - 1] = content + "\n"

    def delete(self, lines, line_n):
        lines[line_n - 1] = ""

    def insert(self, lines, content, line_n):
        lines.insert(line_n - 1, content + "\n")

    def apply_edits(self):
        for f in self.edits.keys():
            with open(f, 'r', encoding='utf-8') as file:
                lines = file.readlines()

            for a in self.edits[f]:
                if (a[0] == 'Edit'):
                    self.edit(lines, a[2], a[1])
                elif (a[0] == 'Insert'):
                    self.insert(lines, a[2], a[1])
                elif (a[0] == 'Delete'):
                    self.delete(lines, a[2], a[1])

            with open(f, 'w', encoding='utf-8') as file:
                file.writelines(lines)


debugger = debugger("project_1")
error_message = f"""File "<frozen runpy>", line 198, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "C:\\Users\\limue\\Documents\\SVCA-Main\\project_1\\project_1\\test.py", line 14, in <module>
    print(add('2', 3))
          ~~~^^^^^^^^
  File "C:\\Users\\limue\\Documents\\SVCA-Main\\project_1\\project_1\\test.py", line 12, in add
    return a + b
           ~~^~~
TypeError: can only concatenate str (not "int") to str"""


if __name__ == "__main__":
    ai_response = debugger.extract_error_nova(error_message)
    print(ai_response)

    debugger.parse_error_files(ai_response)

    edit = debugger.generate_edits(error_message)
    print(edit)

    debugger.string_to_edit(edit)

    debugger.apply_edits()