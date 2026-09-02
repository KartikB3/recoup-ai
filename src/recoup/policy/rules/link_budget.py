"""Downgrade a payment link after the run-level API budget is spent."""

from __future__ import annotations

from recoup.domain.enums import Intervention
from recoup.domain.models import PolicyVerdict
from recoup.policy.context import Rule, RuleContext, modify
from recoup.policy.sources import MERCHANT_POLICY


def _check(ctx: RuleContext) -> PolicyVerdict | None:
    budget = ctx.config.link_budget
    if ctx.current is not Intervention.PAYMENT_LINK or budget is None or ctx.links_used < budget:
        return None
    return modify(
        ctx,
        Intervention.SOFT_REMINDER,
        MERCHANT_POLICY,
        "The run-level payment-link budget is spent; use a reminder without a new link.",
    )


RULE = Rule(rule_id="link-budget", check=_check)
