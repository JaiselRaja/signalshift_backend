"""Application configuration via pydantic-settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── App ───
    app_name: str = "Signal Shift API"
    app_env: str = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8081"]

    # ─── Database ───
    database_url: str = "postgresql+asyncpg://signal:shift@localhost:5432/signalshift"
    database_pool_size: int = 20
    database_echo: bool = False

    # ─── Redis ───
    redis_url: str = "redis://localhost:6379/0"

    # ─── JWT ───
    jwt_secret_key: str = "super-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30

    # ─── OTP ───
    otp_expire_seconds: int = 300
    otp_length: int = 6
    otp_max_attempts: int = 5

    # ─── Payment ───
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    # ─── UPI (manual verification flow) ───
    upi_vpa: str = ""
    upi_payee_name: str = "Signal Shift"

    # ─── Google OAuth ───
    google_client_id: str = ""

    # ─── Email (MSG91) ───
    msg91_auth_key: str = ""
    msg91_email_domain: str = "msg.signalshift.in"
    msg91_from_email: str = "no-reply@msg.signalshift.in"
    msg91_from_name: str = "Signal Shift"
    msg91_otp_template_id: str = ""


settings = Settings()
