"""Read only the baked-in demo catalog."""
import json
import re
from pathlib import Path


def load_demos(root):
    demos = {}
    root = Path(root).resolve()
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or folder.is_symlink():
            continue
        manifest = folder / "demo.json"
        if manifest.is_symlink():
            raise ValueError("Demo manifests must not be symlinks")
        data = json.loads(manifest.read_text(encoding="utf-8"))
        demo_id = data["id"]
        if not re.fullmatch(r"[a-z][a-z0-9_]*", demo_id) or demo_id != folder.name or demo_id in demos:
            raise ValueError("Invalid or duplicate demo ID")
        file_name, test_name = data["target_test"].split("::", 1)
        if Path(file_name).name != file_name or not re.fullmatch(r"test_[a-zA-Z0-9_]+", test_name):
            raise ValueError("Demo target must be a file and one test name")
        source = folder / file_name
        if source.is_symlink() or not source.is_file():
            raise ValueError("Invalid demo source")
        public = {key: data[key] for key in ("id", "display_name", "description", "target_test", "category_hint")}
        if not all(isinstance(value, str) for value in public.values()):
            raise ValueError("Demo metadata must contain strings")
        demos[demo_id] = {"manifest": public, "source": source, "test_name": test_name}
    if not demos:
        raise ValueError("Demo catalog is empty")
    return demos
