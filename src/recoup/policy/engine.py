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
from recoup.policy.sources import MERCHANT_POLICY
from recoup.reasoner.schemas import BatchInsight, BatchPolicyVerdict

if TYPE_CHECKING:
    from recoup.runner.batch import Proposal

BATCH_POLICY_RULE_ID = "batch-cluster-suppression"


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
        self.suppressed_invoices: frozenset[str] = frozenset()
        self.group_escalation_opened = False

    def arm_batch_suppression(
        self,
        insight: BatchInsight,
        verdict: BatchPolicyVerdict,
    ) -> bool:
        """Let an approved aggregate decision bind on individual invoices.

        Separate from :meth:`adjudicate_batch` on purpose. Adjudicating decides
        whether the recommendation is *allowed*; arming is the runner asking for
        it to be *applied*. Keeping them apart means a caller cannot apply a
        recommendation the engine refused, and the artifact's
        ``applied_to_ledger`` flag reports what actually happened.
        """
        if not verdict.suppression_approved or verdict.verdict is VerdictKind.VETOED:
            return False
        self.suppressed_invoices = frozenset(insight.invoice_ids)
        self.group_escalation_opened = False
        return bool(self.suppressed_invoices)

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
            suppressed_invoices=self.suppressed_invoices,
            group_escalation_opened=self.group_escalation_opened,
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
        if (
            ctx.current is Intervention.ESCALATE_HUMAN
            and record.invoice_id in self.suppressed_invoices
        ):
            # The group's single consolidated escalation is now open, so every
            # later contact against the group is a duplicate.
            self.group_escalation_opened = True

        if first_modification is not None:
            return first_modification.model_copy(update={"final": ctx.current})
        return PolicyVerdict(
            verdict=VerdictKind.APPROVED,
            original=ctx.original,
            final=ctx.current,
            explanation="All policy rules passed.",
        )

    def adjudicate_batch(
        self,
        insight: BatchInsight,
        tick: Tick,
        ledger: Ledger,
    ) -> BatchPolicyVerdict:
        """Validate the scope of an aggregate suppression recommendation.

        The model may identify a pattern, but only this method decides whether
        individual chasing may be suppressed.  It checks current ledger facts,
        never generator flags, archetypes, provenance, or spotlight metadata.
        """
        del tick
        if not insight.pattern_found or not insight.suppression_recommended:
            return BatchPolicyVerdict(
                verdict=VerdictKind.APPROVED,
                explanation=(
                    "No aggregate suppression was proposed; per-record policy remains active."
                ),
            )

        if insight.parent_group_id is None:
            return self._batch_veto(insight, "The recommendation did not name a parent group.")

        try:
            proposed = [ledger.get(invoice_id) for invoice_id in insight.invoice_ids]
        except KeyError:
            return self._batch_veto(
                insight, "The recommendation named an invoice outside the current ledger."
            )

        if len(proposed) < self.config.min_batch_group_invoices:
            return self._batch_veto(
                insight,
                "A consolidated escalation requires at least "
                f"{self.config.min_batch_group_invoices} invoices.",
            )
        if any(record.parent_group_id != insight.parent_group_id for record in proposed):
            return self._batch_veto(
                insight, "Every recommended invoice must belong to the named parent group."
            )
        if len({record.payer_id for record in proposed}) < self.config.min_batch_group_payers:
            return self._batch_veto(
                insight,
                "A consolidated escalation requires at least "
                f"{self.config.min_batch_group_payers} payers.",
            )
        if any(record.outstanding_paise <= 0 for record in proposed):
            return self._batch_veto(
                insight, "A settled invoice cannot be included in contact suppression."
            )

        expected_ids = {
            record.invoice_id
            for record in ledger.records
            if record.parent_group_id == insight.parent_group_id and record.outstanding_paise > 0
        }
        if set(insight.invoice_ids) != expected_ids:
            return self._batch_veto(
                insight,
                "The recommendation must cover the complete open parent group, "
                "not a selected subset.",
            )

        return BatchPolicyVerdict(
            verdict=VerdictKind.APPROVED,
            rule_id=BATCH_POLICY_RULE_ID,
            final_intervention=Intervention.ESCALATE_HUMAN,
            suppression_approved=True,
            parent_group_id=insight.parent_group_id,
            invoice_ids=sorted(expected_ids),
            rule_source=MERCHANT_POLICY,
            explanation=(
                "The complete open parent group passed the merchant breadth and membership checks; "
                "suppress duplicate invoice-level contact and open one relationship escalation."
            ),
        )

    @staticmethod
    def _batch_veto(insight: BatchInsight, explanation: str) -> BatchPolicyVerdict:
        """Reject an unsafe or unverifiable aggregate scope."""
        return BatchPolicyVerdict(
            verdict=VerdictKind.VETOED,
            rule_id=BATCH_POLICY_RULE_ID,
            parent_group_id=insight.parent_group_id,
            invoice_ids=insight.invoice_ids,
            rule_source=MERCHANT_POLICY,
            explanation=explanation,
        )
