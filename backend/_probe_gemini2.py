import requests
import time
from app.config import settings

url = "https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent"
text = 'Reply with JSON: {"ok": true}'

r = requests.post(
    url,
    params={"key": settings.gemini_api_key},
    json={"contents": [{"parts": [{"text": text}]}],
          "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"}},
    timeout=45,
)
print("with json config:", r.status_code)

time.sleep(3)

r2 = requests.post(
    url,
    params={"key": settings.gemini_api_key},
    json={"contents": [{"parts": [{"text": text}]}]},
    timeout=45,
)
print("without json config:", r2.status_code)
if r2.status_code != 200:
    print(r2.text[:300])
