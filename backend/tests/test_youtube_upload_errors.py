import json
from unittest.mock import Mock
from googleapiclient.errors import HttpError
from app.services.youtube_upload_service import _format_youtube_http_error, _youtube_http_error_details

def test_youtube_http_error_details_and_safe_formatting():
    response = Mock(status=400)
    payload = {
        "error": {
            "code": 400,
            "reason": "badRequest",
            "message": "The request is invalid",
            "errors": [{"reason": "invalidCategoryId", "message": "Invalid category ID"}],
        }
    }
    exc = HttpError(response, json.dumps(payload).encode())
    code, reason, message, details = _youtube_http_error_details(exc)
    assert (code, reason, message) == ("400", "badRequest", "The request is invalid")
    assert details == [("invalidCategoryId", "Invalid category ID")]
    formatted = _format_youtube_http_error(exc)
    assert "invalidCategoryId" in formatted
    assert "Invalid category ID" in formatted
    assert "token" not in formatted.lower()

def test_youtube_error_redacts_credentials():
    response = Mock(status=400)
    exc = HttpError(response, b'{"error":{"message":"Bearer secret-token api_key=secret-key"}}')
    formatted = _format_youtube_http_error(exc)
    assert "secret-token" not in formatted
    assert "secret-key" not in formatted
    assert "[REDACTED]" in formatted
