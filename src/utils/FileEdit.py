def edit(lines, content, line_n):
        print("editing")
        lines[line_n - 1] = content + "\n"

def delete(lines, line_n):
    lines[line_n - 1] = ""

def insert(lines, content, line_n):
    lines.insert(line_n - 1, content + "\n")

def apply_edits(edits):
    for f in edits.keys():
        with open(f, 'r', encoding='utf-8') as file:
            lines = file.readlines()

        for a in self.edits[f]:
            if (a[0] == 'Edit'):
                self.edit(lines, a[2], a[1])
            elif (a[0] == 'Insert'):
                self.insert(lines, a[2], a[1])
            elif (a[0] == 'Delete'):
                self.delete(lines, a[2], a[1])

        with open(f, 'w', encoding='utf-8') as file:
            file.writelines(lines)