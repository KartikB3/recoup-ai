"""Frozen domain contracts. Phase 1. See IMPLEMENTATION-PLAN section 2.

Invoice, FreeText, EmailReply, PaymentEvent, ContactLedger, VirtualDate,
LLMProposal, DraftedMessage, PromiseToPay, PolicyVerdict, RuleSource, AuditRow.

INVARIANTS enforced here, not downstream:
  - All money is int paise. Never float. Never rupees. Every monetary field is
    named `*_paise` and a test walks these models asserting the annotation is
    `int`.
  - All dates are virtual. `VirtualDate` is a plain `datetime.date` anchored to
    `VIRTUAL_EPOCH`, and nothing in the domain, ledger, policy or reasoner may
    call `datetime.now()` or `date.today()`. A test greps for both.
  - No numeric field on LLMProposal is ever used as money or as a date. The
    only number the model emits is `confidence`. A promise is returned as the
    phrase it found plus the span it quoted; the LEDGER turns that into a tick.

Ground truth vs. what the agent sees
------------------------------------
`Invoice` carries simulation ground truth -- `payer_archetype`, `flags`,
`provenance` -- because the adjudicator and the metrics need it. The reasoner
never does. `Invoice.to_snapshot()` is the only thing the reasoner is shown,
and it strips all three. `tests/test_domain.py` asserts that.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from recoup.domain.enums import (
    Archetype,
    Arm,
    Channel,
    ExecutorKind,
    Flag,
    Intervention,
    MessageCategory,
    OutcomeKind,
    PaymentEventKind,
    RecordSource,
    RecordState,
    RowKind,
    RuleKind,
    SignalKind,
    VerdictKind,
)

#: A virtual calendar date. A real `date` object with a fictional anchor, so
#: that date arithmetic, ordering and ISO serialisation all come for free. The
#: virtuality is enforced by the ban on `date.today()`, not by a wrapper type.
VirtualDate: TypeAlias = date

#: Money. Always an integer count of paise. There is no rupee type.
Paise: TypeAlias = int

#: Discrete virtual time. One tick is six virtual hours. See ledger.clock.
Tick: TypeAlias = int

#: Day zero of the simulated world. A Monday, chosen so that weekday-shaped
#: payer behaviour ("this week's run", "by Friday") lines up sensibly.
VIRTUAL_EPOCH: VirtualDate = date(2026, 4, 6)


def canonical_json(value: Any) -> str:
    """Serialise deterministically: sorted keys, no incidental whitespace.

    Used for the audit log's hash chain, for the reasoner's input-hash cache
    key, and for the byte-identical-batch gate. Two processes with different
    `PYTHONHASHSEED` values must produce the same string, which is why every
    set-valued field in this module has an explicit sorted serialiser.
    """
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def format_inr(amount_paise: Paise) -> str:
    """Render paise as rupees with Indian digit grouping. Presentation only.

    Never round-tripped back into a money value. The integer is the truth.
    """
    rupees, paise = divmod(abs(int(amount_paise)), 100)
    digits = str(rupees)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        parts: list[str] = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        digits = ",".join([*parts, tail])
    sign = "-" if amount_paise < 0 else ""
    return f"{sign}Rs {digits}.{paise:02d}"


class PaymentEvent(BaseModel):
    """A money event. Used for a payer's prior track record and for this bill."""

    model_config = ConfigDict(extra="forbid")

    kind: PaymentEventKind
    on: VirtualDate
    amount_paise: Paise
    reference: str | None = None
    note: str | None = None


class EmailReply(BaseModel):
    """One reply from the payer's accounts-payable desk. Free text the LLM reads."""

    model_config = ConfigDict(extra="forbid")

    received_on: VirtualDate
    from_name: str
    from_role: str
    subject: str
    body: str


class FreeText(BaseModel):
    """Everything unstructured attached to a record.

    This field is the LLM's entire reason for existing. If it is thin, the
    project is a rules engine with an API bill. See docs/SEED-DISTRIBUTION.md
    for the corpus that fills it.
    """

    model_config = ConfigDict(extra="forbid")

    payer_notes: str = ""
    email_replies: list[EmailReply] = Field(default_factory=list)
    dispute_description: str | None = None

    @property
    def is_empty(self) -> bool:
        """True when the record carries no free text at all. Silence is signal."""
        return not self.payer_notes and not self.email_replies and not self.dispute_description


class TextProvenance(BaseModel):
    """Which corpus templates produced this record's free text. GROUND TRUTH.

    Never shown to the reasoner. Exists so that docs/SEED-DISTRIBUTION.md can
    report corpus coverage honestly and so that a later evaluation can ask
    whether the model read the signal that was actually planted.
    """

    model_config = ConfigDict(extra="forbid")

    template_ids: list[str] = Field(default_factory=list)
    signals: list[SignalKind] = Field(default_factory=list)
    cluster_hint_strength: str | None = None


class ContactAttempt(BaseModel):
    """One contact that actually reached the payer. Written only by the ledger."""

    model_config = ConfigDict(extra="forbid")

    tick: Tick
    intervention: Intervention
    channel: Channel
    category: MessageCategory


