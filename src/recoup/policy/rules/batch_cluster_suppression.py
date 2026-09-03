"""Apply an approved aggregate suppression to individual invoices.

The aggregate reasoner may notice that several invoices under one parent group
are silent for a single account-level reason.  :meth:`PolicyEngine.
adjudicate_batch` decides whether that recommendation is allowed to bind, using
ledger facts only.  This rule is where an approved decision finally reaches a
record.

The recommendation has two halves, and both are applied here so that neither is
an assertion: open **one** consolidated relationship escalation, then suppress
duplicate invoice-level chasing across the rest of the group.  The first
contact proposed against the group becomes that escalation; every later one is
vetoed and carries this rule's id, so nine suppressed records appear in the
audit log and in `rule_firings` rather than being silently skipped.

Ordering matters and is asserted in the tests: this rule sits after
`visible-dispute`, so an invoice with its own visible dispute is still routed
on its own merits rather than absorbed into a group decision.
"""

from __future__ import annotations

from recoup.domain.enums import CONTACT_INTERVENTIONS, Intervention
from recoup.domain.models import PolicyVerdict
from recoup.policy.context import Rule, RuleContext, modify, veto
from recoup.policy.sources import MERCHANT_POLICY


def _check(ctx: RuleContext) -> PolicyVerdict | None:
    if ctx.record.invoice_id not in ctx.suppressed_invoices:
        return None
    if ctx.current not in CONTACT_INTERVENTIONS:
        return None
    if not ctx.group_escalation_opened:
        return modify(
            ctx,
            Intervention.ESCALATE_HUMAN,
            MERCHANT_POLICY,
            "An approved account-level pattern opens one consolidated relationship "
            "escalation for the whole parent group.",
        )
    return veto(
        ctx,
        MERCHANT_POLICY,
        "The parent group is already held under one consolidated escalation, so "
        "duplicate invoice-level chasing is suppressed.",
    )


RULE = Rule(rule_id="batch-cluster-suppression", check=_check)
