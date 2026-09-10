'Text-only metadata generation from existing Drive file context.'
from __future__ import annotations
from app.services.ai_provider import VideoContext

def generate_video_metadata(
    provider,
    *,
    filename: str,
    source_name: str,
    mime_type: str,
    size_bytes: int | None,
    duration_seconds: int | None,
):
    # Generate metadata without downloading or inspecting the video.
    return provider.generate_metadata(
        VideoContext(filename, source_name, mime_type, size_bytes, duration_seconds)
    )
