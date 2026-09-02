"""Closed enumerations. Phase 1.

Every set in this module is closed on purpose. Where a value would otherwise be
a free string it is an enum here, so that the reasoner's structured-output
schema physically cannot emit something outside the space and so that the
dashboard never has to render an unknown token.

INVARIANT: `Intervention` is closed. Nothing outside it exists in this codebase.

Ground truth vs. observable
---------------------------
`Archetype` and `Flag` are **simulation ground truth**. They are never shown to
the reasoner (see `Invoice.to_snapshot`) and exist so the adjudicator can
resolve outcomes and the metrics can score false interventions. Everything the
agent is allowed to see is either a ledger fact or free text.
"""

from __future__ import annotations

from enum import StrEnum


class RecordState(StrEnum):
    """The ledger state machine. Build spec section 2.

    Terminal states are PAID and WRITTEN_OFF only. EXHAUSTED and HUMAN_QUEUE are
    deliberately *not* terminal: a payer who is no longer being chased can still
    pay, which is what makes WAIT and STOP capable of winning rather than merely
    conceding. See `ledger.ledger.ALLOWED_TRANSITIONS`.
    """

    AT_RISK = "AT_RISK"
    CONTACTED = "CONTACTED"
    PROMISED = "PROMISED"
    PAID = "PAID"
    DISPUTED = "DISPUTED"
    HUMAN_QUEUE = "HUMAN_QUEUE"
    EXHAUSTED = "EXHAUSTED"
    WRITTEN_OFF = "WRITTEN_OFF"


class Intervention(StrEnum):
    """The complete action space. Build spec section 4. Closed set.

    WAIT and STOP are first-class and are logged like any other decision. That
    is what makes this an agent with judgement rather than a dunning cron job.
    """

    WAIT = "WAIT"
    SOFT_REMINDER = "SOFT_REMINDER"
    PAYMENT_LINK = "PAYMENT_LINK"
    PHONE_FOLLOWUP = "PHONE_FOLLOWUP"
    ESCALATE_HUMAN = "ESCALATE_HUMAN"
    STOP = "STOP"


class Flag(StrEnum):
    """Ground-truth facts about a record. Never in the reasoner snapshot.

    DISPUTED                  the payer has a genuine grievance
    ALREADY_PAID_UNRECONCILED the money has left the payer; our books are stale
    HARDSHIP_CLAIMED          real distress, not a stall
    """

    DISPUTED = "DISPUTED"
    ALREADY_PAID_UNRECONCILED = "ALREADY_PAID_UNRECONCILED"
    HARDSHIP_CLAIMED = "HARDSHIP_CLAIMED"


class Archetype(StrEnum):
    """Payer behaviour class. Ground truth; drives the adjudicator only."""

    RELIABLE_BUT_SLOW = "RELIABLE_BUT_SLOW"
    CHRONIC_LATE = "CHRONIC_LATE"
    DISPUTING = "DISPUTING"
    DISTRESSED = "DISTRESSED"
    SILENT = "SILENT"
    PAID_UNRECONCILED = "PAID_UNRECONCILED"


class MessageCategory(StrEnum):
    """TRAI DLT header category suffix.

    P promotional · S service · T transactional · G government.
    The contact-window rule that applies depends on this classification, which
    is why it is a field on every drafted message rather than an afterthought.
    """

    P = "P"
    S = "S"
    T = "T"
    G = "G"


class Channel(StrEnum):
    """How a contact reaches the payer."""

    EMAIL = "EMAIL"
    SMS = "SMS"
    PHONE = "PHONE"


class Arm(StrEnum):
    """Which strategy produced a row. All arms share the seed and the world.

    CONTROL is the do-nothing floor: it never contacts anybody, and on this book
    it still recovers roughly half the value, because most payers settle on
    their own cycle. It is not a joke entry. Reporting AGENT against BASELINE
    alone would let both claim credit for money that was going to arrive
    regardless, and the whole argument of this project is about which contacts
    were worth making.

    The arm is stamped on every audit row, so a metric layer can separate four
    runs without keying on `run_id` conventions.
    """

    AGENT = "AGENT"
    BASELINE = "BASELINE"
    POLICY_BASELINE = "POLICY_BASELINE"
    CONTROL = "CONTROL"


class RecordSource(StrEnum):
    """Where an at-risk record came from. One ledger, several intakes."""

    INVOICE = "INVOICE"
    FAILED_PAYMENT = "FAILED_PAYMENT"
    FAILED_MANDATE = "FAILED_MANDATE"


class VerdictKind(StrEnum):
    """What the policy engine did to a proposal."""

    APPROVED = "APPROVED"
    MODIFIED = "MODIFIED"
    VETOED = "VETOED"


class RuleKind(StrEnum):
    """Provenance of a policy rule.

    REGULATORY carries a citation and must be verified at the issuing body.
    MERCHANT is business policy and is labelled as such everywhere it renders.
    A merchant rule is never dressed up as regulatory. See docs/ISSUES.md
    ISS-006 through ISS-009.
    """

    REGULATORY = "REGULATORY"
    MERCHANT = "MERCHANT"


