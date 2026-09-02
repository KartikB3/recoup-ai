"""Apply the TCCCPR default time-band preference to promotional drafts."""

from __future__ import annotations

from recoup.domain.enums import MessageCategory
from recoup.domain.interventions import is_contact
from recoup.domain.models import PolicyVerdict, Tick
from recoup.ledger.clock import hour_of_day
from recoup.policy.context import Rule, RuleContext, veto
from recoup.policy.sources import TRAI_TIME_BANDS


def _next_allowed_tick(tick: Tick) -> Tick:
    candidate = tick + 1
    while not 10 <= hour_of_day(candidate) < 21:
        candidate += 1
    return candidate


def _check(ctx: RuleContext) -> PolicyVerdict | None:
    drafted = ctx.llm_proposal.drafted_message if ctx.llm_proposal is not None else None
    promotional = drafted is not None and drafted.category is MessageCategory.P
    hour = hour_of_day(ctx.tick)
    if not is_contact(ctx.current) or not promotional or 10 <= hour < 21:
        return None
    return veto(
        ctx,
        TRAI_TIME_BANDS,
        f"Promotional contact at {hour:02d}:00 falls in a default-OFF preference band.",
        defer_to_tick=_next_allowed_tick(ctx.tick),
    )


RULE = Rule(rule_id="trai-promotional-window", check=_check)
