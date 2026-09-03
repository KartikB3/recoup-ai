"""Structured reasoner contracts.

The per-record output remains :class:`recoup.domain.models.LLMProposal`, the
contract frozen in Phase 1.  This module owns the aggregate contract introduced
in Phase 3 and exposes both JSON schemas for tests and cache fingerprinting.

The Python SDK's ``messages.parse()`` helper accepts the Pydantic *type* through
``output_format`` and translates it to ``output_config.format`` on the wire.
``output_config`` itself carries the effort setting.  Keeping those two roles
separate is required by anthropic 1.3 and is covered by a request-shape test.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from recoup.domain.enums import Intervention, VerdictKind
from recoup.domain.models import LLMProposal, RuleSource


class BatchInsight(BaseModel):
    """One portfolio-level pattern proposed by the model.

    This is deliberately a *proposal*.  ``suppression_recommended`` cannot
    suppress anything by itself; :class:`recoup.policy.engine.PolicyEngine`
    validates the identifiers and group membership and emits the final verdict.
    """

    model_config = ConfigDict(extra="forbid")

    pattern_found: bool
    diagnosis: str
    parent_group_id: str | None = None
    invoice_ids: list[str] = Field(default_factory=list, max_length=126)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    suppression_recommended: bool = False

    @model_validator(mode="after")
    def pattern_fields_are_consistent(self) -> BatchInsight:
        """Reject half-formed recommendations before policy ever sees them."""
        if len(self.invoice_ids) != len(set(self.invoice_ids)):
            raise ValueError("batch insight invoice_ids must be unique")
        if not self.pattern_found:
            if self.parent_group_id is not None or self.invoice_ids:
                raise ValueError("an absent pattern cannot name a group or invoices")
            if self.suppression_recommended:
                raise ValueError("an absent pattern cannot recommend suppression")
        elif self.parent_group_id is None or not self.invoice_ids:
            raise ValueError("a detected pattern must name its group and invoices")
        return self


class BatchPolicyVerdict(BaseModel):
    """The deterministic engine's final decision on a batch recommendation."""

    model_config = ConfigDict(extra="forbid")

    verdict: VerdictKind
    rule_id: str | None = None
    final_intervention: Intervention | None = None
    suppression_approved: bool = False
    parent_group_id: str | None = None
    invoice_ids: list[str] = Field(default_factory=list)
    rule_source: RuleSource | None = None
    explanation: str

    @model_validator(mode="after")
    def approved_suppression_is_an_escalation(self) -> BatchPolicyVerdict:
        """A portfolio suppression may only resolve to the existing safe action."""
        if self.suppression_approved:
            if self.verdict is not VerdictKind.APPROVED:
                raise ValueError("approved suppression requires an APPROVED verdict")
            if self.final_intervention is not Intervention.ESCALATE_HUMAN:
                raise ValueError("approved suppression must escalate to a human")
            if self.parent_group_id is None or not self.invoice_ids:
                raise ValueError("approved suppression must name its scope")
        elif self.final_intervention is not None:
            raise ValueError("a non-approved suppression cannot have a final intervention")
        return self


class BatchInsightResult(BaseModel):
    """The proposed insight, policy decision, and current execution state.

    Phase 3 persists this decision artifact.  Applying the consolidated
    escalation to the ledger is deliberately deferred to the Phase 6
    end-to-end/dashboard wiring, and the artifact says so rather than implying
    that an approved recommendation already changed record state.
    """

    model_config = ConfigDict(extra="forbid")

    proposal: BatchInsight
    policy_verdict: BatchPolicyVerdict
    applied_to_ledger: bool = False

    @model_validator(mode="after")
    def application_requires_approval(self) -> BatchInsightResult:
        if self.applied_to_ledger and not self.policy_verdict.suppression_approved:
            raise ValueError("a batch recommendation cannot be applied before policy approval")
        return self


def proposal_json_schema() -> dict[str, object]:
    """The exact per-record schema sent by ``messages.parse``."""
    return LLMProposal.model_json_schema()


def batch_insight_json_schema() -> dict[str, object]:
    """The exact aggregate schema sent by ``messages.parse``."""
    return BatchInsight.model_json_schema()
