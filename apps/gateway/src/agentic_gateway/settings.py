from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ARP_", env_file=".env", extra="ignore")

    database_url: str = ""
    valkey_url: str = "redis://localhost:6379/0"
    gateway_token: SecretStr = SecretStr("")
    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    public_origin: str = "http://localhost:8080"  # sent as HTTP-Referer for OpenRouter attribution
    # Comma-separated overrides; otherwise routing.DEFAULT_PAID_MODELS / catalog free models.
    paid_models: str = ""
    free_models: str = ""
    # Free tier per account: 20 requests/min and 50/day; 1,000/day once the account has bought
    # $10 of credits in total. Raise these two after topping up.
    free_requests_per_minute: int = 20
    free_requests_per_day: int = 50
    free_requests_per_user_per_day: int = 50  # fair share so one person can't drain the lab
    request_timeout_seconds: float = 120.0
    lease_seconds: int = 300


@lru_cache
def get_settings() -> GatewaySettings:
    return GatewaySettings()
