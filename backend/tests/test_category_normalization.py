import os
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/test")
os.environ.setdefault("JWT_SECRET", "test-secret")
from app.config import settings
from app.services.ai_provider import _normalize_category_id

def test_numeric_category_is_preserved():
    assert _normalize_category_id("24") == "24"

def test_category_name_mapping():
    assert _normalize_category_id("Entertainment") == "24"
    assert _normalize_category_id("People & Blogs") == "22"

def test_category_case_and_whitespace_variations():
    assert _normalize_category_id("  how To & Style  ") == "26"
    assert _normalize_category_id("People and Blogs") == "22"

def test_invalid_category_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "youtube_default_category_id", "22")
    assert _normalize_category_id("Not a YouTube category") == "22"

def test_missing_category_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "youtube_default_category_id", "27")
    assert _normalize_category_id(None) == "27"
