"""Provider-neutral AI metadata generation for YouTube uploads."""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import requests

from app.config import settings


class AIProviderError(Exception):
    """A user-safe AI metadata generation failure."""
    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class VideoContext:
    filename: str
    source_name: str
    mime_type: str
    size_bytes: int | None = None
    duration_seconds: int | None = None
@dataclass(frozen=True)
class SEOMetadata:
    title: str
    description: str
    tags: list[str]
    hashtags: list[str]
    category_id: str = "22"


class AIProvider(ABC):
    @abstractmethod
    def generate_metadata(self, context: VideoContext) -> SEOMetadata:
        raise NotImplementedError


def _redact_api_key(message: str) -> str:
    """Remove configured AI API keys from error messages/URLs."""
    keys = [
        getattr(settings, "gemini_api_key", ""),
        getattr(settings, "openrouter_api_key", ""),
    ]
    for key in keys:
        if key and key in message:
            message = message.replace(key, "[REDACTED]")
    return message


def _extract_json_object(text: str) -> dict:
    """Extract a JSON object even if the model wraps it in markdown/reasoning text."""
    text = (text or "").strip()

    if "```" in text:
        for part in text.split("```"):
            candidate = part.strip()
            if candidate.lower().startswith("json"):
                candidate = candidate[4:].strip()
            if candidate.startswith("{") and candidate.endswith("}"):
                try:
                    value = json.loads(candidate)
                    if isinstance(value, dict):
                        return value
                except json.JSONDecodeError:
                    pass

    start = text.find("{")
    if start >= 0:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    value = json.loads(text[start:index + 1])
                    if isinstance(value, dict):
                        return value
                    break

    raise ValueError("AI response did not contain a valid JSON object.")




_YOUTUBE_CATEGORY_IDS = {
    "film & animation": "1", "autos & vehicles": "2", "music": "10",
    "pets & animals": "15", "sports": "17", "travel & events": "19",
    "gaming": "20", "people & blogs": "22", "comedy": "23",
    "entertainment": "24", "news & politics": "25", "howto & style": "26",
    "education": "27", "science & technology": "28", "nonprofits & activism": "29",
}


def _normalize_category_id(value) -> str:
    # Return a numeric category ID, falling back safely for unknown values.
    default = str(settings.youtube_default_category_id).strip()
    candidate = str(value or "").strip()
    if candidate.isdigit():
        return candidate
    normalized = " ".join(candidate.casefold().replace("–", "-").split())
    normalized = normalized.replace(" and ", " & ").replace("how-to", "howto").replace("how to", "howto")
    return _YOUTUBE_CATEGORY_IDS.get(normalized, default)


def _metadata_from_data(data: dict) -> SEOMetadata:
    """Validate and normalize provider output into the existing metadata schema."""
    title = str(data.get("title") or "").strip()
    description = str(data.get("description") or "").strip()
    tags = _clean_list(data.get("tags"))
    hashtags = _clean_list(data.get("hashtags"), limit=15)
    category_id = _normalize_category_id(data.get("category_id"))

    hashtags = [
        h if h.startswith("#") else f"#{h.replace(' ', '')}"
        for h in hashtags
    ]
    hashtags = _clean_list(hashtags, limit=8)

    if not title or not description:
        raise AIProviderError("AI returned incomplete YouTube metadata.", retryable=False)
    if len(title) > 100:
        raise AIProviderError("AI returned a title longer than YouTube allows.", retryable=False)
    if len(description) > 5000:
        raise AIProviderError("AI returned a description longer than YouTube allows.", retryable=False)
    if sum(len(tag) + 1 for tag in tags) > 500:
        raise AIProviderError("AI returned too many tags for YouTube.", retryable=False)
    # Category names and unknown values have already been safely normalized to
    # a numeric configured default; valid SEO must not fail on this field.
    if hashtags:
        description = f"{description}\n\n{' '.join(hashtags)}"
    if len(description) > 5000:
        raise AIProviderError(
            "AI metadata plus hashtags exceeds YouTube's description limit.",
            retryable=False,
        )
    return SEOMetadata(
        title=title,
        description=description,
        tags=tags,
        hashtags=hashtags,
        category_id=category_id,
    )


def _clean_list(value, limit: int = 30) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        text = str(item).strip()
        if text and text not in result:
            result.append(text[:100])
        if len(result) >= limit:
            break
    return result


