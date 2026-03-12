import json
import os
import re
from openai import OpenAI
from dotenv import load_dotenv
import src.utils.SymbolExt as SymbolExt
import src.utils.FileMng as FileMng

load_dotenv()

client = OpenAI(
    api_key=os.getenv("NOVA_API_KEY"),
    base_url="https://api.nova.amazon.com/v1",
    default_headers={"Accept-Encoding": "gzip, deflate"},
    timeout=90.0
)


class AstFlowchartGenerator:
    """Generate AST map (stored in appdata) with AI docstrings, then generate a flowchart from it."""

    def __init__(self, project_root):
        self.project_root = os.path.abspath(project_root)
        self.ast_map = {}

    def generate_all(self):
        """Generate AST map (with docstrings) and flowchart.json."""
        self.generate_ast_map()
        return self.generate_flowchart()

    def generate_ast_map(self):
        """Scan project, build AST map, and enrich with AI docstrings."""
        self.ast_map = SymbolExt.initialize_ast_map(self.project_root, {})
        self._add_docstrings_to_ast_map()
        self._save_ast_map()
        return self.ast_map

    def generate_flowchart(self):
        """Generate flowchart.json based on the AST map."""
        if not self.ast_map:
            if not self._load_ast_map():
                self.generate_ast_map()

        flowchart_data = self._call_nova_for_flowchart(self.ast_map)
        if not flowchart_data:
            return None

        output_path = os.path.join(self.project_root, "flowchart.json")
        FileMng.save_json(flowchart_data, output_path)
        return flowchart_data

    def _save_ast_map(self):
        normalized = {os.path.abspath(k): v for k, v in self.ast_map.items()}
        project_id = FileMng.get_project_id_by_root(self.project_root)
        if project_id:
            FileMng.save_ast_map(project_id, normalized)

    def _load_ast_map(self):
        project_id = FileMng.get_project_id_by_root(self.project_root)
        if not project_id:
            return False
        cached = FileMng.load_ast_map(project_id)
        if cached:
            self.ast_map = {os.path.abspath(k): v for k, v in cached.items()}
            return True
        return False

    def _add_docstrings_to_ast_map(self):
        for file_path, tags in self.ast_map.items():
            code = self._read_code(file_path)
            if code is None:
                continue

            language = self._detect_language(file_path)
            if not language:
                continue

            lines = code.splitlines()
            missing = []
            for tag in tags:
                existing = self._get_doc_comment(lines, tag.get("line"), language)
                if existing:
                    tag["docstring"] = existing
                    continue

                doc_id = self._tag_id(tag)
                tag["docstring_id"] = doc_id
                missing.append({
                    "id": doc_id,
                    "kind": tag.get("kind", "symbol"),
                    "name": tag.get("name", "?"),
                    "line": tag.get("line")
                })

            if missing:
                generated = self._call_nova_for_docstrings(file_path, code, missing)
                for tag in tags:
                    doc_id = tag.get("docstring_id")
                    if doc_id and doc_id in generated:
                        tag["docstring"] = generated[doc_id]

            for tag in tags:
                tag.pop("docstring_id", None)

    def _call_nova_for_docstrings(self, file_path, code, missing):
        trimmed_code = code
        if len(trimmed_code) > 12000:
            trimmed_code = trimmed_code[:12000] + "\n# (truncated)"

        SYSTEM_PROMPT = (
            "You are a senior engineer. Generate concise docstrings for symbols "
            "missing documentation. Return JSON only."
        )
        prompt = f"""
        File: {file_path}

        Symbols missing docstrings (id, kind, name, line):
        {json.dumps(missing, indent=2)}

        Code:
        {trimmed_code}

        Rules:
        - Return ONLY a JSON object mapping id -> docstring string.
        - Keep each docstring 1-2 sentences, plain text (no quotes, no markdown).
        - Do not include any extra keys or commentary.
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

        content = response.choices[0].message.content or ""
        data = self._safe_json_loads(content)
        return data if isinstance(data, dict) else {}

    def _call_nova_for_flowchart(self, ast_map):
        SYSTEM_PROMPT = (
            "You are a senior software architect. Build a simple software structure JSON for the project "
            "based on the AST symbol map. Return JSON only."
        )

        compact = self._compact_ast_map(ast_map)
        prompt = f"""
        AST MAP (compact):
        {json.dumps(compact, indent=2)}

        Rules:
        - Understand the software strucuture with the ast map, build a software structure one directional tree.
        - every children node should be an existing nodes. Generate children nodes before generating parent nodes.
        - Return JSON only, no extra text.
        - One parent a node.
        - one to three children a node.
        Return ONLY a valid JSON object with this structure:
        {{
            "framework": "Any framework that's applicable",
            "nodes": [
                {{
                    "id": "initialize project",
                    "description": "install dependencies",
                    "filenames": [],
                    "files_to_import": [],
                    "command": ["initialize the project"],
                    "children": []
                }},
                {{
                    "id": "function 1",
                    "description": "function1 does this",
                    "filenames": ["file1.extension"],
                    "files_to_import": [],
                    "command": [],
                    "parent": ["integrate project"],
                    "children": []
                }},
                {{
                    "id": "function 2",
                    "description": "function2 does this",
                    "filenames": ["file1.extension"],
                    "files_to_import": [],
                    "command": ["install an api"],
                    "parent": ["integrate project"],
                    "children": []
                }},
                {{
                    "id": "function 3",
                    "description": "function 3 does this",
                    "filenames": ["example.extension"],
                    "files_to_import": ["file1.extension"],
                    "command": [],
                    "parent": ["integrate project"],
                    "children": []
                }},
                {{
                    "id": "integrate project",
                    "description": "Integrate function 1, function 2, and function 3",
                    "filenames": ["file1.extension"],
                    "files_to_import": [],
                    "command": [],
                    "children": ["function 1", "function 2", "function 3"]
                }}
            ]
        }}
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

        content = response.choices[0].message.content or ""
        data = self._safe_json_loads(content)
        return data if isinstance(data, dict) else None

    def _compact_ast_map(self, ast_map):
        compact = {}
        for file_path, tags in (ast_map or {}).items():
            compact[file_path] = []
            for tag in tags:
                compact[file_path].append({
                    "name": tag.get("name"),
                    "kind": tag.get("kind"),
                    "line": tag.get("line"),
                    "parent": tag.get("parent"),
                    "docstring": tag.get("docstring", "")
                })
        return compact

    def _read_code(self, file_path):
        if not file_path or not os.path.exists(file_path):
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as fh:
                return fh.read()
        except Exception:
            return None

    def _detect_language(self, file_path):
        if not file_path:
            return None
        _, ext = os.path.splitext(file_path)
        return SymbolExt.EXT_TO_LANG.get(ext.lower())

    def _get_doc_comment(self, lines, line_no, language):
        if not line_no or line_no < 1 or line_no > len(lines):
            return ""
        idx = line_no - 1

        if language == "python":
            for j in range(idx, min(idx + 6, len(lines))):
                stripped = lines[j].strip()
                if stripped.startswith(("'''", '"""')):
                    quote = stripped[:3]
                    content = stripped[3:]
                    if content.endswith(quote) and len(content) > 3:
                        return content[:-3].strip()
                    parts = []
                    if content:
                        parts.append(content)
                    k = j + 1
                    while k < len(lines):
                        line = lines[k]
                        if quote in line:
                            before, _sep, _after = line.partition(quote)
                            parts.append(before)
                            break
                        parts.append(line)
                        k += 1
                    return " ".join(p.strip() for p in parts if p.strip())
            return ""

        idx -= 1
        while idx >= 0 and not lines[idx].strip():
            idx -= 1
        if idx < 0:
            return ""
        if lines[idx].strip().endswith("*/"):
            parts = []
            while idx >= 0:
                line = lines[idx].strip()
                parts.append(line)
                if line.startswith("/**"):
                    break
                idx -= 1
            parts = list(reversed(parts))
            body = " ".join(
                p.replace("/**", "").replace("*/", "").lstrip("*").strip()
                for p in parts
            ).strip()
            return body
        return ""

    def _tag_id(self, tag):
        kind = tag.get("kind", "symbol")
        name = tag.get("name", "?")
        line = tag.get("line", 0)
        return f"{kind}:{name}:{line}"

    def _safe_json_loads(self, text):
        if not text:
            return None
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r'^```(?:json)?\s*\n', '', cleaned)
            cleaned = re.sub(r'\n```\s*$', '', cleaned)
        try:
            return json.loads(cleaned)
        except Exception:
            pass
        try:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(cleaned[start:end + 1])
        except Exception:
            return None
        return None
