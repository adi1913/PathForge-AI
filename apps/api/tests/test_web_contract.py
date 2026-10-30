"""The web app's typed client is generated from apps/web/openapi.json; fail when the API drifts from it."""

import json
from pathlib import Path

import pytest

from app.main import app

SNAPSHOT = Path(__file__).resolve().parents[2] / "web" / "openapi.json"
REFRESH = "Run `.venv/bin/python scripts/export_openapi.py` in apps/api, then `npm run gen:types` in apps/web."


@pytest.mark.skipif(not SNAPSHOT.exists(), reason="apps/web is not present in this checkout")
def test_web_openapi_snapshot_matches_the_api():
    snapshot = json.loads(SNAPSHOT.read_text())
    current = json.loads(json.dumps(app.openapi()))
    assert snapshot == current, f"apps/web/openapi.json is stale. {REFRESH}"


@pytest.mark.skipif(not SNAPSHOT.exists(), reason="apps/web is not present in this checkout")
def test_web_contract_exposes_no_answer_key_fields():
    text = SNAPSHOT.read_text()
    for forbidden in ("expected_answer", "evaluation_rubric", "correct_option", "answer_key"):
        assert forbidden not in text