class GeminiProvider(AIProvider):
    def generate_metadata(self, context: VideoContext) -> SEOMetadata:
        if not settings.gemini_api_key:
            raise AIProviderError("GEMINI_API_KEY is not configured on the server.")

        prompt = f"""You are an expert YouTube SEO editor. Generate metadata only from the textual file context below. Do not claim to have watched or analyzed the video. Do not invent people, events, locations, gameplay moments, dialogue, or other facts that are not present in this context.
Return JSON ONLY with exactly these keys: title, description, tags, hashtags, category_id. category_id MUST be a numeric YouTube category ID (not a name). Title <= 100 characters; description should naturally explain what viewers see; provide 10-20 relevant tags and 5-8 relevant hashtags.
Use concise, natural metadata. Keep title <= 100 characters. Keep tags as short phrases.
Do not invent names, locations, events, dialogue, brands, people, or details. Create metadata specific to this video, avoiding generic titles, clickbait, and keyword stuffing.

Filename: {context.filename}
Source folder: {context.source_name}
MIME type: {context.mime_type}
Size bytes: {context.size_bytes}
Duration seconds: {context.duration_seconds}
"""
        models = [settings.gemini_model]
        fallback = settings.gemini_fallback_model
        if fallback and fallback not in models:
            models.append(fallback)
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"},
        }
        last_error: AIProviderError | None = None
        data: dict | None = None
        for model in models:  # primary first, then fallback (at most one fallback model)
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            for attempt in range(3):  # max 3 Gemini attempts per model
                response = None
                try:
                    response = requests.post(
                        url,
                        params={"key": settings.gemini_api_key},
                        json=payload,
                        timeout=settings.ai_request_timeout_seconds,
                    )
                    response.raise_for_status()
                    body = response.json()
                    parts = body["candidates"][0]["content"]["parts"]
                    text = next(
                        (p.get("text", "") for p in parts if not p.get("thought")),
                        "",
                    )
                    data = json.loads(text)
                    break
                except (requests.RequestException, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    status_code = getattr(response, "status_code", None)
                    retryable = status_code in (408, 429) or (status_code is not None and status_code >= 500)
                    last_error = AIProviderError(
                        f"Gemini metadata generation failed: {_redact_api_key(str(exc))}",
                        retryable=retryable,
                    )
                    # Only transient 5xx/timeout/429 errors are worth retrying or
                    # falling back; never for permanent failures (400/401/403, malformed).
                    if not retryable:
                        raise last_error from exc
                    if attempt < 2:
                        time.sleep(2 ** (attempt + 1))  # 2s, then 4s
            if data is not None:
                break

        if data is None:
            raise last_error or AIProviderError("Gemini metadata generation failed.", retryable=False)

        return _metadata_from_data(data)



class OpenRouterProvider(AIProvider):
    """OpenRouter provider using its OpenAI-compatible chat completions API."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key
    def generate_metadata(self, context: VideoContext) -> SEOMetadata:
        api_key = (self.api_key if self.api_key is not None else settings.openrouter_api_key).strip()
        model = settings.openrouter_model.strip()
        base_url = settings.openrouter_base_url.strip().rstrip("/")

        if not api_key:
            raise AIProviderError(
                "OPENROUTER_API_KEY is not configured on the server.",
                retryable=False,
            )

        prompt = f"""You are an expert YouTube SEO editor. Generate metadata only from the textual file context below. Do not claim to have watched or analyzed the video. Do not invent people, events, locations, gameplay moments, dialogue, or other facts that are not present in this context.
Return JSON ONLY with exactly these keys: title, description, tags, hashtags, category_id. category_id MUST be a numeric YouTube category ID (not a name). Title <= 100 characters; description should naturally explain what viewers see; provide 10-20 relevant tags and 5-8 relevant hashtags.
Use concise, natural metadata. Keep title <= 100 characters. Keep tags as short phrases.
Do not invent names, locations, events, dialogue, brands, people, or details. Create metadata specific to this video, avoiding generic titles, clickbait, and keyword stuffing.

Filename: {context.filename}
Source folder: {context.source_name}
MIME type: {context.mime_type}
Size bytes: {context.size_bytes}
Duration seconds: {context.duration_seconds}
"""

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.4,
            "max_tokens": 2000,
            "response_format": {"type": "json_object"},
        }
        url = f"{base_url}/chat/completions"
        last_error: AIProviderError | None = None

        for attempt in range(3):
            response = None
            try:
                response = requests.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "http://localhost:5173",
                        "X-Title": "AI YouTube Auto Publisher",
                    },
                    json=payload,
                    timeout=settings.ai_request_timeout_seconds,
                )
                response.raise_for_status()
                body = response.json()
                text = body["choices"][0]["message"].get("content", "") or ""
                if isinstance(text, list):
                    text = "".join(
                        str(part.get("text", ""))
                        for part in text
                        if isinstance(part, dict)
                    )
                return _metadata_from_data(_extract_json_object(str(text)))

            except (
                requests.RequestException,
                KeyError,
                IndexError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ) as exc:
                status_code = getattr(response, "status_code", None)
                retryable = (
                    isinstance(exc, requests.Timeout)
                    or status_code in (408, 429)
                    or (status_code is not None and status_code >= 500)
                )
                last_error = AIProviderError(
                    f"OpenRouter metadata generation failed: {_redact_api_key(str(exc))}",
                    retryable=retryable,
                )
                if not retryable:
                    raise last_error from exc
                if attempt < 2:
                    time.sleep(2 ** (attempt + 1))

        raise last_error or AIProviderError(
            "OpenRouter metadata generation failed.",
            retryable=False,
        )

def get_ai_provider(user=None) -> AIProvider:
    # Own-Credentials users always use their own OpenRouter key. This keeps the
    # server/developer key and its billing limits out of their upload flow.
    if user is not None:
        from app.services.access_service import credential_values
        if getattr(user.access_mode, "value", user.access_mode) == "own":
            own_key = credential_values(user)[2]
            if not own_key:
                raise AIProviderError("Your OpenRouter API key is not configured. Update your own credentials in Setup.", retryable=False)
            return OpenRouterProvider(own_key)

    provider = settings.ai_provider.strip().lower()
    if provider == "gemini":
        return GeminiProvider()
    if provider == "openrouter":
        from app.services.access_service import credential_values
        return OpenRouterProvider(credential_values(user)[2] if user is not None else None)
    raise AIProviderError(f"Unsupported AI_PROVIDER '{settings.ai_provider}'.")
