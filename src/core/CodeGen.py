import os
import json
import re
from openai import OpenAI
from dotenv import load_dotenv
import src.utils.FileMng as FileMng
import src.utils.SymbolExt as SymbolExt
from pathlib import Path
import time
import src.utils.Terminal as Terminal

load_dotenv()

client = OpenAI(
    api_key=os.getenv("NOVA_API_KEY"),
    base_url="https://api.nova.amazon.com/v1",
    default_headers={"Accept-Encoding": "gzip, deflate"},  # Disable zstd
    timeout=90.0
)


class CodingAgent:
    # FIXED:
    def __init__(self, project_path):
        self.ast_map = {}
        self.project_root = str(project_path)  # ✅ Use project_path parameter
        self.project_name = Path(project_path).name  # ✅ Use project_path parameter
        
        if not self._load_ast_map():
            self.ast_map = SymbolExt.initialize_ast_map(self.project_root, self.ast_map)
            self._save_ast_map()

    def _to_abs_path(self, path_value):
        if not path_value:
            return path_value
        if os.path.isabs(path_value):
            return os.path.normpath(path_value)
        return os.path.normpath(os.path.join(self.project_root, path_value))

    def _save_ast_map(self):
        ast_map_path = os.path.join(self.project_root, "ast_map.json")
        normalized = {os.path.abspath(k): v for k, v in self.ast_map.items()}
        FileMng.save_json(normalized, ast_map_path)

    def _load_ast_map(self):
        ast_map_path = os.path.join(self.project_root, "ast_map.json")
        if not os.path.exists(ast_map_path):
            return False
        try:
            raw_map = FileMng.load_json(ast_map_path)
            self.ast_map = {os.path.abspath(k): v for k, v in raw_map.items()}
            return True
        except Exception:
            return False

    def call_nova(self, step, topic):
        file_set = {}
        
        # Run commands
        for c in step['command']:
            if c and c.strip():  # ✅ Only run non-empty commands
                output = Terminal.run_command(c, cwd=self.project_root)
                if output:
                    print(output, end="")
        
        if not step['filenames']:
            return ""
        
        # Collect file context
        for f in step['filenames']:
            norm_f = self._to_abs_path(f)
            if norm_f in self.ast_map:
                file_set[norm_f] = self.ast_map[norm_f]
            else:
                file_set[norm_f] = SymbolExt.get_ast_map("", file_path=norm_f)
        
        for f in step['files_to_import']:
            norm_f = self._to_abs_path(f)
            if norm_f in self.ast_map:
                file_set[norm_f] = self.ast_map[norm_f]
            else:
                file_set[norm_f] = SymbolExt.get_ast_map("", file_path=norm_f)
        
        # Build context
        context = SymbolExt.extract_symbol_tree(self.ast_map, file_set)
        import_list = SymbolExt.list_imports(None, file_set)
        context += "\n\nIMPORTS:\n" + "\n".join(import_list)
        
        print(context)
        
        SYSTEM_PROMPT = """You are a senior software architect and coding agent. The user will give you a description of a coding task, which is a step in a larger project.

        GENERAL RULES:
        1. Provide the code you want to implement. No conversational filler or explanations.
        2. You will be provided a context, which is a symbol table. Use it to understand the context of the current file. The format of the symbol table will be:
        File filepath:
        - [type] `name` (line #) -> (docstring)
        ...
        IMPORT:
        <import lines...>
        3. After you draft the code, review every requirement. If the requirement is not fulfilled, modify the code until it does.
        4. NO ASSUMING UNDER ANY CIRCUMSTANCE
        5. NEVER REPEAT IMPORT AND CODE

        CODING RULES:
        1. Read the symbol table, it includes the context
        First part includes context of the files you need to edit/add, and files you need to import and use its existing functions.
        Second part, after IMPORT: are the libraries that are already imported, you don't have to import again.
        2. If there is no existing code, generate code according to the description.
        3. You can only import existing libraries or files listed in FILES YOU MIGHT NEED TO IMPORT
        4. The output MUST strictly follow this format:
        [Filename]
        ```
        code
        ```
        [Filename]
        ```
        code
        ```
        ...
        5. When indicating the filename, don't use # filename.py, use [filename.py]
        6. All files in FILES TO GENERATE must be generated.
        7. Add docstring for each function and class.
        """
        
        prompt = f"""
        CONTEXT OF EXISTING FILES:
        {context}

        TOPIC: {topic}
        TASK: {step['description']}
        FILES TO GENERATE: {step['filenames']}
        FILES YOU MIGHT NEED TO IMPORT: {step['files_to_import']}

        NO ASSUMING UNDER ANY CIRCUMSTANCE
        NEVER REPEAT IMPORT AND CODE

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
            
            if response.choices[0].message.content is None:
                print("nothing generated")
                return self.call_nova(step, topic)
            
            return response.choices[0].message.content
        
        except Exception as e:
            print("error generating")
            if "Error code: 429" in str(e):
                print(e)
                time.sleep(10)
                return self.call_nova(step, topic)
            else:
                raise  # Re-raise other exceptions

    def generate(self, procedure, step, progress=None):
        if progress:
            step_id = step.get("id", "")
            step_desc = step.get("description", "")
            progress(step_id, step_desc)
        raw_code = self.call_nova(step, procedure["name"])
        
        if raw_code is not None:
            if "### QUESTION:" in raw_code:
                print(raw_code)
                return raw_code
            
            self.save_and_update(raw_code)
        
        # Process children
        for c in step["children"]:
            self.generate(procedure, procedure["steps"][c], progress=progress)
        
        return None

    def save_and_update(self, text):
        pattern = r"\[([^\]]+)\]:?\s*```(?:[a-zA-Z0-9_+-]*)\n(.*?)\n```"
        matches = re.findall(pattern, text, re.DOTALL)
        
        for filename, code in matches:
            abs_filename = self._to_abs_path(filename)
            norm_filename = Path(abs_filename)
            norm_filename.parent.mkdir(parents=True, exist_ok=True)
            
            # Check if file exists
            if os.path.exists(abs_filename):
                # Read existing content
                with open(abs_filename, "r", encoding="utf-8") as f:
                    existing_code = f.read()
                
                # Check if code already exists (avoid duplicates)
                if code.strip() in existing_code:
                    print(f"⚠️  Code already exists in {filename}, skipping...")
                    continue
                
                # Append new code
                with open(abs_filename, "a", encoding="utf-8") as f:
                    f.write("\n\n")
                    f.write(code)
            else:
                # Create new file
                with open(abs_filename, "w", encoding="utf-8") as f:
                    f.write(code)
            
            # Update AST map
            with open(abs_filename, "r", encoding="utf-8") as f:
                full_code = f.read()
            
            self.ast_map[str(norm_filename)] = SymbolExt.get_ast_map(
                full_code, file_path=str(norm_filename)
            )
            self._save_ast_map()


if __name__ == "__main__":
    project_path = os.path.abspath("project_1")
    agent = CodingAgent(project_path)
    filepath = os.path.join(project_path, "flowchart.json")
    procedure = FileMng.get_procedure(filepath)
    agent.generate(procedure, procedure["steps"][procedure["start_id"]])
