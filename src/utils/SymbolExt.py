import os
from tree_sitter_language_pack import get_parser

EXT_TO_LANG = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
}



def _detect_language(file_path):
    if not file_path:
        return None
    _, ext = os.path.splitext(file_path)
    return EXT_TO_LANG.get(ext.lower())


def _node_text(source_bytes, node):
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")


def _get_name(source_bytes, node):
    name_node = node.child_by_field_name("name")
    if name_node:
        return _node_text(source_bytes, name_node)
    for child in node.children:
        if child.type in ("identifier", "property_identifier"):
            return _node_text(source_bytes, child)
    return None


def _add_var_tag(name, node, class_stack, tags):
    if not name:
        return
    tags.append({
        "name": name,
        "kind": "variable",
        "line": node.start_point[0] + 1,
        "parent": class_stack[-1] if class_stack else None
    })


def _walk_python_symbols(source_bytes, node, class_stack, tags):
    node_type = node.type
    if node_type == "class_definition":
        name = _get_name(source_bytes, node)
        if name:
            tags.append({
                "name": name,
                "kind": "class",
                "line": node.start_point[0] + 1,
                "parent": None
            })
        class_stack.append(name)
        for child in node.children:
            _walk_python_symbols(source_bytes, child, class_stack, tags)
        class_stack.pop()
        return
    if node_type == "function_definition":
        name = _get_name(source_bytes, node)
        if name:
            tags.append({
                "name": name,
                "kind": "function",
                "line": node.start_point[0] + 1,
                "parent": class_stack[-1] if class_stack else None
            })
    if node_type == "assignment":
        for child in node.children:
            if child.type == "identifier":
                _add_var_tag(_node_text(source_bytes, child), node, class_stack, tags)
    if node_type == "annotated_assignment":
        target = node.child_by_field_name("target")
        if target and target.type == "identifier":
            _add_var_tag(_node_text(source_bytes, target), node, class_stack, tags)
    if node_type == "for_statement":
        target = node.child_by_field_name("left")
        if target and target.type == "identifier":
            _add_var_tag(_node_text(source_bytes, target), node, class_stack, tags)
    if node_type == "with_statement":
        for child in node.children:
            if child.type == "as_pattern":
                alias = child.child_by_field_name("alias")
                if alias and alias.type == "identifier":
                    _add_var_tag(_node_text(source_bytes, alias), node, class_stack, tags)
    for child in node.children:
        _walk_python_symbols(source_bytes, child, class_stack, tags)


def _walk_js_symbols(source_bytes, node, class_stack, tags):
    node_type = node.type
    if node_type == "class_declaration":
        name = _get_name(source_bytes, node)
        if name:
            tags.append({
                "name": name,
                "kind": "class",
                "line": node.start_point[0] + 1,
                "parent": None
            })
        class_stack.append(name)
        for child in node.children:
            _walk_js_symbols(source_bytes, child, class_stack, tags)
        class_stack.pop()
        return
    if node_type in ("function_declaration",):
        name = _get_name(source_bytes, node)
        if name:
            tags.append({
                "name": name,
                "kind": "function",
                "line": node.start_point[0] + 1,
                "parent": None
            })
    if node_type in ("method_definition",):
        name = _get_name(source_bytes, node)
        if name:
            tags.append({
                "name": name,
                "kind": "method",
                "line": node.start_point[0] + 1,
                "parent": class_stack[-1] if class_stack else None
            })
    if node_type == "variable_declarator":
        name = _get_name(source_bytes, node)
        if name:
            tags.append({
                "name": name,
                "kind": "variable",
                "line": node.start_point[0] + 1,
                "parent": class_stack[-1] if class_stack else None
            })
    if node_type == "assignment_expression":
        left = node.child_by_field_name("left")
        if left and left.type == "identifier":
            tags.append({
                "name": _node_text(source_bytes, left),
                "kind": "variable",
                "line": node.start_point[0] + 1,
                "parent": class_stack[-1] if class_stack else None
            })
    for child in node.children:
        _walk_js_symbols(source_bytes, child, class_stack, tags)


def _walk_symbols(source_bytes, node, language, class_stack, tags):
    if language == "python":
        _walk_python_symbols(source_bytes, node, class_stack, tags)
        return
    if language in ("javascript", "typescript", "tsx"):
        _walk_js_symbols(source_bytes, node, class_stack, tags)
        return


def _walk_python_imports(source_bytes, node, imports, include_line=False):
    if node.type in ("import_statement", "import_from_statement"):
        text = _node_text(source_bytes, node).strip()
        if text:
            if include_line:
                imports.append({
                    "name": text,
                    "kind": "import",
                    "line": node.start_point[0] + 1,
                })
            else:
                imports.append(text)
    for child in node.children:
        _walk_python_imports(source_bytes, child, imports, include_line=include_line)


def _walk_js_imports(source_bytes, node, imports, include_line=False):
    if node.type == "import_statement":
        text = _node_text(source_bytes, node).strip()
        if text:
            if include_line:
                imports.append({
                    "name": text,
                    "kind": "import",
                    "line": node.start_point[0] + 1,
                })
            else:
                imports.append(text)
    for child in node.children:
        _walk_js_imports(source_bytes, child, imports, include_line=include_line)


def get_ast_map(code, file_path):
    language = _detect_language(file_path)
    if not language:
        return []
    parser = get_parser(language)
    source_bytes = code.encode("utf-8", errors="ignore")
    tree = parser.parse(source_bytes)
    tags = []
    _walk_symbols(source_bytes, tree.root_node, language, [], tags)
    return tags


