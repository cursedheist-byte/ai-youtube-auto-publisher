import os
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/test")
os.environ.setdefault("JWT_SECRET", "test-secret")

from app.models import UploadStatus


def test_upload_statuses_match_required_lifecycle():
    assert [s.value for s in UploadStatus] == ["pending", "uploading", "success", "failed", "uncertain"]
