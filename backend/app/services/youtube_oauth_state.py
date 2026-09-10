from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.models import OAuthState


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_oauth_state(db: Session, user_id: uuid.UUID) -> tuple[str, str]:
    state = secrets.token_urlsafe(48)
    browser_nonce = secrets.token_urlsafe(32)
    row = OAuthState(
        state_hash=_hash(state),
        user_id=user_id,
        browser_binding_hash=_hash(browser_nonce),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=settings.oauth_state_ttl_seconds),
    )
    db.add(row)
    db.commit()
    return state, browser_nonce


def consume_oauth_state(
    db: Session, state: str, *, browser_binding: str | None = None
) -> uuid.UUID:
    if not state or len(state) > 512:
        raise ValueError("OAuth state is invalid or expired. Please try connecting again.")
    row = (
        db.query(OAuthState)
        .filter(OAuthState.state_hash == _hash(state))
        .with_for_update()
        .first()
    )
    now = datetime.now(timezone.utc)
    if row is None or row.expires_at <= now:
        if row is not None:
            db.delete(row)
            db.commit()
        raise ValueError("OAuth state is invalid or expired. Please try connecting again.")
    if not browser_binding or not secrets.compare_digest(row.browser_binding_hash, _hash(browser_binding)):
        raise ValueError("OAuth state does not match the browser session. Please try connecting again.")
    user_id = row.user_id
    db.delete(row)
    db.commit()
    return user_id


def purge_expired_oauth_states(db: Session) -> int:
    count = (
        db.query(OAuthState)
        .filter(OAuthState.expires_at < datetime.now(timezone.utc))
        .delete(synchronize_session=False)
    )
    db.commit()
    return count
