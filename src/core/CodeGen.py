import os
import re
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
import time
import src.utils.Terminal as Terminal
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


class CodingAgent:
    # FIXED:
    def __init__(self, project_path):
        self.project_root = str(project_path)  # ✅ Use project_path parameter
        self.project_name = Path(project_path).name  # ✅ Use project_path parameter
        self.stack = []
        self._progress = None

    def _notify_rate_limit(self):
        msg = "Request per minute exceeded. Retrying in 10 seconds..."
        if callable(self._progress):
            try:
                self._progress("rate-limit", msg)
            except Exception:
                pass
        else:
            print(msg)


    def _to_abs_path(self, path_value):
        if not path_value:
            return path_value
        if os.path.isabs(path_value):
            return os.path.normpath(path_value)
        return os.path.normpath(os.path.join(self.project_root, path_value))

    def _read_file_text(self, path_value):
        if not path_value or not os.path.exists(path_value):
            return ""
        try:
            with open(path_value, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return ""

    def _update_ast_map_for_file(self, abs_path):
        if not abs_path:
            return
        full_code = self._read_file_text(abs_path)
        if full_code is None:
            return
        try:
            entry = SymbolExt.get_ast_map(full_code, file_path=abs_path)
        except Exception:
            return

        project_id = FileMng.get_project_id_by_root(self.project_root)
        ast_map = FileMng.load_ast_map(project_id) if project_id else None
        if not isinstance(ast_map, dict):
            ast_map = {}

        ast_map[os.path.abspath(abs_path)] = entry

        # Save ast_map to appdata
        try:
            if project_id:
                FileMng.save_ast_map(project_id, ast_map)
        except Exception:
            pass

    def _load_ast_tags_text(self, max_files=200, max_tags_per_file=30):
        project_id = FileMng.get_project_id_by_root(self.project_root)
        ast_map = FileMng.load_ast_map(project_id) if project_id else None
        if not isinstance(ast_map, dict):
            return "# (no tags)"

        parts = []
        count = 0
        for file_path, entries in ast_map.items():
            if count >= max_files:
                break
            if not isinstance(entries, list):
                continue
            tags = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("name")
                kind = entry.get("type") or entry.get("kind") or "symbol"
                params = entry.get("params") or []
                if name and params:
                    name = f"{name}({', '.join(params)})"
                doc = entry.get("docstring") or entry.get("comment") or ""
                if name:
                    if doc:
                        short_doc = str(doc).strip().replace("\n", " ")
                        if len(short_doc) > 160:
                            short_doc = short_doc[:157] + "..."
                        tags.append(f"{kind} {name} — {short_doc}")
                    else:
                        tags.append(f"{kind} {name}")
                if len(tags) >= max_tags_per_file:
                    break
            if not tags:
                continue
            parts.append(f"FILE: {file_path}\n- " + "\n- ".join(tags))
            count += 1
        return "\n\n".join(parts) if parts else "# (no tags)"

    def call_nova(self, step, topic):
        file_set = []
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
            file_set.append(norm_f)

        for f in step['files_to_import']:
            norm_f = self._to_abs_path(f)
            file_set.append(norm_f)

        # Build context with full file contents
        seen = set()
        context_parts = []
        for f in file_set:
            if not f or f in seen:
                continue
            seen.add(f)
            code = self._read_file_text(f)
            context_parts.append(f"FILE: {f}\n```\n{code}\n```")
        context = "\n\n".join(context_parts)

        tags_text = self._load_ast_tags_text()

        print(context)
        print(tags_text)
        
        SYSTEM_PROMPT = """You are a senior software architect and coding agent. The user will give you a description of a coding task, which is a step in a larger project.

        GENERAL RULES:
        1. Provide the code you want to implement. No conversational filler or explanations.
        2. You will be provided a context with the full content of relevant files plus a project-wide tag index. Use both to understand the current codebase.
        3. After you draft the code, review every requirement. If the requirement is not fulfilled, modify the code until it does.
        5. NEVER REPEAT IMPORT AND CODE
        6. Pls always think deeply whether ur code works or not. 
        7. Your code doesnt have to be short, can be long if needed, pls idiot u always generate useless code.
        8. If initializing a react or next project, pls initialize in the root folder, dont create another folder.
        CODING RULES:
        1. Read the provided file contents and the tag index; use existing code and imports from those files.
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
        8. Please generate the actual runnable code instead of some shit like (placeholder, actual analysis logic should be implemented), this is fucking bullshit idiot
        9. 
        READ THE CONTEXT AND AVOID GENERATING EXISITNG FUNCTIONS OR METHOD
        """
        
        prompt = f"""
        PROJECT TAGS (SUMMARY OF OTHER FILES):
        {tags_text}

        CONTEXT OF EXISTING FILES:
        {context}

        TOPIC: {topic}
        TASK: {step['description']}
        FILES TO GENERATE: {step['filenames']}
        FILES YOU MIGHT NEED TO IMPORT: {step['files_to_import']}

        NO ASSUMING UNDER ANY CIRCUMSTANCE
        NEVER REPEAT GENERATING THE SAME FUNCTION, CLASS, LOGIC
        IF THIS FILE ISN'T A MAIN FILE, IT SHOULD ONLY BULID FUNCTIONS, CLASSES, VARIABLES, AND NOT RUN ANYTHING
        If initializing a react or next project, pls initialize in the root folder, dont create another folder.
        Please give the raw code and docstring right below the function or class definition, don't put it above
        or ask questions if the code is repeated or not clear context, please don't skip asking question even if the code is short.
        """
        
        for attempt in range(6):
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
                )
                
                if response.choices[0].message.content is None:
                    print("nothing generated")
                    return self.call_nova(step, topic)
                
                return response.choices[0].message.content
            
            except Exception as e:
                print("error generating")
                if is_rate_limit_error(e):
                    time.sleep(10)
                    continue
                raise  # Re-raise other exceptions

    def _get_children(self, step):
        if not isinstance(step, dict):
            return []
        if "chlidren" in step:
            return step.get("chlidren", []) or []
        return step.get("children", []) or []

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
        
        return

    def generate_project(self, procedure, progress=None):
        self._progress = progress
        steps = procedure.get("steps", {})
        if not steps:
            return

        # Reverse order: process leaves first (parents after children)
        remaining_children = {step_id: 0 for step_id in steps.keys()}
        parents_of = {step_id: [] for step_id in steps.keys()}
        for step_id, step in steps.items():
            children = self._get_children(step)
            remaining_children[step_id] = len(children)
            for child_id in children:
                if child_id in parents_of:
                    parents_of[child_id].append(step_id)

        ready = [step_id for step_id, count in remaining_children.items() if count == 0]
        completed = set()

        while ready:
            current_id = ready.pop(0)
            if current_id in completed:
                continue
            step = steps.get(current_id)
            if not step:
                continue

            self.generate(procedure, step, progress=progress)
            completed.add(current_id)

            for parent_id in parents_of.get(current_id, []):
                if parent_id not in remaining_children:
                    continue
                remaining_children[parent_id] -= 1
                if remaining_children[parent_id] <= 0 and parent_id not in completed:
                    ready.append(parent_id)

        # Fallback for cycles or missing parents: process remaining steps in a stable order
        remaining = [sid for sid in steps.keys() if sid not in completed]
        for step_id in remaining:
            step = steps.get(step_id)
            if not step:
                continue
            self.generate(procedure, step, progress=progress)

    def save_and_update(self, text):
        pattern = r"\[([^\]]+)\]:?\s*```(?:[a-zA-Z0-9_+-]*)\n(.*?)\n```"
        matches = re.findall(pattern, text, re.DOTALL)

        for filename, code in matches:
            abs_filename = self._to_abs_path(filename)
            norm_filename = Path(abs_filename)
            norm_filename.parent.mkdir(parents=True, exist_ok=True)

            # Overwrite with full file content generated by the model.
            with open(abs_filename, "w", encoding="utf-8") as f:
                f.write(code.rstrip("\n") + "\n")

            # Update AST map entry for this file
            self._update_ast_map_for_file(abs_filename)

