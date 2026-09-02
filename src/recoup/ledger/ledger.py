"""The ledger: the system of record. Phase 1.

NOT Razorpay. State transitions are the only way state changes.

    AT_RISK -> CONTACTED -> PROMISED -> PAID
                         -> DISPUTED -> HUMAN_QUEUE
                         -> EXHAUSTED -> WRITTEN_OFF

Two deliberate extensions to the diagram in build spec section 2, both of which
change what the measurement means:

1. **Terminal is PAID and WRITTEN_OFF only.** EXHAUSTED and HUMAN_QUEUE can
   still receive a payment. A payer who settles on their own 45-day cycle pays
   whether or not anyone chased them, so a record the agent stopped chasing is
   not automatically a record the agent lost. Without this, STOP and WAIT are
   pure concessions and the agent can never win by declining to act -- which is
   precisely the behaviour the project exists to demonstrate.

2. **WRITTEN_OFF is reached only at run finalisation**, from EXHAUSTED. Nothing
   writes it off mid-run.

Everything in this module that mutates a record does so through `transition`,
which validates against `ALLOWED_TRANSITIONS` and raises rather than silently
accepting a nonsense move. `tests/test_ledger.py` asserts that no module
outside `recoup.ledger` assigns to `.state`.
"""

from __future__ import annotations

from recoup.domain.enums import (
    Channel,
    Intervention,
    MessageCategory,
    OutcomeKind,
    RecordState,
)
from recoup.domain.interventions import spec
from recoup.domain.models import (
    ActionRecord,
    ContactAttempt,
    Invoice,
    OutcomeRecord,
    Tick,
)
from recoup.ledger.clock import ticks_for_days

#: Terminal states. Nothing leaves these.
TERMINAL_STATES: frozenset[RecordState] = frozenset({RecordState.PAID, RecordState.WRITTEN_OFF})

#: The state machine, in full. A move not listed here is a bug, not a surprise.
ALLOWED_TRANSITIONS: dict[RecordState, frozenset[RecordState]] = {
    RecordState.AT_RISK: frozenset(
        {
            RecordState.AT_RISK,
            RecordState.CONTACTED,
            RecordState.PROMISED,
            RecordState.PAID,
            RecordState.DISPUTED,
            RecordState.HUMAN_QUEUE,
            RecordState.EXHAUSTED,
        }
    ),
    RecordState.CONTACTED: frozenset(
        {
            RecordState.CONTACTED,
            RecordState.PROMISED,
            RecordState.PAID,
            RecordState.DISPUTED,
            RecordState.HUMAN_QUEUE,
            RecordState.EXHAUSTED,
        }
    ),
    RecordState.PROMISED: frozenset(
        {
            RecordState.PROMISED,
            RecordState.CONTACTED,
            RecordState.PAID,
            RecordState.DISPUTED,
            RecordState.HUMAN_QUEUE,
            RecordState.EXHAUSTED,
        }
    ),
    RecordState.DISPUTED: frozenset(
        {
            RecordState.DISPUTED,
            RecordState.HUMAN_QUEUE,
            RecordState.PAID,
            RecordState.WRITTEN_OFF,
        }
    ),
    RecordState.HUMAN_QUEUE: frozenset(
        {
            RecordState.HUMAN_QUEUE,
            RecordState.DISPUTED,
            RecordState.PAID,
            RecordState.WRITTEN_OFF,
        }
    ),
    RecordState.EXHAUSTED: frozenset(
        {
            RecordState.EXHAUSTED,
            RecordState.DISPUTED,
            RecordState.HUMAN_QUEUE,
            RecordState.PAID,
            RecordState.WRITTEN_OFF,
        }
    ),
    RecordState.PAID: frozenset(),
    RecordState.WRITTEN_OFF: frozenset(),
}

#: How long a payer-level contact-frequency window runs, in ticks.
CONTACT_WINDOW_TICKS: int = ticks_for_days(30)


class IllegalTransition(RuntimeError):
    """A state move the machine does not allow. Raised, never swallowed."""

    def __init__(self, record_id: str, current: RecordState, target: RecordState) -> None:
        super().__init__(f"{record_id}: {current} -> {target} is not a permitted transition")
        self.record_id = record_id
        self.current = current
        self.target = target


#: States the automated loop no longer proposes actions in, though the record
#: is not finished and can still be paid.
#:
#: HUMAN_QUEUE means a person has the case. Whether it got there by the agent
#: escalating or by the payer complaining, the machine is done with it, and a
#: run that kept proposing on it would be reporting agent decisions a human had
#: already superseded. DISPUTED is deliberately NOT here: whether to keep
#: acting on a disputed record is a policy judgement, and Phase 2's hard-stop
#: rule is where that judgement belongs -- not baked into the ledger.
UNATTENDED_STATES: frozenset[RecordState] = frozenset({RecordState.HUMAN_QUEUE})


def is_terminal(state: RecordState) -> bool:
    """Whether a record in this state can still change."""
    return state in TERMINAL_STATES