def initialize_ast_map(root_dir, ast_map=None):
    """Populate ast_map by scanning existing source files."""
    skip_dirs = {".git", "__pycache__"}
    ast_map = ast_map or {}
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    code = f.read()
                norm_path = os.path.normpath(file_path)
                ast_map[norm_path] = get_ast_map(code, file_path=norm_path)
            except Exception:
                continue
    return ast_map


def list_imports(code, fileset, include_line=False):
    file_paths = list(fileset.keys())

    imports = []
    seen_paths = set()
    for path in file_paths:
        if not path:
            continue
        norm_path = os.path.normpath(path)
        if norm_path in seen_paths:
            continue
        seen_paths.add(norm_path)

        language = _detect_language(norm_path)
        if not language:
            continue

        file_code = None
        if code is not None and path == fileset:
            file_code = code
        elif os.path.exists(norm_path):
            try:
                with open(norm_path, "r", encoding="utf-8") as fh:
                    file_code = fh.read()
            except Exception:
                file_code = None

        if file_code is None:
            continue

        parser = get_parser(language)
        source_bytes = file_code.encode("utf-8", errors="ignore")
        tree = parser.parse(source_bytes)
        file_imports = []
        if language == "python":
            _walk_python_imports(source_bytes, tree.root_node, file_imports, include_line=include_line)
        elif language in ("javascript", "typescript", "tsx"):
            _walk_js_imports(source_bytes, tree.root_node, file_imports, include_line=include_line)

        imports.append(f"#{norm_path}")
        if file_imports:
            imports.extend(file_imports)

    return imports


def _summarize_leaf_text(text):
    text = text.replace("\n", "\\n").strip()
    if len(text) > 80:
        return text[:77] + "..."
    return text


def _format_node_label(source_bytes, node, field_name):
    label = node.type
    if field_name:
        label = f"{field_name}: {label}"
    if node.type in (
        "identifier",
        "property_identifier",
        "string",
        "string_fragment",
        "string_content",
        "integer",
        "float",
        "true",
        "false",
        "none",
        "null",
        "number",
    ):
        value = _summarize_leaf_text(_node_text(source_bytes, node))
        if value:
            label = f"{label} = {value}"
    return label


def _render_ast_tree(source_bytes, node, max_depth=12, max_nodes=4000):
    lines = []
    node_counter = [0]

    def walk(n, prefix, is_last, depth):
        if node_counter[0] >= max_nodes:
            return
        node_counter[0] += 1

        field_name = None
        parent = n.parent
        if parent:
            try:
                idx = parent.children.index(n)
                field_name = parent.field_name_for_child(idx)
            except Exception:
                field_name = None

        connector = "`- " if is_last else "|- "
        lines.append(prefix + connector + _format_node_label(source_bytes, n, field_name))

        if depth >= max_depth:
            return

        children = list(n.children)
        if not children:
            return

        next_prefix = prefix + ("   " if is_last else "|  ")
        for i, child in enumerate(children):
            walk(child, next_prefix, i == len(children) - 1, depth + 1)

    walk(node, "", True, 0)
    return "\n".join(lines)


def get_ast_tree(code, file_path, max_depth=12, max_nodes=4000):
    language = _detect_language(file_path)
    if not language:
        return "# (unsupported language)"
    parser = get_parser(language)
    source_bytes = code.encode("utf-8", errors="ignore")
    tree = parser.parse(source_bytes)
    return _render_ast_tree(source_bytes, tree.root_node, max_depth=max_depth, max_nodes=max_nodes)


def extract_symbol_tree(ast_map, file_set):
    normalized_file_set = {os.path.normpath(p) for p in (file_set or [])}
    context_lines = []

    normalized_ast_map = {}
    for f, tags in (ast_map or {}).items():
        norm_f = os.path.normpath(f)
        normalized_ast_map.setdefault(norm_f, [])
        if tags:
            normalized_ast_map[norm_f].extend(tags)

    def _get_doc_comment(lines, line_no, language):
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

    def _format_tag(tag, lines, language):
        kind = tag.get("kind", "symbol").capitalize()
        name = tag.get("name", "?")
        line = tag.get("line")
        parent = tag.get("parent")
        line_part = f" (line {line})" if line else ""
        parent_part = f" in `{parent}`" if parent else ""
        comment = _get_doc_comment(lines, line, language) if lines else ""
        comment_part = comment if comment else "(no comment)"
        return f"- [{kind}] `{name}`{line_part}{parent_part} -> {comment_part}"

    def _emit_file(path_key, tags):
        if not tags:
            context_lines.append(f"File {path_key}:\n# (no symbols)")
            return
        lines = None
        language = _detect_language(path_key)
        if os.path.exists(path_key):
            try:
                with open(path_key, "r", encoding="utf-8") as fh:
                    lines = fh.read().splitlines()
            except Exception:
                lines = None
        tag_lines = [_format_tag(t, lines, language) for t in tags]
        context_lines.append(f"File {path_key}:\n" + "\n".join(tag_lines))

    if normalized_file_set:
        ast_paths = list(normalized_ast_map.keys())
        emitted = set()
        for norm_f in sorted(normalized_file_set):
            candidates = []
            if norm_f in normalized_ast_map:
                candidates = [norm_f]
            else:
                norm_tail = norm_f
                for p in ast_paths:
                    if p.endswith(norm_tail) or os.path.basename(p) == os.path.basename(norm_tail):
                        candidates.append(p)
            if not candidates:
                candidates = [norm_f]

            for cand in candidates:
                if cand in emitted:
                    continue
                emitted.add(cand)
                _emit_file(cand, normalized_ast_map.get(cand, []))
        return "\n".join(context_lines)

    for norm_f, tags in normalized_ast_map.items():
        _emit_file(norm_f, tags)

    return "\n".join(context_lines)
