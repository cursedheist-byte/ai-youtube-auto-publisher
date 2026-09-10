"""
Centralized application configuration.

All settings are read from environment variables (via a .env file in local dev).
Nothing here is hard-coded so the same code runs against local Postgres,
Supabase, or Neon just by changing DATABASE_URL.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    database_url: str

    # Auth
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # Token encryption (used starting Phase 3, present now so schema/config are ready)
    encryption_key: str = ""

    # CORS
    cors_origins: str = "http://localhost:5173"

    # Google / AI
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri: str = "http://localhost:8000/api/channels/oauth/callback"
    oauth_state_ttl_seconds: int = 600
    oauth_state_cookie_name: str = "yt_oauth_state_binding"
    oauth_state_cookie_secure: bool = False
    google_service_account_json_path: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_fallback_model: str = "gemini-flash-latest"
    openrouter_api_key: str = ""
    openrouter_model: str = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    ai_provider: str = "gemini"
    ai_request_timeout_seconds: int = 45
    youtube_privacy_status: str = "public"
    youtube_default_category_id: str = "22"
    youtube_upload_chunk_bytes: int = 8 * 1024 * 1024

    # Frontend base URL, used to redirect the browser back after the OAuth callback
    frontend_url: str = "http://localhost:5173"

    # Automation
    scheduler_timezone: str = "UTC"
    automation_hour_utc: int = 3
    automation_minute_utc: int = 0
    retry_interval_minutes: int = 60
    max_upload_retries: int = 3
    upload_stale_after_minutes: int = 30

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
