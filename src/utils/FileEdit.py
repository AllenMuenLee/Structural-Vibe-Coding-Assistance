def edit(lines, content, line_n):
    print("editing")
    lines[line_n - 1] = content + "\n"

def delete(lines, line_n):
    lines[line_n - 1] = ""

def insert(lines, content, line_n):
    lines.insert(line_n - 1, content + "\n")

def apply_edits(edits):
    for f, actions in (edits or {}).items():
        with open(f, 'r', encoding='utf-8') as file:
            lines = file.readlines()

        for action in actions:
            if not action or len(action) < 2:
                continue
            kind = action[0]
            line_n = action[1]
            content = action[2] if len(action) > 2 else ""
            if kind == 'Edit':
                edit(lines, content, line_n)
            elif kind == 'Insert':
                insert(lines, content, line_n)
            elif kind == 'Delete':
                delete(lines, line_n)

        with open(f, 'w', encoding='utf-8') as file:
            file.writelines(lines)
