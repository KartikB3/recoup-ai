"""Intervention cost and cadence model. Phase 1. See build spec section 4.

Each intervention carries its cost in contact-budget units and API-budget
units, the channel and TRAI category it correctly belongs to, and how long the
record rests before the agent looks at it again.

WAIT and STOP cost nothing and are still first-class decisions that get logged.
That is what makes this an agent with judgement rather than a dunning cron job.

On `review_ticks` -- the decision cadence
-----------------------------------------
The tick loop does not consult the reasoner 112 times per record. A record is
reviewed when `tick >= invoice.next_review_tick`, and acting pushes that
forward by the interval below. This is what keeps a 120-record batch at a few
hundred model calls instead of thirteen thousand, and it is also what makes
WAIT meaningful: at a review point the agent can decide to do nothing and let
the clock run.

The BASELINE arm does not use this. It runs a fixed three-day schedule of its
own. Keeping the two cadences separate is what the comparison measures.

On `correct_category` -- classification is itself a rule
--------------------------------------------------------
TRAI requires a message to carry the right header category. Nothing Recoup
sends is promotional; dunning an existing obligation is service. The reasoner
nevertheless proposes a category on every drafted message, and the policy
engine checks it against this table. A proposal that classifies a chaser as
promotional is a real compliance failure, caught deterministically. That is a
more honest use of the TRAI classification rule than inventing promotional
content so a time window has something to bite on.
"""

from __future__ import annotations

from dataclasses import dataclass

from recoup.domain.enums import Channel, Intervention, MessageCategory

#: Sentinel for "this record has left the automated loop". Large enough that no
#: real run reaches it; finite so that arithmetic on it never overflows meaning.
REVIEW_NEVER: int = 10**9


@dataclass(frozen=True)
class InterventionSpec:
    """The full cost and shape of one intervention. Frozen: this is a contract."""

    contact_units: int
    """Counts against the merchant contact-frequency rules."""

    api_units: int
    """Counts against the global 30 payment-link budget (ISS-001)."""

    channel: Channel | None
    """None for decisions that do not reach the payer."""

    correct_category: MessageCategory | None
    """The TRAI header category this message must carry. None for non-messages."""

    review_ticks: int
    """Ticks before the agent looks at this record again."""

    is_contact: bool
    """Whether this puts a message in front of the payer."""

    ends_automation: bool
    """Whether the record leaves the automated loop after this."""


#: The complete table. Every intervention in the closed enum appears exactly
#: once; a test asserts that, so adding an intervention without costing it is a
#: build failure rather than a silent zero.
SPECS: dict[Intervention, InterventionSpec] = {
    Intervention.WAIT: InterventionSpec(
        contact_units=0,
        api_units=0,
        channel=None,
        correct_category=None,
        # Two virtual days. Short enough that a WAIT is a decision to hold, not
        # a decision to abandon.
        review_ticks=8,
        is_contact=False,
        ends_automation=False,
    ),
    Intervention.SOFT_REMINDER: InterventionSpec(
        contact_units=1,
        api_units=0,
        channel=Channel.EMAIL,
        correct_category=MessageCategory.S,
        # 72 virtual hours, deliberately equal to the merchant minimum spacing
        # rule so the cadence cannot on its own produce a spacing violation.
        review_ticks=12,
        is_contact=True,
        ends_automation=False,
    ),
    Intervention.PAYMENT_LINK: InterventionSpec(
        contact_units=1,
        api_units=1,
        channel=Channel.EMAIL,
        # A link that settles an existing obligation is service, not
        # transactional: -T is scoped to messages triggered by a
        # customer-initiated transaction, and this is merchant-initiated.
        correct_category=MessageCategory.S,
        review_ticks=12,
        is_contact=True,
        ends_automation=False,
    ),
    Intervention.PHONE_FOLLOWUP: InterventionSpec(
        contact_units=1,
        api_units=0,
        channel=Channel.PHONE,
        # Voice is outside the DLT header scheme entirely, so there is no
        # category to classify. The contact-hour rule still applies.
        correct_category=None,
        # Four and a half virtual days. The extra half-day is deliberate: a
        # phone call made at 08:00 moves the next review to 20:00, where the
        # RBI contact-hour rule can demonstrably fire. Whole-day cadences kept
        # every Phase 1 decision phase-locked at 08:00 (ISS-025).
        review_ticks=18,
        is_contact=True,
        ends_automation=False,
    ),
    Intervention.ESCALATE_HUMAN: InterventionSpec(
        contact_units=0,
        api_units=0,
        channel=None,
        correct_category=None,
        review_ticks=REVIEW_NEVER,
        is_contact=False,
        ends_automation=True,
    ),
    Intervention.STOP: InterventionSpec(
        contact_units=0,
        api_units=0,
        channel=None,
        correct_category=None,
        review_ticks=REVIEW_NEVER,
        is_contact=False,
        ends_automation=True,
    ),
}


def spec(intervention: Intervention) -> InterventionSpec:
    """Look up an intervention's cost. Raises rather than defaulting to free."""
    return SPECS[intervention]


def is_contact(intervention: Intervention) -> bool:
    """Whether this intervention reaches the payer."""
    return SPECS[intervention].is_contact
