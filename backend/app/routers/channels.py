import logging
import urllib.parse
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status, Cookie
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import AutomationSettings, Category, User, YouTubeChannel
from app.schemas import (
    AutomationSettingsOut,
    AutomationSettingsUpdate,
    ChannelWithSettingsOut,
    OAuthStartOut,
    YouTubeChannelOut,
    AutomationRunOut,
)
from app.services.youtube_oauth_state import purge_expired_oauth_states
from app.services.youtube_oauth_service import (
    YouTubeChannelError,
    build_authorization_url,
    disconnect_channel,
    exchange_code_for_credentials,
    fetch_channel_info,
    consume_state,
    store_channel_connection,
)

router = APIRouter(prefix="/api/channels", tags=["channels"])
logger = logging.getLogger("ai_yt_publisher.channels")


def _get_own_channel_or_404(db: Session, channel_id: uuid.UUID, user: User) -> YouTubeChannel:
    channel = db.get(YouTubeChannel, channel_id)
    if channel is None or channel.user_id != user.id:
        # Same 404 for "doesn't exist" and "not yours" -- never confirm another user's channel exists.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
    return channel


@router.get("", response_model=list[ChannelWithSettingsOut])
def list_my_channels(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    channels = db.query(YouTubeChannel).filter(YouTubeChannel.user_id == user.id).all()
    results = []
    for c in channels:
        s = c.settings
        if s is None:  # defensive -- should always exist, created alongside the channel
            s = AutomationSettings(channel_id=c.id, enabled=False, daily_upload_count=2)
            db.add(s)
            db.commit()
            db.refresh(s)
        results.append(
            ChannelWithSettingsOut(
                channel=YouTubeChannelOut.model_validate(c),
                settings=AutomationSettingsOut.model_validate(s),
            )
        )
    return results


def _safe_oauth_return_path(return_to: str | None) -> str:
    # Keep the OAuth return target on the authenticated frontend routes.
    if not return_to or not return_to.startswith("/") or return_to.startswith("//"):
        return "/app"
    path = urllib.parse.urlsplit(return_to).path
    if path not in {"/setup", "/app", "/dashboard"}:
        return "/app"
    query = urllib.parse.urlsplit(return_to).query
    return f"{path}?{query}" if query else path
def _is_https(request: Request) -> bool:
    """HTTPS detection that works behind Render's TLS-terminating proxy."""
    if request.url.scheme == "https":
        return True
    return request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https"


@router.get("/oauth/start", response_model=OAuthStartOut)
def start_oauth(
    request: Request,
    response: Response,
    return_to: str | None = Query(default=None, max_length=2048),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        purge_expired_oauth_states(db)
        url, browser_nonce = build_authorization_url(db, user.id)
    except YouTubeChannelError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    # In production the SPA (Vercel) calls the API (Render) cross-site, so the
    # browser-binding cookie must be Secure + SameSite=None to survive
    # third-party Set-Cookie rules; otherwise the callback arrives with no
    # cookie and the state check fails. Locally (same-site localhost) Lax/False
    # keeps working. Cookie value/path/domain unchanged: still scoped to the
    # backend origin and only to /api/channels/oauth.
    https = settings.oauth_state_cookie_secure or _is_https(request)
    cookie_samesite = "none" if https else "lax"
    response.set_cookie(
        settings.oauth_state_cookie_name, browser_nonce, max_age=settings.oauth_state_ttl_seconds,
        httponly=True, secure=https, samesite=cookie_samesite, path="/api/channels/oauth"
    )
    response.set_cookie(
        f"{settings.oauth_state_cookie_name}_return",
        _safe_oauth_return_path(return_to),
        max_age=settings.oauth_state_ttl_seconds,
        httponly=True,
        secure=https,
        samesite=cookie_samesite,
        path="/api/channels/oauth",
    )
    logger.info("oauth start: user %s state cookie set (secure=%s samesite=%s)", user.id, https, cookie_samesite)
    return OAuthStartOut(authorization_url=url)

@router.get("/oauth/callback")
def oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
    browser_nonce: str | None = Cookie(default=None, alias=settings.oauth_state_cookie_name),
    return_to: str | None = Cookie(default=None, alias=f"{settings.oauth_state_cookie_name}_return"),
):
    """
    Google redirects the browser here directly (no JWT header available).
    Identity comes from the one-time server-side state record, additionally
    bound to the initiating browser by an HttpOnly cookie.
    """
    safe_return_path = _safe_oauth_return_path(return_to)
    # Safe diagnostics only: presence booleans, never cookie/state values.
    logger.info(
        "oauth callback: state_param_present=%s oauth_state_cookie_present=%s return_cookie_present=%s",
        state is not None, browser_nonce is not None, return_to is not None,
    )

    def redirect_error(message: str):
        response = RedirectResponse(
            f"{settings.frontend_url}{safe_return_path}"
            f"{'&' if '?' in safe_return_path else '?'}channel_error={urllib.parse.quote(message)}"
        )
        response.delete_cookie(settings.oauth_state_cookie_name, path="/api/channels/oauth")
        response.delete_cookie(f"{settings.oauth_state_cookie_name}_return", path="/api/channels/oauth")
        return response

    if not state:
        return redirect_error("missing_oauth_state")

    try:
        user_id = consume_state(db, state, browser_nonce)
    except YouTubeChannelError as exc:
        logger.info("oauth callback: state rejected (%s)", exc)
        return redirect_error(str(exc))

    if error:
        return redirect_error(error)
    if not code:
        return redirect_error("missing_authorization_code")

    try:
        user = db.get(User, user_id)
        credentials = exchange_code_for_credentials(code, user)
        channel_info = fetch_channel_info(credentials)
        store_channel_connection(db, user_id, credentials, channel_info)
    except YouTubeChannelError as exc:
        # Safe identifiers only -- never log tokens, secrets or codes.
        logger.info("oauth callback failed for user %s: %s", user_id, exc)
        return redirect_error(str(exc))
    except (SQLAlchemyError, Exception) as exc:  # never leave the user on a raw 500
        db.rollback()
        logger.exception("oauth callback unexpected failure for user %s", user_id)
        return redirect_error("oauth_callback_failed")

    response = RedirectResponse(
        f"{settings.frontend_url}{safe_return_path}"
        f"{'&' if '?' in safe_return_path else '?'}channel_connected=1"
    )
    response.delete_cookie(settings.oauth_state_cookie_name, path="/api/channels/oauth")
    response.delete_cookie(f"{settings.oauth_state_cookie_name}_return", path="/api/channels/oauth")
    logger.info("oauth callback success: user %s connected channel %s (%s)", user_id, channel_info["id"], channel_info["title"])
    return response

@router.post("/{channel_id}/disconnect", status_code=status.HTTP_204_NO_CONTENT)
def disconnect(channel_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    channel = _get_own_channel_or_404(db, channel_id, user)
    disconnect_channel(db, channel)
    return None


@router.patch("/{channel_id}/settings", response_model=AutomationSettingsOut)
def update_settings(
    channel_id: uuid.UUID,
    payload: AutomationSettingsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    channel = _get_own_channel_or_404(db, channel_id, user)
    settings_row = channel.settings
    if settings_row is None:
        settings_row = AutomationSettings(channel_id=channel.id)
        db.add(settings_row)

    if payload.enabled is not None:
        settings_row.enabled = payload.enabled
    if payload.daily_upload_count is not None:
        settings_row.daily_upload_count = payload.daily_upload_count
    if "category_id" in payload.model_fields_set:
        if payload.category_id is not None and db.get(Category, payload.category_id) is None:
            raise HTTPException(status_code=400, detail="Category not found")
        settings_row.category_id = payload.category_id
    db.commit()
    db.refresh(settings_row)
    return settings_row

@router.get("/{channel_id}/runs", response_model=list[AutomationRunOut])
def list_runs(
    channel_id: uuid.UUID,
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    channel = _get_own_channel_or_404(db, channel_id, user)
    return sorted(channel.runs, key=lambda r: (r.run_date, r.started_at or datetime.min.replace(tzinfo=datetime.now().astimezone().tzinfo)), reverse=True)[:limit]
