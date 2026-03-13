import json
import os

def get_procedure(file_path = "procedure.json"):
    with open(file_path, "r") as f:
        return json.load(f)

def save_procedure(procedure, file_path):
    with open(file_path, "w") as f:
        json.dump(procedure, f, indent=4)

def save_json(data, file_path):
    with open(file_path, "w") as f:
        json.dump(data, f, indent=4)

def load_json(file_path):
    with open(file_path, "r") as f:
        return json.load(f)

def init_procedure_files(procedure):
    for step_id, data in procedure.items():
        for filename in data['filenames']:
            with open(filename, "w") as f:
                pass
            f.close()

def save_project(project_id, project_path):
    appdata_root = _appdata_root()
    projects_path = os.path.join(appdata_root, "projects.json")

    if os.path.exists(projects_path):
        with open(projects_path, "r", encoding="utf-8") as p:
            try:
                projects = json.load(p)
            except Exception:
                projects = []
    else:
        projects = []

    projects.append({
        "id": project_id,
        "project_root": project_path,
    })

    with open(projects_path, "w", encoding="utf-8") as p:
        json.dump(projects, p, indent=2)


def load_projects():
    appdata_root = _appdata_root()
    projects_path = os.path.join(appdata_root, "projects.json")
    if not os.path.exists(projects_path):
        return []
    try:
        with open(projects_path, "r", encoding="utf-8") as p:
            data = json.load(p)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def delete_project(project_id):
    appdata_root = _appdata_root()
    projects_path = os.path.join(appdata_root, "projects.json")
    if not os.path.exists(projects_path):
        return False
    try:
        with open(projects_path, "r", encoding="utf-8") as p:
            projects = json.load(p)
        if not isinstance(projects, list):
            return False
        new_projects = [p for p in projects if p.get("id") != project_id]
        with open(projects_path, "w", encoding="utf-8") as p:
            json.dump(new_projects, p, indent=2)
        return True
    except Exception:
        return False


def _appdata_root():
    appdata_root = os.path.join(os.getenv("APPDATA", ""), "SVCA")
    os.makedirs(appdata_root, exist_ok=True)
    return appdata_root


def get_project_id_by_root(project_root):
    if not project_root:
        return None
    project_root_abs = os.path.abspath(project_root)
    for project in load_projects():
        root = os.path.abspath(project.get("project_root", ""))
        if root == project_root_abs:
            return project.get("id")
    return None



def save_ast_map(project_id, ast_map):
    if not project_id:
        return None
    appdata_root = _appdata_root()
    ast_map_path = os.path.join(appdata_root, f"{project_id}.ast_map.json")
    try:
        with open(ast_map_path, "w", encoding="utf-8") as f:
            json.dump(ast_map, f, indent=2)
        return ast_map_path
    except Exception:
        return None


def load_ast_map(project_id):
    if not project_id:
        return None
    appdata_root = _appdata_root()
    ast_map_path = os.path.join(appdata_root, f"{project_id}.ast_map.json")
    if not os.path.exists(ast_map_path):
        return None
    try:
        with open(ast_map_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def add_file_to_project(project_root, relative_path):
    if not project_root:
        return False, "Project root is missing.", None
    if not relative_path:
        return False, "File path is empty.", None

    project_root_abs = os.path.abspath(project_root)
    rel = relative_path.strip().lstrip("/\\")
    file_path = os.path.abspath(os.path.join(project_root_abs, rel))

    if not file_path.startswith(project_root_abs):
        return False, "Invalid file path.", None
    if os.path.exists(file_path):
        return False, "File already exists.", file_path

    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("")
        return True, "File created.", file_path
    except Exception as exc:
        return False, f"Failed to create file: {exc}", None


def delete_file_from_project(project_root, relative_path):
    if not project_root:
        return False, "Project root is missing."
    if not relative_path:
        return False, "File path is empty."

    project_root_abs = os.path.abspath(project_root)
    rel = relative_path.strip().lstrip("/\\")
    file_path = os.path.abspath(os.path.join(project_root_abs, rel))

    if not file_path.startswith(project_root_abs):
        return False, "Invalid file path."
    if not os.path.exists(file_path):
        return False, "File not found."

    try:
        os.remove(file_path)
        return True, "File deleted."
    except Exception as exc:
        return False, f"Failed to delete file: {exc}"
