import os
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/test")
os.environ.setdefault("JWT_SECRET", "test-secret")

from app.services.ai_provider import _clean_list, VideoContext


def test_clean_list_deduplicates_and_limits():
    assert _clean_list(["a", "a", "", "b"]) == ["a", "b"]


def test_video_context_is_only_known_metadata():
    ctx = VideoContext("clip.mp4", "Minecraft Gameplay", "video/mp4", 100, 60)
    assert ctx.filename == "clip.mp4"
    assert ctx.source_name == "Minecraft Gameplay"
