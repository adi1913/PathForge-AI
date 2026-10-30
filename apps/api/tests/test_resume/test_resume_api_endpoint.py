"""
Upload resume -> Resume parser -> Section extraction -> Skill extraction
-> Skill normalization -> Evidence generation -> UserSkill persistence
-> Structured response. Verifies actual database rows, not just the
HTTP response. No mocking of the analyzer itself — only what's
explicitly appropriate (nothing here needs an LLM; DEMO_MODE runs the
real rule-based extractor).
"""

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_MODE", "true")
    db_path = tmp_path / "resume_e2e_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("QDRANT_LOCAL_PATH", ":memory:")

    import app.db.session as session_module

    importlib.reload(session_module)
    session_module.Base.metadata.create_all(bind=session_module.engine)
    yield
    session_module.Base.metadata.drop_all(bind=session_module.engine)


def _fresh_app():
    import app.main as main_module

    importlib.reload(main_module)
    return main_module.app


def _seed_user_and_skills():
    import app.db.session as session_module
    from app.models.skill import Skill
    from app.models.user import User

    db = session_module.SessionLocal()
    for slug, name in [("python", "Python"), ("sql", "SQL"), ("rag", "RAG"), ("fastapi", "FastAPI")]:
        db.add(Skill(slug=slug, name=name))
    user = User(email="e2e-resume@example.com", password_hash="hashed")
    db.add(user)
    db.commit()
    user_id = user.id
    db.close()
    return user_id


def test_resume_analyze_end_to_end_via_text():
    user_id = _seed_user_and_skills()

    with TestClient(_fresh_app()) as client:
        response = client.post(
            "/api/resume/analyze",
            data={
                "text": (
                    "Jane Smith\njane@example.com\n\n"
                    "SKILLS\nPython, SQL\n\n"
                    "PROJECTS\nRAG Chatbot\nBuilt a RAG chatbot using FastAPI.\n"
                ),
                "user_id": user_id,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["user_skills_created"] >= 2
    skill_names = {s["normalized_skill"] for s in body["analysis"]["skills"]}
    assert "python" in skill_names
    assert "sql" in skill_names

    # Verify real database rows, not just the HTTP response shape.
    import app.db.session as session_module
    from app.models.document import Document, DocumentChunk
    from app.models.skill import UserSkill

    db = session_module.SessionLocal()
    doc = db.query(Document).filter_by(id=body["document_id"]).one()
    assert (doc.document_metadata or {}).get("document_type") == "resume"
    assert db.query(DocumentChunk).filter_by(document_id=doc.id).count() > 0
    user_skills = db.query(UserSkill).filter_by(user_id=user_id).all()
    assert len(user_skills) == body["user_skills_created"]
    assert all(us.evidence for us in user_skills)
    db.close()


def test_resume_analyze_via_pdf_upload():
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(text="Jane Smith")
    pdf.ln()
    pdf.cell(text="SKILLS")
    pdf.ln()
    pdf.cell(text="Python, SQL")
    pdf_bytes = bytes(pdf.output())

    with TestClient(_fresh_app()) as client:
        response = client.post(
            "/api/resume/analyze",
            files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["analysis"]["parser_metadata"]["parser_used"] == "PDFResumeParser"


def test_resume_analyze_rejects_empty_request():
    with TestClient(_fresh_app()) as client:
        response = client.post("/api/resume/analyze", data={})
    assert response.status_code == 422


def test_resume_analyze_rejects_oversized_text():
    # Starlette's own multipart form-field size guard (1MB default) fires
    # before our handler runs for a field this large — a 400 from that
    # layer is a real rejection too, not a bypass of the size limit.
    with TestClient(_fresh_app()) as client:
        response = client.post("/api/resume/analyze", data={"text": "x" * 6_000_000})
    assert response.status_code in (400, 413)


def test_resume_analyze_rejects_oversized_file():
    # The file-upload path streams to a spooled temp file rather than
    # hitting Starlette's inline form-field cap, so this exercises our
    # own RESUME_MAX_UPLOAD_BYTES check specifically.
    with TestClient(_fresh_app()) as client:
        response = client.post("/api/resume/analyze", files={"file": ("big.txt", b"x" * 6_000_000, "text/plain")})
    assert response.status_code == 413


def test_resume_analyze_scanned_pdf_returns_clear_warning_not_failure():
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()  # blank — no extractable text, simulating a scanned image
    pdf_bytes = bytes(pdf.output())

    with TestClient(_fresh_app()) as client:
        response = client.post(
            "/api/resume/analyze",
            files={"file": ("scanned.pdf", pdf_bytes, "application/pdf")},
        )

    assert response.status_code == 200
    body = response.json()
    assert any("no extractable text" in w.lower() for w in body["analysis"]["warnings"])
    assert body["analysis"]["skills"] == []
