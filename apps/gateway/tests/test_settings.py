import pytest
from pydantic import ValidationError

from agentic_gateway.settings import GatewaySettings


def test_by_default_one_user_gets_a_share_of_the_free_quota_not_all_of_it() -> None:
    fields = GatewaySettings.model_fields
    per_user = fields["free_requests_per_user_per_day"].default
    assert 0 < per_user < fields["free_requests_per_day"].default


def test_a_user_share_above_the_lab_cap_is_refused_at_startup() -> None:
    with pytest.raises(ValidationError, match="ARP_FREE_REQUESTS_PER_USER_PER_DAY"):
        GatewaySettings(free_requests_per_day=50, free_requests_per_user_per_day=51)
    GatewaySettings(free_requests_per_day=50, free_requests_per_user_per_day=50)  # one-person lab
