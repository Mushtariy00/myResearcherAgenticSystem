"""The lab's OpenRouter balance, until the gateway reads it from OpenRouter's credits endpoint.

Each month's opening balance is generated from the month alone. The lab's real paid spend this
month comes off it, so the balance moves with the calls the lab actually makes.
"""

from datetime import datetime
from decimal import Decimal

from agentic_api.demo._seed import rng_for

# Admins are alerted when the prepaid balance drops below this (auto top-up stays off).
ALERT_FLOOR_USD = Decimal("10.00")
_CENT = Decimal("0.01")


def opening_balance(month: datetime) -> Decimal:
    """The generated balance at the start of ``month``'s UTC month: $38 to $64."""
    rng = rng_for("lab-balance", f"{month:%Y-%m}")
    return Decimal(rng.randint(3800, 6400)) / 100


def balance(month: datetime, spent_this_month: Decimal) -> Decimal:
    """What is left after this month's spend, in whole cents, never below zero."""
    return max(Decimal(0), opening_balance(month) - spent_this_month).quantize(_CENT)
