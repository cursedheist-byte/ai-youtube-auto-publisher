"""Per-user YouTube OAuth and encrypted credential lifecycle."""
from __future__ import annotations

import uuid
from datetime import timezone

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import ChannelStatus, YouTubeChannel, User
from app.services.access_service import credential_values
from app.services.token_crypto import decrypt_token, encrypt_token
from app.services.youtube_oauth_state import create_oauth_state, consume_oauth_state

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


class YouTubeChannelError(Exception):
    """A YouTube/OAuth failure meant to be shown to the user."""


def _client_config(user: User | None = None) -> dict:
    client_id, client_secret, _ = credential_values(user) if user is not None else (settings.google_oauth_client_id, settings.google_oauth_client_secret, settings.openrouter_api_key)
    if not client_id or not client_secret:
        raise YouTubeChannelError(
            "Google OAuth is not configured on the server (GOOGLE_OAUTH_CLIENT_ID / "
            "GOOGLE_OAUTH_CLIENT_SECRET)."
        )
    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_oauth_redirect_uri],
        }
    }


def build_authorization_url(db: Session, user_id: uuid.UUID) -> tuple[str, str]:
    """Create a one-time DB-backed state bound to a browser cookie."""
    user = db.get(User, user_id)
    config = _client_config(user)
    state, browser_nonce = create_oauth_state(db, user_id)
    flow = Flow.from_client_config(
        config, scopes=YOUTUBE_SCOPES, redirect_uri=settings.google_oauth_redirect_uri
    )
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    return authorization_url, browser_nonce


def consume_state(db: Session, state: str, browser_nonce: str | None) -> uuid.UUID:
    try:
        return consume_oauth_state(db, state, browser_binding=browser_nonce)
    except ValueError as exc:
        raise YouTubeChannelError(str(exc)) from exc


def exchange_code_for_credentials(code: str, user: User | None = None) -> Credentials:
    if not code or len(code) > 4096:
        raise YouTubeChannelError("Google authorization code is invalid.")
    flow = Flow.from_client_config(
        _client_config(user), scopes=YOUTUBE_SCOPES, redirect_uri=settings.google_oauth_redirect_uri
    )
    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        raise YouTubeChannelError(f"Couldn't complete Google sign-in: {exc}") from exc
    return flow.credentials


def fetch_channel_info(credentials: Credentials) -> dict:
    try:
        service = build("youtube", "v3", credentials=credentials, cache_discovery=False)
        response = service.channels().list(part="snippet", mine=True).execute()
    except HttpError as exc:
        raise YouTubeChannelError(f"YouTube API error while fetching channel info: HTTP {getattr(exc.resp, 'status', 'unknown')}") from exc
    items = response.get("items", [])
    if not items:
        raise YouTubeChannelError("This Google account has no YouTube channel. Create a channel first, then connect it.")
    channel = items[0]
    return {"id": channel["id"], "title": channel["snippet"]["title"]}


def store_channel_connection(db: Session, user_id: uuid.UUID, credentials: Credentials, channel_info: dict) -> YouTubeChannel:
    user = db.get(User, user_id)
    if user and user.access_grant and db.query(YouTubeChannel).filter(YouTubeChannel.user_id == user_id, YouTubeChannel.status == ChannelStatus.CONNECTED).count() >= user.access_grant.channel_limit:
        existing_channel = db.query(YouTubeChannel).filter(YouTubeChannel.user_id == user_id, YouTubeChannel.youtube_channel_id == channel_info["id"]).first()
        if existing_channel is None: raise YouTubeChannelError("Admin Access users may connect only one YouTube channel.")
    existing = db.query(YouTubeChannel).filter(YouTubeChannel.youtube_channel_id == channel_info["id"]).first()
    if existing and existing.user_id != user_id:
        raise YouTubeChannelError("This YouTube channel is already connected to a different account.")
    if not credentials.token:
        raise YouTubeChannelError("Google did not return an access token. Please reconnect.")
    encrypted_access = encrypt_token(credentials.token)
    encrypted_refresh = encrypt_token(credentials.refresh_token) if credentials.refresh_token else (existing.oauth_refresh_token if existing else None)
    if not encrypted_refresh:
        raise YouTubeChannelError("Google did not return a refresh token. Reconnect and grant the requested access.")
    expiry = credentials.expiry.replace(tzinfo=timezone.utc) if credentials.expiry and credentials.expiry.tzinfo is None else credentials.expiry
    if existing:
        existing.channel_title = channel_info["title"]
        existing.oauth_access_token = encrypted_access
        existing.oauth_refresh_token = encrypted_refresh
        existing.token_expiry = expiry
        existing.status = ChannelStatus.CONNECTED
        db.commit(); db.refresh(existing)
        return existing
    channel = YouTubeChannel(
        user_id=user_id,
        youtube_channel_id=channel_info["id"],
        channel_title=channel_info["title"],
        oauth_access_token=encrypted_access,
        oauth_refresh_token=encrypted_refresh,
        token_expiry=expiry,
        status=ChannelStatus.CONNECTED,
    )
    db.add(channel); db.commit(); db.refresh(channel)
    return channel


def get_credentials_for_channel(db: Session, channel: YouTubeChannel) -> Credentials:
    if not channel.oauth_refresh_token:
        channel.status = ChannelStatus.REVOKED
        db.commit()
        raise YouTubeChannelError("This channel has no stored refresh token. Reconnect it.")
    try:
        refresh_token = decrypt_token(channel.oauth_refresh_token)
        access_token = decrypt_token(channel.oauth_access_token) if channel.oauth_access_token else None
    except Exception as exc:
        channel.status = ChannelStatus.ERROR
        db.commit()
        raise YouTubeChannelError("Stored YouTube credentials could not be decrypted. Check ENCRYPTION_KEY and reconnect if necessary.") from exc
    credentials = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=credential_values(channel.user)[0],
        client_secret=credential_values(channel.user)[1],
        scopes=YOUTUBE_SCOPES,
    )
    credentials.expiry = channel.token_expiry.replace(tzinfo=None) if channel.token_expiry else None
    if not credentials.valid:
        try:
            credentials.refresh(GoogleAuthRequest())
        except RefreshError as exc:
            channel.status = ChannelStatus.REVOKED; db.commit()
            raise YouTubeChannelError("This channel's authorization was revoked. Reconnect the channel.") from exc
        except Exception as exc:
            channel.status = ChannelStatus.ERROR; db.commit()
            raise YouTubeChannelError(f"Couldn't refresh this channel's access token: {exc}") from exc
        if not credentials.token:
            channel.status = ChannelStatus.ERROR; db.commit()
            raise YouTubeChannelError("Google token refresh returned no access token.")
        channel.oauth_access_token = encrypt_token(credentials.token)
        channel.token_expiry = credentials.expiry.replace(tzinfo=timezone.utc) if credentials.expiry and credentials.expiry.tzinfo is None else credentials.expiry
        channel.status = ChannelStatus.CONNECTED
        db.commit()
    return credentials


def disconnect_channel(db: Session, channel: YouTubeChannel) -> None:
    if channel.oauth_access_token:
        try:
            import requests
            token = decrypt_token(channel.oauth_access_token)
            requests.post("https://oauth2.googleapis.com/revoke", params={"token": token}, timeout=10)
        except Exception:
            pass
    channel.oauth_access_token = None
    channel.oauth_refresh_token = None
    channel.token_expiry = None
    channel.status = ChannelStatus.REVOKED
    db.commit()
