import os
import secrets
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_database_url() -> str:
    if os.getenv("VERCEL"):
        return "sqlite:////tmp/lead_engine.db"
    return "sqlite:///./lead_engine.db"


def default_admin_api_key() -> str:
    if os.getenv("VERCEL"):
        return secrets.token_urlsafe(32)
    return "dev-admin-key"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    database_url: str = Field(default_factory=default_database_url)
    admin_api_key: str = Field(default_factory=default_admin_api_key, min_length=8)

    google_places_api_key: str | None = None
    apollo_api_key: str | None = None
    hunter_api_key: str | None = None
    clearout_api_key: str | None = None

    sending_provider: Literal["sandbox", "resend"] = "sandbox"
    resend_api_key: str | None = None
    outreach_from_email: str = "leads@outreach.ardeno.studio"
    outreach_reply_to: str = "hello@ardeno.studio"
    outreach_company_name: str = "Ardeno Studio"
    outreach_postal_address: str = "Set a valid physical mailing address before production sending"
    outreach_unsubscribe_base_url: str = "http://127.0.0.1:8088/api/v1/unsubscribe"
    require_dns_auth: bool = True
    sender_dns_auth_verified: bool = False
    daily_send_cap_per_sender: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()
