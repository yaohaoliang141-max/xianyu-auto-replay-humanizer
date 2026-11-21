"""Load private runtime settings without exposing them; Compose env wins."""
import json
import os
from pathlib import Path
import runpy
import sys


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {"backend-web", "websocket", "scheduler"}:
        raise SystemExit("Expected backend-web, websocket, or scheduler")
    runtime = json.loads(Path("/run/xianyu/runtime-settings.json").read_text(encoding="utf-8"))["environment"]
    if not isinstance(runtime, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in runtime.items()):
        raise SystemExit("Invalid runtime environment format")
    container_env = dict(os.environ)
    os.environ.update(runtime)
    os.environ.update(container_env)
    root = Path("/app")
    service = root / sys.argv[1]
    os.chdir(service)
    sys.path[:0] = [str(service), str(root)]
    runpy.run_path(str(service / "main.py"), run_name="__main__")


if __name__ == "__main__":
    main()