class ContactLedger(BaseModel):
    """Per-invoice contact accounting. Read by the policy engine, written by the ledger.

    Payer-level frequency rules ("max 4 contacts per payer per 30 days") are
    aggregated across a payer's invoices by `ledger.Ledger.payer_contacts_since`,
    because a payer with nine open bills must not get nine times the messages.
    """

    model_config = ConfigDict(extra="forbid")

    attempts: list[ContactAttempt] = Field(default_factory=list)
    payment_links_sent: int = 0

    @property
    def count(self) -> int:
        """Total contacts made against this invoice."""
        return len(self.attempts)

    @property
    def last_tick(self) -> Tick | None:
        """Tick of the most recent contact, or None if never contacted."""
        return self.attempts[-1].tick if self.attempts else None

    def count_since(self, tick: Tick) -> int:
        """Contacts made at or after `tick`. Inclusive lower bound."""
        return sum(1 for a in self.attempts if a.tick >= tick)


class PromiseToPay(BaseModel):
    """A promise the reasoner found in free text.

    NOTE THE ABSENCE OF A DATE. The model returns the phrase and the span it
    quoted; `ledger.clock.resolve_promise_phrase` turns the phrase into a tick
    deterministically. This is the concrete form of invariant 3.
    """

    model_config = ConfigDict(extra="forbid")

    relative_phrase: str
    quote: str


class DraftedMessage(BaseModel):
    """A message the reasoner drafted. Content only -- never a number that matters."""

    model_config = ConfigDict(extra="forbid")

    channel: Channel
    category: MessageCategory
    subject: str | None = None
    body: str


class LLMProposal(BaseModel):
    """Reasoner output. Pydantic -> JSON Schema -> structured output.

    `confidence` is the ONLY numeric field, and it is used for abstention, never
    as money and never as a date. `intervention` is the closed enum, so a
    proposal outside the action space is not merely discouraged but impossible.
    """

    model_config = ConfigDict(extra="forbid")

    diagnosis: str
    intervention: Intervention
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    drafted_message: DraftedMessage | None = None
    extracted_promise: PromiseToPay | None = None


class RuleSource(BaseModel):
    """Provenance of a policy rule. Regulatory verification is load-bearing.

    A regulatory rule with `verified=False` renders with a visible chip and
    never appears in the video. Verification is not applicable to merchant
    policy, which is labelled merchant policy rather than given a false badge.
    `cited_date` is a real-world publication date and is a string on purpose,
    so it can never be confused with a `VirtualDate`.
    """

    model_config = ConfigDict(extra="forbid")

    kind: RuleKind
    title: str
    cited_date: str | None = None
    url: str | None = None
    verified: bool | None = None
    scope_caveat: str | None = None

    @model_validator(mode="after")
    def verification_matches_source_kind(self) -> RuleSource:
        """Require verification only where an issuing-body source exists."""
        if self.kind is RuleKind.REGULATORY and self.verified is None:
            raise ValueError("regulatory sources require a verification status")
        if self.kind is RuleKind.MERCHANT and self.verified is not None:
            raise ValueError("verification is not applicable to merchant policy")
        return self


class PolicyVerdict(BaseModel):
    """What the deterministic engine did to a proposal. Rendered verbatim in the UI."""

    model_config = ConfigDict(extra="forbid")

    verdict: VerdictKind
    original: Intervention
    final: Intervention | None
    rule_id: str | None = None
    rule_source: RuleSource | None = None
    explanation: str = ""
    defer_to_tick: Tick | None = None
    """When a "not now" verdict says the proposal could be reconsidered.

    A Phase 2 addition to the planned field list, and the reason is ISS-025.
    Contact-window rules are deferrals, not refusals: without somewhere to put
    the deferral the runner pushes the next review by the proposed
    intervention's usual interval, which is a whole number of virtual days, so
    a record blocked at 20:00 comes back at 20:00 and is blocked for the rest
    of the run.

    It is a TICK, not a date, and it is computed by the deterministic engine
    from the virtual clock -- never by a model. Invariant 3 is untouched: the
    field is on the verdict, not on `LLMProposal`. It is logged on the audit
    row, so `audit.replay` reads the deferral back out of the log rather than
    recomputing it.
    """


class ActionRecord(BaseModel):
    """What was actually done, after the policy engine had its say."""

    model_config = ConfigDict(extra="forbid")

    intervention: Intervention
    executed: bool
    executor: ExecutorKind = ExecutorKind.SIMULATED
    channel: Channel | None = None
    category: MessageCategory | None = None
    external_ref: str | None = None
    contact_units: int = 0
    api_units: int = 0


class OutcomeRecord(BaseModel):
    """What the world did back. Arrives as a NEW audit row, never as an update."""

    model_config = ConfigDict(extra="forbid")

    kind: OutcomeKind
    amount_paise: Paise = 0
    detail: str = ""


