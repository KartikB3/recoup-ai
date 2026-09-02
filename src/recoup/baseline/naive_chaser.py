"""The baseline arm. Phase 2.

Contact every 3 days until paid or 5 attempts. Runs through the SAME runner, the
SAME ledger and the SAME seed, and bypasses the policy engine.

That bypass is the whole point: the baseline is what generates the false
interventions the agent avoids.

Why this is not a straw man
---------------------------
It would be easy to write a baseline that loses, and worthless to do so. This
one is what a competent engineer actually ships when asked to automate
receivables chasing in an afternoon, and on the CHRONIC_LATE population -- which
is the largest responsive segment in the book -- it does genuinely well, because
chasing those payers genuinely works.

It loses on the parts it cannot see, and every one of those losses is a real
category rather than a rhetorical one:

  * it chases the ten PAID_UNRECONCILED records, whose money already left the
    payer, because nothing in the structured fields says otherwise;
  * it chases DISPUTING payers into filing formal disputes, converting a
    commercial objection into a human queue item;
  * it presses DISTRESSED payers, for whom pressure lowers the odds of payment
    and raises the odds of a complaint;
  * it spends five contacts on RELIABLE_BUT_SLOW payers who were going to pay
    on their own cycle regardless;
  * and it keeps chasing after the fatigue threshold, damaging its own book.

None of that is a handicap imposed on it. It is the consequence of deciding
from `days_overdue` and a contact count, which is all it looks at -- and the
honest description of every rules-based collections system in production.

It bypasses the policy engine because that is what makes the veto count
visible. A baseline that respected the same rules would be a second agent.
"""

from __future__ import annotations

from typing import Any

from recoup.domain.enums import Arm, Intervention
from recoup.domain.models import Tick
from recoup.ledger.clock import ticks_for_days
from recoup.runner.batch import Proposal

#: Days between contacts. Three, per build spec section 4.
CHASE_INTERVAL_DAYS: int = 3

#: Attempts before it gives up on a record.
MAX_ATTEMPTS: int = 5

#: Contacts after which it switches from a reminder to a payment link. Sending
#: the link on the first approach would spend the scarce API budget (ISS-001)
#: on records that would have paid to a reminder, so even the naive arm escalates
#: rather than leading with it.
LINK_AFTER_ATTEMPTS: int = 2


class NaiveChaser:
    """Chase on a fixed cadence until paid or out of attempts. Satisfies `Proposer`.

    Reads four fields of the snapshot: how many contacts have been made, when
    the last one was, how overdue the record is, and its state. It has no
    access to the free text, which is not a restriction imposed on it -- it
    simply has no way to use prose, and that is the gap the agent arm exists to
    close.
    """

    name = "naive-chaser"
    arm = Arm.BASELINE

    def propose(self, snapshot: dict[str, Any], tick: Tick) -> Proposal:
        """Decide from the contact count and the clock. Nothing else."""
        contacts_made = int(snapshot["contacts_made"])
        last_contact_tick = snapshot["last_contact_tick"]

        if contacts_made >= MAX_ATTEMPTS:
            # Out of attempts. STOP is the honest move: it ends automation and
            # leaves the record to be written off at finalisation, which is
            # what a fixed-cadence chaser does when the cadence runs out.
            return Proposal(intervention=Intervention.STOP)

        if last_contact_tick is not None:
            elapsed = tick - int(last_contact_tick)
            if elapsed < ticks_for_days(CHASE_INTERVAL_DAYS):
                return Proposal(intervention=Intervention.WAIT)

        if contacts_made >= LINK_AFTER_ATTEMPTS:
            return Proposal(intervention=Intervention.PAYMENT_LINK)
        return Proposal(intervention=Intervention.SOFT_REMINDER)


class PolicyNaiveChaser(NaiveChaser):
    """The identical naive ladder, isolated behind the policy engine."""

    name = "naive-chaser-with-policy"
    arm = Arm.POLICY_BASELINE
