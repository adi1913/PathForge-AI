"""Write the API's OpenAPI document to apps/web/openapi.json (the frontend generates its types from it).

Run from apps/api:  .venv/bin/python scripts/export_openapi.py
Then, in apps/web:  npm run gen:types
"""

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("QDRANT_LOCAL_PATH", ":memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app

TARGET = Path(__file__).resolve().parents[2] / "web" / "openapi.json"

if __name__ == "__main__":
    TARGET.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")
    print(f"wrote {TARGET}")
