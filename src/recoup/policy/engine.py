"""The policy engine. Phase 2. The core of the product.

Runs AFTER the reasoner. Approves, modifies, or vetoes. Rules run in a fixed,
documented order; the first veto wins; modifications compose. The order is part
of the spec, not an implementation detail, and it is written down in
docs/POLICY-SOURCES.md.

Every veto is logged AS A VETO and is visible in the UI.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from recoup.domain.enums import Intervention, VerdictKind
from recoup.domain.models import Invoice, PolicyVerdict, Tick
from recoup.ledger.ledger import Ledger
from recoup.policy.context import MerchantPolicy, Rule, RuleContext
from recoup.policy.rules import RULE_ORDER

if TYPE_CHECKING:
    from recoup.runner.batch import Proposal


class PolicyEngine:
    """Apply the fixed rule ladder to one proposal.

    The engine has one piece of per-run state: how many payment links it has
    approved. Callers therefore construct a fresh instance for every arm.
    """

    def __init__(
        self,
        config: MerchantPolicy | None = None,
        rules: tuple[Rule, ...] = RULE_ORDER,
    ) -> None:
        self.config = config or MerchantPolicy()
        self.rules = rules
        self.links_used = 0

    def adjudicate(
        self,
        record: Invoice,
        proposal: Proposal,
        tick: Tick,
        ledger: Ledger,
    ) -> PolicyVerdict:
        """Approve, compose reductions, or return the first veto."""
        ctx = RuleContext(
            record=record,
            original=proposal.intervention,
            current=proposal.intervention,
            tick=tick,
            ledger=ledger,
            config=self.config,
            links_used=self.links_used,
            llm_proposal=proposal.llm_proposal,
        )
        first_modification: PolicyVerdict | None = None

        for rule in self.rules:
            verdict = rule.check(ctx)
            if verdict is None:
                continue
            stamped = verdict.model_copy(update={"rule_id": rule.rule_id})
            if stamped.verdict is VerdictKind.VETOED:
                return stamped
            if stamped.verdict is not VerdictKind.MODIFIED or stamped.final is None:
                raise ValueError(f"rule {rule.rule_id} returned an invalid firing verdict")
            if first_modification is None:
                first_modification = stamped
            ctx = replace(ctx, current=stamped.final)

        if ctx.current is Intervention.PAYMENT_LINK:
            self.links_used += 1

        if first_modification is not None:
            return first_modification.model_copy(update={"final": ctx.current})
        return PolicyVerdict(
            verdict=VerdictKind.APPROVED,
            original=ctx.original,
            final=ctx.current,
            explanation="All policy rules passed.",
        )
