"""Veto a drafted message whose DLT category does not fit the intervention."""

from __future__ import annotations

from recoup.domain.interventions import spec
from recoup.domain.models import PolicyVerdict
from recoup.policy.context import Rule, RuleContext, veto
from recoup.policy.sources import TRAI_MESSAGE_CATEGORY


def _check(ctx: RuleContext) -> PolicyVerdict | None:
    drafted = ctx.llm_proposal.drafted_message if ctx.llm_proposal is not None else None
    if drafted is None:
        return None
    expected = spec(ctx.current).correct_category
    # An earlier rule may have reduced a drafted contact to a non-message such
    # as ESCALATE_HUMAN. The stale draft is then never sent and has no category
    # to validate.
    if expected is None:
        return None
    if drafted.category is expected:
        return None
    return veto(
        ctx,
        TRAI_MESSAGE_CATEGORY,
        f"Draft category {drafted.category.value} is invalid for {ctx.current.value}; "
        f"expected {expected.value}.",
    )


RULE = Rule(rule_id="trai-message-category", check=_check)