def _legal(current: RecordState, target: RecordState) -> RecordState:
    """`target` if the machine permits it from `current`, otherwise no move.

    The transition table is the single source of truth about what can happen.
    A derivation function that contradicts it does not make the move legal, it
    just moves the crash from `transition` to somewhere less obvious.
    """
    return target if target in ALLOWED_TRANSITIONS[current] else current


def state_after_action(current: RecordState, intervention: Intervention) -> RecordState:
    """Pure. The state a record reaches by the agent acting on it.

    Shared with `audit.replay`, which is what makes the replay acceptance test
    meaningful: the log is re-run through the same machine rather than being
    asked to remember an answer.
    """
    if is_terminal(current):
        return current
    if intervention is Intervention.ESCALATE_HUMAN:
        return _legal(current, RecordState.HUMAN_QUEUE)
    if intervention is Intervention.STOP:
        # STOP means "automation stops chasing", and it moves a record to
        # EXHAUSTED only from the states where chasing was the active mode.
        # From DISPUTED or HUMAN_QUEUE the chase had already halted for a
        # substantive reason -- an unresolved objection, a person holding the
        # case -- and STOP merely confirms it. Marking those EXHAUSTED would
        # feed them to `finalise` and write them off, turning an open
        # commercial matter into a settled loss in the metric table.
        #
        # Driven off ALLOWED_TRANSITIONS rather than a second list, so the
        # state machine stays the one place this is decided.
        return _legal(current, RecordState.EXHAUSTED)
    if spec(intervention).is_contact and current is RecordState.AT_RISK:
        return _legal(current, RecordState.CONTACTED)
    return current


def state_after_outcome(current: RecordState, outcome: OutcomeKind) -> RecordState:
    """Pure. The state a record reaches by the world responding.

    Shared with `audit.replay`. See `state_after_action`.

    Every branch below is filtered through `_legal`, so this function can never
    name a move the table forbids. That guard is not decorative: WRITTEN_OFF is
    reachable only from EXHAUSTED and only at finalisation, and without the
    filter an outcome row carrying it would write off an AT_RISK record --
    turning a live receivable into a booked loss on the strength of one log
    line.
    """
    if is_terminal(current):
        return current
    match outcome:
        case OutcomeKind.PAID_FULL:
            return _legal(current, RecordState.PAID)
        case OutcomeKind.PROMISED:
            return _legal(current, RecordState.PROMISED)
        case OutcomeKind.DISPUTE_RAISED:
            return _legal(current, RecordState.DISPUTED)
        case OutcomeKind.COMPLAINT | OutcomeKind.ESCALATED:
            return _legal(current, RecordState.HUMAN_QUEUE)
        case OutcomeKind.PROMISE_BROKEN:
            return RecordState.CONTACTED if current is RecordState.PROMISED else current
        case OutcomeKind.REPLIED:
            return RecordState.CONTACTED if current is RecordState.AT_RISK else current
        case OutcomeKind.WRITTEN_OFF:
            return _legal(current, RecordState.WRITTEN_OFF)
        case OutcomeKind.PAID_PARTIAL | OutcomeKind.NO_RESPONSE:
            return current
    return current