class Invoice(BaseModel):
    """The at-risk record. IMPLEMENTATION-PLAN section 2.1.

    Mutable, but only `ledger.ledger` is allowed to mutate `state`. A test
    asserts that no module outside `recoup.ledger` assigns to `.state`.
    """

    model_config = ConfigDict(extra="forbid")

    # --- identity -----------------------------------------------------------
    invoice_id: str
    parent_group_id: str | None = None
    payer_id: str
    payer_name: str
    payer_city: str
    payer_contact_name: str
    payer_contact_role: str

    # --- ground truth: never in the reasoner snapshot ------------------------
    payer_archetype: Archetype
    flags: set[Flag] = Field(default_factory=set)
    provenance: TextProvenance = Field(default_factory=TextProvenance)
    spotlight: bool = False

    # --- the money and the clock --------------------------------------------
    amount_paise: Paise
    issued_on: VirtualDate
    due_on: VirtualDate

    # --- observable state ----------------------------------------------------
    state: RecordState = RecordState.AT_RISK
    source: RecordSource = RecordSource.INVOICE
    history: list[PaymentEvent] = Field(default_factory=list)
    free_text: FreeText = Field(default_factory=FreeText)
    contact_ledger: ContactLedger = Field(default_factory=ContactLedger)

    # --- ledger runtime ------------------------------------------------------
    next_review_tick: Tick = 0
    recovered_paise: Paise = 0
    promise_phrase: str | None = None
    promise_due_tick: Tick | None = None
    resolved_tick: Tick | None = None

    @field_serializer("flags")
    def _serialize_flags(self, value: set[Flag]) -> list[str]:
        """Sorted, because set iteration order varies with PYTHONHASHSEED.

        Without this the byte-identical-batch gate fails across processes, and
        it fails intermittently, which is the worst way for it to fail.
        """
        return sorted(str(f) for f in value)

    @property
    def outstanding_paise(self) -> Paise:
        """Value still open on this invoice. Never negative.

        `Ledger.record_outcome` already clamps what it writes, so an overpayment
        should not arise -- but this property feeds the reasoner's snapshot and
        the metric table, and a negative receivable is not a meaningful quantity
        in either. Clamping here means the invariant holds on the model itself
        rather than resting on every writer's discipline.
        """
        return max(0, self.amount_paise - self.recovered_paise)

    def days_overdue(self, as_of: VirtualDate) -> int:
        """Days past the due date. Negative before it falls due.

        Derived from calendar dates, never from `tick // 4` -- the tick grid is
        offset from midnight, so the two disagree at day boundaries.
        """
        return (as_of - self.due_on).days

    def age_days(self, as_of: VirtualDate) -> int:
        """Days since the invoice was issued."""
        return (as_of - self.issued_on).days

    def to_snapshot(self, as_of: VirtualDate, tick: Tick) -> dict[str, Any]:
        """Exactly what the reasoner is allowed to see. Nothing else, ever.

        Excludes `payer_archetype`, `flags`, `provenance` and `spotlight`: those
        are the simulation's answer key. Including any of them would make the
        agent's performance meaningless and a judge would be right to say so.

        The metrics DO read `flags` -- scoring is allowed to see ground truth
        that the agent is not. That asymmetry is the point of a held-out label.
        """
        return {
            "invoice_id": self.invoice_id,
            "parent_group_id": self.parent_group_id,
            "payer_id": self.payer_id,
            "payer_name": self.payer_name,
            "payer_city": self.payer_city,
            "payer_contact_name": self.payer_contact_name,
            "payer_contact_role": self.payer_contact_role,
            "amount_paise": self.amount_paise,
            "outstanding_paise": self.outstanding_paise,
            "issued_on": self.issued_on.isoformat(),
            "due_on": self.due_on.isoformat(),
            "as_of": as_of.isoformat(),
            "tick": tick,
            "days_overdue": self.days_overdue(as_of),
            "state": str(self.state),
            "source": str(self.source),
            "history": [e.model_dump(mode="json") for e in self.history],
            "free_text": self.free_text.model_dump(mode="json"),
            "contacts_made": self.contact_ledger.count,
            "last_contact_tick": self.contact_ledger.last_tick,
            "payment_links_sent": self.contact_ledger.payment_links_sent,
            "promise_phrase": self.promise_phrase,
        }


class AuditRow(BaseModel):
    """One append-only row. Never updated; outcomes arrive as new rows.

    The eight fields of build spec section 6, plus `run_id`, `arm`, `row_id` and
    `prev_row_hash` from IMPLEMENTATION-PLAN section 2.4, plus `kind`.

    `kind` is a deliberate addition to the planned field list: it makes the raw
    audit view filterable without inferring row type from which optional fields
    happen to be populated, and it gives `audit.replay` an explicit dispatch.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str
    arm: Arm
    row_id: int
    prev_row_hash: str
    kind: RowKind

    tick: Tick
    record_id: str
    input_snapshot: dict[str, Any] | None = None
    llm_proposal: LLMProposal | None = None
    policy_verdict: PolicyVerdict | None = None
    policy_rule: str | None = None
    action: ActionRecord | None = None
    outcome: OutcomeRecord | None = None


def add_days(day: VirtualDate, days: int) -> VirtualDate:
    """Virtual date arithmetic. Exists so callers never reach for `timedelta`."""
    return day + timedelta(days=days)
