"""Route a visibly disputed invoice to a human and stop automated chasing."""

from __future__ import annotations

from recoup.domain.enums import Intervention, RecordState
from recoup.domain.models import PolicyVerdict
from recoup.policy.context import Rule, RuleContext, modify
from recoup.policy.sources import MERCHANT_POLICY


def _check(ctx: RuleContext) -> PolicyVerdict | None:
    visible = (
        ctx.record.state is RecordState.DISPUTED
        or ctx.record.free_text.dispute_description is not None
    )
    if not visible or ctx.current is Intervention.ESCALATE_HUMAN:
        return None
    return modify(
        ctx,
        Intervention.ESCALATE_HUMAN,
        MERCHANT_POLICY,
        "A visible dispute stops automated contact and routes the invoice to a human.",
    )


RULE = Rule(rule_id="visible-dispute", check=_check)
