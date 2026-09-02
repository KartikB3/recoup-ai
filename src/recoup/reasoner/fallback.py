"""Deterministic no-model proposer used by the Phase 2 agent arm.

For when the API errors, times out, or refuses. Assume it is down while the
video is being recorded.

GATE: the full batch must complete with ANTHROPIC_API_KEY empty OR unset.
Branch on falsy-or-missing, not on `"ANTHROPIC_API_KEY" not in os.environ` -
an empty value still outranks every other credential source rather than
falling through, so CI runs the stricter empty-string case.
"""

from __future__ import annotations

from typing import Any

from recoup.domain.enums import Arm, Channel, Intervention, MessageCategory, RecordState
from recoup.domain.models import DraftedMessage, LLMProposal, Tick
from recoup.runner.batch import Proposal

#: Five payer contacts plus the terminal STOP decision. This is six decision
#: rungs, while the baseline's five-contact cap remains untouched.
MAX_ATTEMPTS: int = 6


def _draft(intervention: Intervention, invoice_id: str) -> DraftedMessage | None:
    if intervention is Intervention.SOFT_REMINDER:
        return DraftedMessage(
            channel=Channel.EMAIL,
            category=MessageCategory.S,
            subject=f"Reminder for invoice {invoice_id}",
            body="Please review the outstanding invoice and let us know its payment status.",
        )
    if intervention is Intervention.PAYMENT_LINK:
        return DraftedMessage(
            channel=Channel.EMAIL,
            category=MessageCategory.S,
            subject=f"Payment link for invoice {invoice_id}",
            body="A payment link is available for the outstanding invoice. Please contact us "
            "if the account needs review.",
        )
    return None


class DeterministicFallback:
    """Propose from structured ledger facts and leave every veto to policy."""

    name = "deterministic-fallback"
    arm = Arm.AGENT

    def propose(self, snapshot: dict[str, Any], tick: Tick) -> Proposal:
        """Walk the fixed Phase 2 action ladder without reading free text."""
        del tick
        days_overdue = int(snapshot["days_overdue"])
        state = str(snapshot["state"])
        contacts_made = int(snapshot["contacts_made"])

        if days_overdue < 0 or state == RecordState.PROMISED.value:
            intervention = Intervention.WAIT
        elif contacts_made == 0:
            intervention = Intervention.SOFT_REMINDER
        elif contacts_made <= 2:
            intervention = Intervention.PAYMENT_LINK
        elif contacts_made == 3:
            intervention = Intervention.PHONE_FOLLOWUP
        elif contacts_made == MAX_ATTEMPTS - 2:
            # Load-bearing: PHONE_FOLLOWUP shifts review to 20:00. The next
            # rung must be a contact so the RBI rule has something to veto.
            intervention = Intervention.SOFT_REMINDER
        else:
            intervention = Intervention.STOP

        llm_proposal = LLMProposal(
            diagnosis="Deterministic Phase 2 fallback based on structured ledger facts.",
            intervention=intervention,
            confidence=1.0,
            reasoning=(
                f"days_overdue={days_overdue}; contacts_made={contacts_made}; state={state}."
            ),
            drafted_message=_draft(intervention, str(snapshot["invoice_id"])),
        )
        return Proposal(intervention=intervention, llm_proposal=llm_proposal)


FallbackProposer = DeterministicFallback
