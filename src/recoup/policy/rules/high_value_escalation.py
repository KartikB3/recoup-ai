"""Prevent automation from abandoning a high-value receivable unseen."""

from __future__ import annotations

from recoup.domain.enums import Intervention
from recoup.domain.models import PolicyVerdict
from recoup.policy.context import Rule, RuleContext, modify
from recoup.policy.sources import MERCHANT_POLICY


def _check(ctx: RuleContext) -> PolicyVerdict | None:
    if (
        ctx.current is not Intervention.STOP
        or ctx.record.outstanding_paise <= ctx.config.escalation_threshold_paise
    ):
        return None
    return modify(
        ctx,
        Intervention.ESCALATE_HUMAN,
        MERCHANT_POLICY,
        "A receivable above the merchant threshold requires human review before abandonment.",
    )


RULE = Rule(rule_id="high-value-escalation", check=_check)
