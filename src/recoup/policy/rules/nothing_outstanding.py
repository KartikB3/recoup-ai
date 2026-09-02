"""Veto contact when the ledger says there is nothing left to collect."""

from __future__ import annotations

from recoup.domain.interventions import is_contact
from recoup.domain.models import PolicyVerdict
from recoup.policy.context import Rule, RuleContext, veto
from recoup.policy.sources import MERCHANT_POLICY


def _check(ctx: RuleContext) -> PolicyVerdict | None:
    if not is_contact(ctx.current) or ctx.record.outstanding_paise > 0:
        return None
    return veto(
        ctx,
        MERCHANT_POLICY,
        "No contact is allowed because the ledger has no outstanding balance to collect.",
    )


RULE = Rule(rule_id="nothing-outstanding", check=_check)
