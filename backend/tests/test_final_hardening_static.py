import ast
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_upload_history_schema_contains_attempt_fields():
    source = (ROOT / "app" / "schemas.py").read_text()
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "UploadHistoryOut")
    names = {n.target.id for n in cls.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)}
    assert {"last_attempt_at", "youtube_privacy_status", "youtube_processing_status", "youtube_status_checked_at"} <= names


def test_oauth_state_is_server_backed_and_random():
    source = (ROOT / "app" / "services" / "youtube_oauth_state.py").read_text()
    assert "secrets.token_urlsafe(48)" in source
    assert "with_for_update()" in source
    assert "expires_at" in source
    assert "compare_digest" in source


def test_uncertain_upload_is_distinct_state():
    source = (ROOT / "app" / "models.py").read_text()
    assert 'UNCERTAIN = "uncertain"' in source
    upload_service = (ROOT / "app" / "services" / "upload_service.py").read_text()
    assert "UploadStatus.UNCERTAIN" in upload_service
