from functools import lru_cache
from typing import Self

from pydantic import SecretStr, model_validator
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
    # $10 of credits in total. Raise the two daily numbers after topping up (e.g. 1000 and 300).
    free_requests_per_minute: int = 20
    free_requests_per_day: int = 50
    # One person's share of the day's free requests, so nobody can use up the whole lab's.
    free_requests_per_user_per_day: int = 20
    request_timeout_seconds: float = 120.0  # one upstream attempt
    # One /v1/complete with all its attempts. The worker waits 180 s for the answer, so it always
    # gets one (or a retryable error) before giving up and resending the call.
    complete_deadline_seconds: float = 150.0
    lease_seconds: int = 300

    @model_validator(mode="after")
    def _user_share_fits_the_lab_cap(self) -> Self:
        if self.free_requests_per_user_per_day > self.free_requests_per_day:
            raise ValueError(
                "ARP_FREE_REQUESTS_PER_USER_PER_DAY must not exceed ARP_FREE_REQUESTS_PER_DAY"
            )
        return self


@lru_cache
def get_settings() -> GatewaySettings:
    return GatewaySettings()
