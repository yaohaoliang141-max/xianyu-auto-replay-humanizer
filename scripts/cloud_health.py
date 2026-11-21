"""Reject an HTTP-200 health response when the database is disconnected."""
import json
import sys
from urllib.request import urlopen


def main():
    try:
        port = int(sys.argv[1])
        with urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as response:
            payload = json.load(response)
        healthy = payload.get("success") is True and payload.get("data", {}).get("database") == "connected"
    except Exception:
        healthy = False
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
