import requests
from app.config import settings

url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent"
r = requests.post(
    url,
    params={"key": settings.gemini_api_key},
    json={"contents": [{"parts": [{"text": "Reply with JSON: {\"ok\": true}"}]}]},
    timeout=45,
)
print(r.status_code)
print(r.text[:800])
