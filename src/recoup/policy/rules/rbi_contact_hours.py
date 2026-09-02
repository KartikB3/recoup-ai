"""Apply Recoup's adopted RBI recovery-contact window."""

from __future__ import annotations

from recoup.domain.interventions import is_contact
from recoup.domain.models import PolicyVerdict, Tick
from recoup.ledger.clock import hour_of_day
from recoup.policy.context import Rule, RuleContext, veto
from recoup.policy.sources import RBI_CONTACT_HOURS


def _next_allowed_tick(tick: Tick) -> Tick:
    candidate = tick + 1
    while not 8 <= hour_of_day(candidate) <= 19:
        candidate += 1
    return candidate


def _check(ctx: RuleContext) -> PolicyVerdict | None:
    hour = hour_of_day(ctx.tick)
    if not is_contact(ctx.current) or 8 <= hour <= 19:
        return None
    return veto(
        ctx,
        RBI_CONTACT_HOURS,
        f"Contact at {hour:02d}:00 is outside the adopted 08:00-19:00 window.",
        defer_to_tick=_next_allowed_tick(ctx.tick),
    )


RULE = Rule(rule_id="rbi-contact-hours", check=_check)