class ExecutorKind(StrEnum):
    """Where an action actually landed. LIVE rows touched the Razorpay API."""

    SIMULATED = "SIMULATED"
    LIVE = "LIVE"


class PaymentEventKind(StrEnum):
    """Money events on a payer's prior invoices, and on this one."""

    ISSUED = "ISSUED"
    PAID_FULL = "PAID_FULL"
    PAID_PARTIAL = "PAID_PARTIAL"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    WRITTEN_OFF = "WRITTEN_OFF"


class OutcomeKind(StrEnum):
    """What the world did back, resolved by the adjudicator.

    Outcomes arrive in the audit log as NEW rows. Nothing is ever updated.
    """

    NO_RESPONSE = "NO_RESPONSE"
    REPLIED = "REPLIED"
    PROMISED = "PROMISED"
    PAID_FULL = "PAID_FULL"
    PAID_PARTIAL = "PAID_PARTIAL"
    DISPUTE_RAISED = "DISPUTE_RAISED"
    COMPLAINT = "COMPLAINT"
    ESCALATED = "ESCALATED"
    PROMISE_BROKEN = "PROMISE_BROKEN"
    WRITTEN_OFF = "WRITTEN_OFF"


class RowKind(StrEnum):
    """What an audit row records.

    A deliberate addition to the planned field list. It makes the raw audit view
    filterable without inferring the row type from which optional fields happen
    to be populated, and it gives `audit.replay` an explicit dispatch.

    INTAKE    the record entering the run, with the opening snapshot
    DECISION  a proposal, a policy verdict, and whatever action followed
    OUTCOME   what the world did back, on a later tick
    """

    INTAKE = "INTAKE"
    DECISION = "DECISION"
    OUTCOME = "OUTCOME"


class FreeTextKind(StrEnum):
    """Which free-text surface a corpus template writes into."""

    PAYER_NOTE = "PAYER_NOTE"
    EMAIL_REPLY = "EMAIL_REPLY"
    DISPUTE_DESCRIPTION = "DISPUTE_DESCRIPTION"


class SignalKind(StrEnum):
    """What a piece of free text actually carries.

    Corpus tagging, and ground truth for evaluating whether the reasoner read
    the text correctly. **The tag's own vocabulary must not appear in the
    template body** -- a note that says "we dispute this" is a regex, not a
    reasoning task. See docs/SEED-DISTRIBUTION.md.
    """

    PROMISE_EXPLICIT = "PROMISE_EXPLICIT"
    PROMISE_VAGUE = "PROMISE_VAGUE"
    PAYMENT_CYCLE = "PAYMENT_CYCLE"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    DOC_MISSING = "DOC_MISSING"
    PO_MISMATCH = "PO_MISMATCH"
    GRN_MISMATCH = "GRN_MISMATCH"
    QUALITY_COMPLAINT = "QUALITY_COMPLAINT"
    TDS_DEDUCTION = "TDS_DEDUCTION"
    GST_MISMATCH = "GST_MISMATCH"
    ALREADY_PAID = "ALREADY_PAID"
    PARTIAL_CONFUSION = "PARTIAL_CONFUSION"
    DUPLICATE_CLAIM = "DUPLICATE_CLAIM"
    ENTITY_MISMATCH = "ENTITY_MISMATCH"
    BANK_REJECTION = "BANK_REJECTION"
    ONBOARDING_PENDING = "ONBOARDING_PENDING"
    HARDSHIP = "HARDSHIP"
    SETTLEMENT_REQUEST = "SETTLEMENT_REQUEST"
    ESCALATION_THREAT = "ESCALATION_THREAT"
    CONTACT_CHURN = "CONTACT_CHURN"
    CHANNEL_REQUEST = "CHANNEL_REQUEST"
    CONSOLIDATION_REQUEST = "CONSOLIDATION_REQUEST"
    ANNOYED_AT_CHASING = "ANNOYED_AT_CHASING"
    SEASONAL_DELAY = "SEASONAL_DELAY"
    MSME_REFERENCE = "MSME_REFERENCE"
    CENTRALISATION_HINT = "CENTRALISATION_HINT"
    AUTHORITY_CHANGE = "AUTHORITY_CHANGE"
    SYSTEM_MIGRATION = "SYSTEM_MIGRATION"
    SCOPE_PAUSE = "SCOPE_PAUSE"


#: Signals that, taken together across one parent group in one week, are what
#: the batch-level insight (build spec section 7b) has to notice. No template
#: carrying one of these may name the cause literally.
CLUSTER_SIGNALS: frozenset[SignalKind] = frozenset(
    {
        SignalKind.CENTRALISATION_HINT,
        SignalKind.AUTHORITY_CHANGE,
        SignalKind.SYSTEM_MIGRATION,
        SignalKind.SCOPE_PAUSE,
    }
)

#: Interventions that put a message in front of the payer. Used by the contact
#: accounting in the ledger and by every merchant contact-frequency rule.
CONTACT_INTERVENTIONS: frozenset[Intervention] = frozenset(
    {
        Intervention.SOFT_REMINDER,
        Intervention.PAYMENT_LINK,
        Intervention.PHONE_FOLLOWUP,
    }
)
