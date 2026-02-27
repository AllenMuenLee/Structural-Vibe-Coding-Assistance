import os
import json
import boto3
import re
from openai import OpenAI
from dotenv import load_dotenv
import FileMng
import SymbolExt
from pathlib import Path
import time
import Command

load_dotenv()

client = OpenAI(
    api_key=os.getenv("NOVA_API_KEY"),
    base_url="https://api.nova.amazon.com/v1"
)

class CodingAgent:
    def __init__(self, project_name):
        Command.run_command(f"cd {project_name}")
        self.ast_map = {}
        self.project_name = project_name
        if not self._load_ast_map():
            self.ast_map = SymbolExt.initialize_ast_map(self.project_name, self.ast_map)
            self._save_ast_map()

    def _save_ast_map(self):
        ast_map_path = self.project_name + "/ast_map.json"
        normalized = {os.path.normpath(k): v for k, v in self.ast_map.items()}
        FileMng.save_json(normalized, ast_map_path)

    def _load_ast_map(self):
        ast_map_path = self.project_name + "/ast_map.json"
        if not os.path.exists(ast_map_path):
            return False
        try:
            raw_map = FileMng.load_json(ast_map_path)
            self.ast_map = {os.path.normpath(k): v for k, v in raw_map.items()}
            return True
        except Exception:
            return False

    def call_nova(self, step):
        file_set = {}

        for c in step['command']:
            Command.run_command(c, cwd=self.project_name)

        if (not step['filenames']):
            return ""

        for f in step['filenames']:
            norm_f = os.path.normpath(f)
            if norm_f in self.ast_map:
                file_set[norm_f] = self.ast_map[norm_f]
            else:
                file_set[norm_f] = SymbolExt.get_ast_map("", file_path=norm_f)

        for f in step['files_to_import']:
            norm_f = os.path.normpath(f)
            if norm_f in self.ast_map:
                file_set[norm_f] = self.ast_map[norm_f]
            else:
                file_set[norm_f] = SymbolExt.get_ast_map("", file_path=norm_f)
        
        context = SymbolExt.extract_symbol_tree(self.ast_map, file_set)
        import_list = SymbolExt.list_imports(None, file_set)
        context += "\n\nIMPORTS:\n" + "\n".join(import_list)
        print(context)
        SYSTEM_PROMPT = """You are a senior software architect and coding agent. the user will give you a description of a coding task, which is a step in a larger project.
        GENERAL RULES:
        1. Provide the code you want to implement. No conversational filler or explanations.
        2. you will be provided a context, which is a symbol table. Use it to context of the current file. The format of the symbol table will be:
        File filepath:
        - [type] `name` (line #) -> (docstring)
        ...

        IMPORT:
        <import lines...>

        3. After you draft the code, review every requirement, if the requirement is not fulfilled, modify the code until it does.

        CODING RULES:
        1. Raad the symbol table, it includes the context
        First part includes context of the files you need to edit / add, and files you need to import and use its existing functions.
        Second part, after IMPORT: are the library that are already imported, you don't have to import again.
        2. If there is no existing code, generate code according to the descrption.
        3. The output MUST strictly follow this format:
        [Filename]
        ```
        code
        ```
        [Filename]
        ```
        code
        ```
        ...
        4. when indicating the filename, don't use # filename.py, use [filename.py]
        5. all files in FILES TO GENERATE must be generated.
        6. add docstring for each function and class.
        """

        prompt = f"""
        CONTEXT OF EXISTING FILES:
        {context}

        TASK: {step['description']}
        FILES TO GENERATE: {step['filenames']}
        FILES YOU MIGHT NEED TO IMPORT: {step['files_to_import']}

        Please give the list of functions and imports you see from the symbol table as a comment
        Please give the raw code and docstring right below the function or class definition, don't put it above
        or ask questions if the code is repeated or not clear context, please don't skip asking question even if the code is short.
        """
        try:
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
                temperature=0.2,
                max_tokens=3000,
                top_p=0.9,
                stream=False
            )
            if type(response.choices[0].message.content.strip()) == type(None):
                print("nothing generated")
                return self.call_nova(step)
            return response.choices[0].message.content
        except Exception as e:
            if ("Error code: 429" in str(e)):
                print(e)
                time.sleep(10)
                return self.call_nova(step)


    def generate(self, procedure,step):
            
        raw_code = self.call_nova(step)
        if (type(raw_code) != type(None)):
            if "### QUESTION:" in raw_code:
                print(raw_code)
                return raw_code
            self.save_and_update(raw_code)

            # If this node has children (as IDs), you would handle them here
            # In your format, 'children' is a list of keys to other dict entries
        for c in step["children"]:
            self.generate(procedure, procedure["steps"][c])

        return None

    def save_and_update(self, text):
        pattern = r"\[([^\]]+)\]:?\s*```(?:[a-zA-Z0-9_+-]*)\n(.*?)\n```"
        
        # re.DOTALL allows the '.' to match newlines within the code block
        matches = re.findall(pattern, text, re.DOTALL)
        
        extracted_data = {}
        for filename, code in matches:
            norm_filename = os.path.normpath(filename)
            norm_filename = Path(norm_filename)
            norm_filename.parent.mkdir(parents=True, exist_ok=True)

            with open(filename, "a", encoding="utf-8") as f:
                f.write(code)
                f.write("\n\n")  # Add spacing between code blocks if multiple are added to the same file

            with open(filename, "r", encoding="utf-8") as f:
                full_code = f.read()

            self.ast_map[norm_filename] = SymbolExt.get_ast_map(
                full_code, file_path=norm_filename
            )
            self._save_ast_map()

if __name__ == "__main__":
    project_name = "project_1"
    agent = CodingAgent(project_name)
    filepath = project_name + "/flowchart.json"
    procedure = FileMng.get_procedure(filepath)
    agent.generate(procedure, procedure["steps"][procedure["start_id"]])
