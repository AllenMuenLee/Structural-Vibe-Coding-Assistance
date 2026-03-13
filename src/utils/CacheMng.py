import json
import os
from platformdirs import user_cache_dir


def _cache_path():
    cache_root = user_cache_dir("SVCA")
    os.makedirs(cache_root, exist_ok=True)
    return os.path.join(cache_root, "cache.json")


def load_cache():
    path = _cache_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def save_cache(data):
    path = _cache_path()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def save_current_project_id(project_id):
    cache = load_cache()
    cache["current_project_id"] = project_id
    save_cache(cache)