class Ledger:
    """The system of record for one run of one arm.

    Holds every record, and is the only thing in the codebase permitted to
    write `Invoice.state`.
    """

    def __init__(self, invoices: list[Invoice]) -> None:
        # Sorted by id so that iteration order is a property of the data and not
        # of insertion. Both arms must walk the batch in the same order or the
        # comparison is measuring dictionary layout.
        self._records: dict[str, Invoice] = {
            inv.invoice_id: inv for inv in sorted(invoices, key=lambda i: i.invoice_id)
        }

    # -- reading -------------------------------------------------------------

    @property
    def records(self) -> list[Invoice]:
        """Every record, in stable id order."""
        return list(self._records.values())

    def get(self, invoice_id: str) -> Invoice:
        """One record by id. Raises KeyError if it is not in this batch."""
        return self._records[invoice_id]

    def active(self) -> list[Invoice]:
        """Records that can still change."""
        return [r for r in self._records.values() if not is_terminal(r.state)]

    def due_for_review(self, tick: Tick) -> list[Invoice]:
        """Records the automated loop should look at now.

        This is the decision-cadence gate. It is what keeps the reasoner at a
        few hundred calls per run rather than one per record per tick.

        Excludes `UNATTENDED_STATES` as well as terminal ones. A record that
        reached HUMAN_QUEUE because the payer complained never had its review
        tick pushed out -- only the ESCALATE_HUMAN *action* does that -- so
        without this filter the agent would carry on proposing actions on cases
        a human had already taken over.
        """
        return [
            r
            for r in self.active()
            if tick >= r.next_review_tick and r.state not in UNATTENDED_STATES
        ]

    def payer_contacts_since(self, payer_id: str, tick: Tick) -> int:
        """Contacts to a payer at or after `tick`, across ALL of their invoices.

        A payer with nine open bills must not receive nine times the messages,
        so the merchant frequency rule is scored here rather than per invoice.
        """
        return sum(
            r.contact_ledger.count_since(tick)
            for r in self._records.values()
            if r.payer_id == payer_id
        )

    def group_records(self, parent_group_id: str) -> list[Invoice]:
        """Every record belonging to one parent group. Feeds the batch insight."""
        return [r for r in self._records.values() if r.parent_group_id == parent_group_id]

    # -- writing -------------------------------------------------------------

    def transition(self, record: Invoice, target: RecordState, tick: Tick) -> RecordState:
        """Move a record. THE ONLY PLACE `Invoice.state` IS ASSIGNED.

        A no-op move is allowed and returns without touching the record, so
        callers can pass a computed target unconditionally.
        """
        current = record.state
        if target is current:
            return current
        if target not in ALLOWED_TRANSITIONS[current]:
            raise IllegalTransition(record.invoice_id, current, target)
        record.state = target
        if target in TERMINAL_STATES and record.resolved_tick is None:
            record.resolved_tick = tick
        return target

    def record_action(
        self,
        record: Invoice,
        intervention: Intervention,
        tick: Tick,
        *,
        executed: bool = True,
        next_review_override: Tick | None = None,
    ) -> ActionRecord:
        """Apply an approved action: cost it, log the contact, set the next review.

        `executed=False` records a vetoed proposal. A veto still consumes a
        review slot -- the agent looked at the record and was stopped -- but it
        makes no contact, spends no budget, and does not move the state. A
        deferring rule can supply the next admissible tick explicitly.
        """
        details = spec(intervention)
        if next_review_override is not None and next_review_override <= tick:
            raise ValueError("next_review_override must be later than the action tick")
        next_review_tick = next_review_override or tick + details.review_ticks
        if not executed:
            record.next_review_tick = next_review_tick
            return ActionRecord(intervention=intervention, executed=False)

        channel: Channel | None = details.channel
        category: MessageCategory | None = details.correct_category
        if details.is_contact and channel is not None:
            record.contact_ledger.attempts.append(
                ContactAttempt(
                    tick=tick,
                    intervention=intervention,
                    channel=channel,
                    # Voice carries no DLT header; classify it as service for
                    # the contact log so the field is never null downstream.
                    category=category or MessageCategory.S,
                )
            )
        if details.api_units:
            record.contact_ledger.payment_links_sent += details.api_units

        self.transition(record, state_after_action(record.state, intervention), tick)
        record.next_review_tick = next_review_tick

        return ActionRecord(
            intervention=intervention,
            executed=True,
            channel=channel,
            category=category,
            contact_units=details.contact_units,
            api_units=details.api_units,
        )

    def record_outcome(self, record: Invoice, outcome: OutcomeRecord, tick: Tick) -> RecordState:
        """Apply what the world did back. Money lands here and nowhere else."""
        if outcome.kind in (OutcomeKind.PAID_FULL, OutcomeKind.PAID_PARTIAL):
            record.recovered_paise = min(
                record.amount_paise, record.recovered_paise + outcome.amount_paise
            )
        if outcome.kind is OutcomeKind.PROMISE_BROKEN:
            record.promise_phrase = None
            record.promise_due_tick = None
        return self.transition(record, state_after_outcome(record.state, outcome.kind), tick)

    def set_promise(self, record: Invoice, phrase: str, due_tick: Tick | None, tick: Tick) -> None:
        """Attach a promise. The PHRASE comes from the reasoner, the TICK from the clock.

        `due_tick` is None when the phrase named nothing resolvable, and the
        caller must not suppress contact in that case. See
        `ledger.clock.resolve_promise_phrase`.

        The promise is always RECORDED; the state move is conditional. A payer
        whose record already sits in HUMAN_QUEUE or DISPUTED can still send a
        reply committing to a date -- a contact was often already in flight when
        the escalation happened -- but that commitment must not pull the record
        back into the automated loop, because a human owns it now. So the phrase
        and the due tick are kept as information, the record stays where it is,
        and `resolve_promise` will still let that payer pay. Promoting it back
        to PROMISED would silently hand a human's case back to the machine.
        """
        record.promise_phrase = phrase
        record.promise_due_tick = due_tick
        if due_tick is not None and RecordState.PROMISED in ALLOWED_TRANSITIONS[record.state]:
            self.transition(record, RecordState.PROMISED, tick)

    def awaiting_write_off(self) -> list[Invoice]:
        """Records the end of the run should write off: everything still EXHAUSTED.

        Returns them rather than moving them. The write-off is a state change
        like any other and must arrive with an audit row attached, so the
        RUNNER applies it through the same outcome path as everything else --
        see `runner.batch`. An earlier version moved them here and logged
        nothing, which left `audit.replay` unable to reconstruct the closing
        position from the log and quietly reproducing it from a copy of this
        logic instead. A replay that re-derives the answer is not a check.

        Nothing else moves. Records left in AT_RISK, CONTACTED, PROMISED,
        DISPUTED or HUMAN_QUEUE stay there and are reported as unresolved,
        because pretending an open receivable is settled is the one thing the
        metric table must not do.
        """
        return [r for r in self._records.values() if r.state is RecordState.EXHAUSTED]
