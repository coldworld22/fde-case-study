from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict

RIYADH = ZoneInfo("Asia/Riyadh")


class Settings(BaseSettings):
    """All configuration comes from environment variables (or a .env file); see .env.example."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="CLINICBOT_", extra="ignore")

    database_url: str = "sqlite:///./clinicbot.db"

    # WhatsApp Business Cloud API
    whatsapp_verify_token: str = "change-me"
    whatsapp_app_secret: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_api_base: str = "https://graph.facebook.com/v21.0"

    # Triage: "rules" works offline; "llm" calls any OpenAI-compatible endpoint (e.g. llm-gateway).
    triage_mode: str = "rules"
    llm_base_url: str = "http://localhost:8080"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 4.0

    # Odoo (JSON-RPC). Leave odoo_url empty to keep events in the outbox until it is configured.
    odoo_url: str = ""
    odoo_db: str = ""
    odoo_user: str = ""
    odoo_api_key: str = ""

    # Booking rules
    slots_offered: int = 3
    min_notice_minutes: int = 60
    max_attempts: int = 6


@lru_cache
def get_settings() -> Settings:
    return Settings()
