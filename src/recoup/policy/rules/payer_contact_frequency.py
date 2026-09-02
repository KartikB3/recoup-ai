"""Cap contact volume per payer across all of their invoices."""

from __future__ import annotations

from recoup.domain.interventions import is_contact
from recoup.domain.models import PolicyVerdict
from recoup.policy.context import Rule, RuleContext, veto
from recoup.policy.sources import MERCHANT_POLICY


def _check(ctx: RuleContext) -> PolicyVerdict | None:
    if not is_contact(ctx.current):
        return None
    floor = max(0, ctx.tick - ctx.config.contact_window_ticks)
    qualifying = [tick for tick in ctx.payer_contact_ticks() if tick >= floor]
    if len(qualifying) < ctx.config.max_contacts_per_payer:
        return None
    if qualifying:
        defer_to = max(ctx.tick + 1, qualifying[0] + ctx.config.contact_window_ticks + 1)
    else:
        defer_to = ctx.tick + max(1, ctx.config.contact_window_ticks)
    return veto(
        ctx,
        MERCHANT_POLICY,
        f"This payer already received {len(qualifying)} contacts in the rolling window.",
        defer_to_tick=defer_to,
    )


RULE = Rule(rule_id="payer-contact-frequency", check=_check)
