import json

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
