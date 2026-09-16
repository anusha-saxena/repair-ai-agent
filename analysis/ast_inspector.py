import ast
import sys
import json

class ASTInspector:
    def __init__(self, file_path):
        self.file_path = file_path
        with open(file_path, "r", encoding="utf-8") as f:
            self.source = f.read()
        self.tree = ast.parse(self.source)
    def detect_shared_state(self):
        shared_variables = set()
        for node in self.tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        shared_variables.add(target.id)
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Global):
                for name in node.names:
                    shared_variables.add(name)
        return list(shared_variables)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    file_path = sys.argv[1]
    if "::" in file_path:
        file_path = file_path.split("::")[0]     
    inspector = ASTInspector(file_path)
    suspicious_vars = inspector.detect_shared_state()  
    output = {
        "file": file_path,
        "suspicious_shared_state": suspicious_vars
    }
    print(json.dumps(output, indent=2))