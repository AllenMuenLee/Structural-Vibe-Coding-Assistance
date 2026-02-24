import os
import json
import boto3
import re
from openai import OpenAI
from dotenv import load_dotenv
import FileMng
import SymbolExt

load_dotenv()

client = OpenAI(
    api_key=os.getenv("NOVA_API_KEY"),
    base_url="https://api.nova.amazon.com/v1"
)

class CodingAgent:
    def __init__(self, project_name):
        self.ast_map = {}
        self.project_name = project_name
        if not self._load_ast_map():
            self.initialize_ast_map(self.project_name)

    def initialize_ast_map(self, root_dir):
        """Populate ast_map by scanning existing source files."""
        skip_dirs = {".git", "__pycache__"}
        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        code = f.read()
                    norm_path = os.path.normpath(file_path)
                    self.ast_map[norm_path] = SymbolExt.get_ast_map(
                        code, file_path=norm_path
                    )
                except Exception:
                    continue
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

    def call_nova(self, data):
        file_set = {p for p in data.get("filenames", [])}
        
        context = SymbolExt.extract_symbol_tree(self.ast_map, file_set)
        print(context)
        SYSTEM_PROMPT = """You are a senior software architect and coding agent. the user will give you a description of a coding task, which is a step in a larger project.
        GENERAL RULES:
        1. Provide the code you want to implement. No conversational filler or explanations.
        2. you will be provided a context, which is a symbol table. Use it to context of the current file. The format of the symbol table will be:
        - [type] `name` (line #) -> #comment

        CODING RULES:
        1. Raad the symbol table, if there are exisiting code, you're job is to add new code that is not repeated. 
        2. If there is no existing code, only generate code according to the descrption.
        3. If you have new code to implementation, output MUST use this format ONLY, this is an example:
        [main.py]
        ```
        def new_function():
            #comment
            pass
        ```
        [anotherfile.py]
        ```
        def new_function():
            #comment
            pass
        ```
        3. add docstring for each function and class.

        QUESTION RULES:
        1. unless you think the code will not work, don't ask questions.
        2. If anything like
            -unclear description about specific implementation or framework 
            -no new code to generate
        3. If you have a question, don't emit the code
        4. please clarify that using the format below and don't generate the code:
        ### QUESTION: [Your question here]
        """

        prompt = f"""
        CONTEXT OF EXISTING FILES:
        {context}

        TASK: {data['description']}
        FILES TO GENERATE: {data['filenames']}

        Please give the raw code and comment right below the function or class definition, don't put it above
        or ask questions if the code is repeated or not clear context, please don't skip asking question even if the code is short.
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
            max_tokens=3000,
            stream=False
        )

        print(response.choices[0].message.content)
        
        return response.choices[0].message.content


    def generate_by_steps(self, procedure, visited_nodes = []):
        """Iterates through the dictionary structure: {ID: {data}}"""
        for step_id, data in procedure.items():
            if (step_id in visited_nodes):
                continue
            visited_nodes.append(step_id)
            print(f"--- Executing Step {step_id}: {data['description']} ---")
            
            # Build context from previously created file skeletons
            
            raw_code = self.call_nova(data)
            if "### QUESTION:" in raw_code:
                print(raw_code)
                return raw_code
            self.save_and_update(raw_code)

            # If this node has children (as IDs), you would handle them here
            # In your format, 'children' is a list of keys to other dict entries
            if data.get("children"):
                # Filter the main dict for only these children and recurse
                child_subdict = {c_id: procedure[c_id] for c_id in data["children"] if c_id in procedure}
                self.generate_by_steps(child_subdict)

        return None

    def save_and_update(self, text):
        pattern = r"\[([^\]]+)\]:?\s*```(?:[a-zA-Z0-9_+-]*)\n(.*?)\n```"
        
        # re.DOTALL allows the '.' to match newlines within the code block
        matches = re.findall(pattern, text, re.DOTALL)
        
        extracted_data = {}
        for filename, code in matches:
            with open(filename, "a", encoding="utf-8") as f:
                f.write(code)
                f.write("\n\n")  # Add spacing between code blocks if multiple are added to the same file

            with open(filename, "r", encoding="utf-8") as f:
                full_code = f.read()

            norm_filename = os.path.normpath(filename)
            self.ast_map[norm_filename] = SymbolExt.get_ast_map(
                full_code, file_path=norm_filename
            )
            self._save_ast_map()

if __name__ == "__main__":
    project_name = "project_1"
    agent = CodingAgent(project_name)
    filepath = project_name + "/procedure.json"
    procedure = FileMng.get_procedure(filepath)
    agent.generate_by_steps(procedure)
