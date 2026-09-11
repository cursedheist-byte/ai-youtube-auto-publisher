"""
Prints SAFE metadata (never key/credential values) for a service-account JSON
so the known-good local key can be compared with the Render deployment log.

Usage:
    python -m app.drive_key_diag [path-to-json]

Without an argument it uses GOOGLE_SERVICE_ACCOUNT_JSON_PATH from settings.
"""
import json
import sys

from app.config import settings
from app.services.drive_service import _key_metadata


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else settings.google_service_account_json_path
    print(f"path: {path}")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read().strip()
    except OSError as exc:
        print(f"file_readable: False ({exc.__class__.__name__})")
        return
    print(f"file_size_bytes: {len(raw.encode('utf-8'))}")
    try:
        info = json.loads(raw)
        print("json_parse_ok: True")
    except json.JSONDecodeError as exc:
        print(f"json_parse_ok: False (position {exc.pos})")
        return
    if not isinstance(info, dict):
        print("top_level_type:", type(info).__name__)
        return
    key = info.get("private_key")
    print("top_level_keys:", sorted(k for k in info if k != "private_key"))
    print("private_key_exists:", key is not None)
    print("private_key_metadata:", json.dumps(_key_metadata(key), default=str))


if __name__ == "__main__":
    main()
