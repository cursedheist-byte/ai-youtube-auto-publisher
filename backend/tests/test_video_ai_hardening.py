import os
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/test")
os.environ.setdefault("JWT_SECRET", "test-secret")
from unittest.mock import Mock, patch
from app.config import settings
from app.services.ai_provider import OpenRouterProvider, _extract_json_object, _metadata_from_data, _redact_api_key, VideoContext

def test_json_extraction_and_metadata_normalization():
    assert _extract_json_object('text ```json {"title":"A","description":"D"} ```') == {"title":"A","description":"D"}
    result = _metadata_from_data({"title":"Specific","description":"What happens","tags":["one","one"],"hashtags":["#One","two"],"category_id":"22"})
    assert result.tags == ["one"]
    assert result.hashtags == ["#One", "#two"]
    assert "#two" in result.description

def test_openrouter_request_is_text_only(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "secret")
    response = Mock(status_code=200)
    response.json.return_value = {"choices":[{"message":{"content":"{\"title\":\"Clip\",\"description\":\"Seen\",\"tags\":[],\"hashtags\":[],\"category_id\":\"22\"}"}}]}
    response.raise_for_status.return_value = None
    with patch("app.services.ai_provider.requests.post", return_value=response) as post:
        OpenRouterProvider().generate_metadata(VideoContext("clip.mp4", "source", "video/mp4", 11, 2))
    content = post.call_args.kwargs["json"]["messages"][0]["content"]
    assert isinstance(content, str)
    assert "Filename: clip.mp4" in content
    assert "Source folder: source" in content
    assert "image_url" not in str(post.call_args.kwargs["json"])
    assert "base64" not in str(post.call_args.kwargs["json"])

def test_retry_behavior(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "secret")
    response = Mock(status_code=500)
    response.raise_for_status.side_effect = __import__("requests").HTTPError("server")
    with patch("app.services.ai_provider.requests.post", return_value=response) as post, patch("app.services.ai_provider.time.sleep"):
        try:
            OpenRouterProvider().generate_metadata(VideoContext("clip.mp4", "source", "video/mp4", 11, 2))
        except Exception as exc:
            assert getattr(exc, "retryable", False)
    assert post.call_count == 3

def test_redaction():
    settings.openrouter_api_key = "secret-key"
    assert "secret-key" not in _redact_api_key("provider secret-key failure")

def test_own_credentials_never_fall_back_to_server_values(monkeypatch):
    from types import SimpleNamespace
    from cryptography.fernet import Fernet
    from app.services.access_service import credential_values
    from app.services.token_crypto import encrypt_token
    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "google_oauth_client_id", "server-google-id")
    monkeypatch.setattr(settings, "google_oauth_client_secret", "server-google-secret")
    monkeypatch.setattr(settings, "openrouter_api_key", "server-openrouter-key")
    own = SimpleNamespace(
        access_mode="own",
        credentials=SimpleNamespace(
            google_client_id="own-google-id",
            google_client_secret=encrypt_token("own-google-secret"),
            openrouter_api_key=encrypt_token("own-openrouter-key"),
        ),
    )
    assert credential_values(own) == ("own-google-id", "own-google-secret", "own-openrouter-key")

    incomplete = SimpleNamespace(
        access_mode="own",
        credentials=SimpleNamespace(
            google_client_id="own-google-id",
            google_client_secret=None,
            openrouter_api_key=None,
        ),
    )
    assert credential_values(incomplete) == ("", "", "")

def test_credential_validation_rejects_invalid_openrouter_key(monkeypatch):
    from app.services.access_service import validate_user_credentials
    google = Mock(status_code=400, text='{"error":"invalid_grant"}')
    router = Mock(status_code=401, text="unauthorized")
    monkeypatch.setattr("app.services.access_service.requests.post", lambda *args, **kwargs: google)
    monkeypatch.setattr("app.services.access_service.requests.get", lambda *args, **kwargs: router)
    import pytest
    with pytest.raises(ValueError, match="Wrong OpenRouter API key"):
        validate_user_credentials("google-id", "google-secret", "bad-key")
