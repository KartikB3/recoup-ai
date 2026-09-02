"""Require minimum spacing between contacts to the same payer."""

from __future__ import annotations

from recoup.domain.interventions import is_contact
from recoup.domain.models import PolicyVerdict
from recoup.policy.context import Rule, RuleContext, veto
from recoup.policy.sources import MERCHANT_POLICY


def _check(ctx: RuleContext) -> PolicyVerdict | None:
    if not is_contact(ctx.current):
        return None
    ticks = ctx.payer_contact_ticks()
    if not ticks:
        return None
    last_tick = ticks[-1]
    if ctx.tick - last_tick >= ctx.config.min_contact_spacing_ticks:
        return None
    return veto(
        ctx,
        MERCHANT_POLICY,
        "The payer was contacted too recently; the merchant requires at least 72 hours.",
        defer_to_tick=max(ctx.tick + 1, last_tick + ctx.config.min_contact_spacing_ticks),
    )


RULE = Rule(rule_id="payer-contact-spacing", check=_check)
