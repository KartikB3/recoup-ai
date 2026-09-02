"""Downgrade a payment link after the invoice-level cap is reached."""

from __future__ import annotations

from recoup.domain.enums import Intervention
from recoup.domain.models import PolicyVerdict
from recoup.policy.context import Rule, RuleContext, modify
from recoup.policy.sources import MERCHANT_POLICY


def _check(ctx: RuleContext) -> PolicyVerdict | None:
    if (
        ctx.current is not Intervention.PAYMENT_LINK
        or ctx.record.contact_ledger.payment_links_sent < ctx.config.max_links_per_invoice
    ):
        return None
    return modify(
        ctx,
        Intervention.SOFT_REMINDER,
        MERCHANT_POLICY,
        "The invoice-level payment-link cap is spent; use a reminder without a new link.",
    )


RULE = Rule(rule_id="invoice-link-cap", check=_check)
