# Credential mode, access-code, and race-safe admin quota helpers"
from __future__ import annotations
import hashlib, secrets
from datetime import date, datetime
import requests
from zoneinfo import ZoneInfo
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.config import settings
from app.models import AccessCode, AccessCodeStatus, AccessGrant, AccessMode, DailyUploadQuota, User, UserCredential
from app.services.token_crypto import encrypt_token, decrypt_token

def code_digest(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()

def generate_access_code(db: Session, expires_at=None):
    code = secrets.token_urlsafe(32)
    row = AccessCode(code_hash=code_digest(code), expires_at=expires_at, channel_limit=1, daily_video_limit=2)
    db.add(row); db.commit(); db.refresh(row)
    return code, row

def validate_user_credentials(google_client_id: str, google_client_secret: str, openrouter_api_key: str) -> None:
    # Validate the OAuth client and API key before persisting them. No video or
    # paid model request is made during this check."
    client_id = (google_client_id or "").strip()
    client_secret = (google_client_secret or "").strip()
    api_key = (openrouter_api_key or "").strip()
    if not client_id or not client_secret or not api_key:
        raise ValueError("Wrong credentials: please provide Google Client ID, Google Client Secret, and OpenRouter API key.")

    try:
        google = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": "credential-validation-only",
                "grant_type": "authorization_code",
                "redirect_uri": settings.google_oauth_redirect_uri,
            },
            timeout=10,
        )
    except requests.RequestException as exc:
        raise ValueError("Google credentials could not be checked right now. Please try again.") from exc
    if google.status_code in (400, 401) and "invalid_client" in google.text.lower():
        raise ValueError("Wrong Google credentials: the Client ID or Client Secret is invalid.")
    if google.status_code >= 500:
        raise ValueError("Google credentials could not be checked right now. Please try again.")

    try:
        router = requests.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
    except requests.RequestException as exc:
        raise ValueError("OpenRouter credentials could not be checked right now. Please try again.") from exc
    if router.status_code in (401, 403):
        raise ValueError("Wrong OpenRouter API key. Please check the key and try again.")
    if router.status_code >= 500:
        raise ValueError("OpenRouter credentials could not be checked right now. Please try again.")
    if router.status_code >= 400:
        raise ValueError("OpenRouter rejected this API key. Please check it and try again.")


def save_user_credentials(db: Session, user: User, google_client_id=None, google_client_secret=None, openrouter_api_key=None):
    row = user.credentials or UserCredential(user_id=user.id)
    if google_client_id is not None: row.google_client_id = google_client_id.strip() or None
    if google_client_secret is not None: row.google_client_secret = encrypt_token(google_client_secret.strip()) if google_client_secret.strip() else None
    if openrouter_api_key is not None: row.openrouter_api_key = encrypt_token(openrouter_api_key.strip()) if openrouter_api_key.strip() else None
    db.add(row); user.access_mode = AccessMode.OWN; db.commit(); db.refresh(row)
    return row

def redeem_access_code(db: Session, user: User, code: str):
    if user.access_grant is not None:
        raise ValueError("An active admin access grant already exists.")
    row = db.query(AccessCode).filter(AccessCode.code_hash == code_digest(code.strip())).with_for_update().first()
    now = datetime.now().astimezone()
    if row is None or row.status != AccessCodeStatus.UNUSED: raise ValueError("Invalid or already redeemed access code.")
    if row.expires_at and row.expires_at <= now: raise ValueError("This access code has expired.")
    row.status = AccessCodeStatus.REDEEMED; row.redeemed_at = now; row.redeemed_by_user_id = user.id
    db.add(AccessGrant(user_id=user.id, access_code_id=row.id, channel_limit=row.channel_limit, daily_video_limit=row.daily_video_limit))
    user.access_mode = AccessMode.ADMIN
    db.commit(); return row

def credential_values(user: User):
    # Admin accounts use server credentials; own-credential accounts never fall back to them.
    if user.access_mode == AccessMode.ADMIN:
        return settings.google_oauth_client_id, settings.google_oauth_client_secret, settings.openrouter_api_key
    row = user.credentials
    if not row:
        return "", "", ""
    try: secret = decrypt_token(row.google_client_secret) if row.google_client_secret else None
    except Exception: secret = None
    try: key = decrypt_token(row.openrouter_api_key) if row.openrouter_api_key else None
    except Exception: key = None
    if row.google_client_id and secret and key:
        return row.google_client_id, secret, key
    return "", "", ""

def quota_date(): return datetime.now(ZoneInfo(settings.scheduler_timezone)).date()

def reserve_admin_upload(db: Session, user: User):
    if user.access_mode != AccessMode.ADMIN: return None
    grant = user.access_grant
    limit = grant.daily_video_limit if grant else 2
    day = quota_date()
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"admin-upload:{user.id}:{day}"})
    quota = db.query(DailyUploadQuota).filter(DailyUploadQuota.user_id == user.id, DailyUploadQuota.quota_date == day).with_for_update().first()
    if quota is None: quota = DailyUploadQuota(user_id=user.id, quota_date=day); db.add(quota); db.flush()
    if quota.reserved_count >= limit: db.rollback(); raise ValueError("Admin Access users are limited to 2 successful uploads per calendar day.")
    quota.reserved_count += 1; db.commit(); return (user.id, day)

def finish_admin_upload(db: Session, reservation, success: bool):
    if not reservation: return
    user_id, day = reservation
    quota = db.query(DailyUploadQuota).filter(DailyUploadQuota.user_id == user_id, DailyUploadQuota.quota_date == day).with_for_update().one()
    if success: quota.successful_count += 1
    else: quota.reserved_count = max(0, quota.reserved_count - 1)
    db.commit()
