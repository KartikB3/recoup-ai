"""The ledger, the clock, and the invariants enforced by reading source. Phase 1.

Two of these tests grep the codebase rather than call it. That is deliberate.
"No `datetime.now()` in domain code" and "only the ledger assigns `.state`" are
properties of the SOURCE, and there is no runtime assertion that catches them --
a wall-clock call in a rarely-taken branch would pass every behavioural test in
this suite and then make the demo unreproducible.
"""

from __future__ import annotations

import ast
import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from recoup.domain.enums import Intervention, OutcomeKind, RecordState
from recoup.domain.models import VIRTUAL_EPOCH, OutcomeRecord
from recoup.generator.generate import generate_batch
from recoup.ledger import clock
from recoup.ledger.ledger import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    UNATTENDED_STATES,
    IllegalTransition,
    Ledger,
    is_terminal,
    state_after_action,
    state_after_outcome,
)

SRC = Path(__file__).resolve().parents[1] / "src" / "recoup"

#: Packages in which a wall-clock call would break reproducibility outright.
NO_WALL_CLOCK_PACKAGES = ("domain", "ledger", "policy", "reasoner", "runner", "baseline")

_WALL_CLOCK = re.compile(r"datetime\.now\(|date\.today\(|time\.time\(")

#: Attribute names that read the real clock. Matched on parsed CALL nodes, not
#: on raw text: three of these modules declare the invariant in their own
#: docstrings ("No `datetime.now()` ... anywhere below"), and a text scan
#: dutifully reports the declaration as a violation of itself.
_WALL_CLOCK_ATTRS = frozenset({"now", "today", "time", "monotonic", "perf_counter"})
_STATE_ASSIGN = re.compile(r"^\s*[\w\.\[\]]*\.state\s*=(?!=)", re.MULTILINE)


# ---------------------------------------------------------------------------
# source-level invariants
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("package", NO_WALL_CLOCK_PACKAGES)
def test_no_wall_clock_anywhere_it_would_matter(package: str) -> None:
    """INVARIANT 2. All dates are virtual.

    A single `datetime.now()` in a branch nobody exercises makes the run
    unreproducible on a different day, and every determinism test here would
    still pass.
    """
    offenders: list[str] = []
    for path in sorted((SRC / package).rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in _WALL_CLOCK_ATTRS:
                source = ast.unparse(func)
                if _WALL_CLOCK.search(source + "("):
                    offenders.append(f"{path.name}:{node.lineno}: {source}()")
    assert not offenders, offenders


def test_only_the_ledger_assigns_record_state() -> None:
    """The state machine is bypassable in exactly one place, and that place is `Ledger`.

    Everything else must go through `transition`, which validates against
    `ALLOWED_TRANSITIONS` and raises. An assignment elsewhere would move a
    record into a state the machine forbids, silently.
    """
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if path.parent.name == "ledger":
            continue
        text = path.read_text(encoding="utf-8")
        for match in _STATE_ASSIGN.finditer(text):
            line = text[: match.end()].count("\n") + 1
            offenders.append(f"{path.relative_to(SRC)}:{line}")
    assert not offenders, f"`.state` assigned outside recoup.ledger: {offenders}"


# ---------------------------------------------------------------------------
# the clock
# ---------------------------------------------------------------------------


def test_the_tick_grid_matches_the_plan() -> None:
    """1 tick = 6 virtual hours; 112 ticks = 28 virtual days."""
    assert clock.HOURS_PER_TICK == 6
    assert clock.TICKS_PER_DAY == 4
    assert clock.DEFAULT_HORIZON == 112
    assert clock.DEFAULT_HORIZON * clock.HOURS_PER_TICK == 28 * 24


def test_the_epoch_offset_separates_the_two_contact_windows() -> None:
    """The 08:00 anchor is load-bearing, not cosmetic.

    On a midnight grid the RBI (08:00-19:00) and TRAI (10:00-21:00) windows
    admit exactly the same ticks and become indistinguishable on screen. Offset
    by eight hours they disagree at 08:00 and at 20:00, so each rule gets its
    own visible moment in the Phase 5 timeline.
    """
    hours = {clock.hour_of_day(t) for t in range(clock.TICKS_PER_DAY)}
    assert hours == {2, 8, 14, 20}
    rbi = {h for h in hours if 8 <= h < 19}
    trai = {h for h in hours if 10 <= h < 21}
    assert rbi != trai, "the two windows must not admit the same ticks"


def test_virtual_dates_advance_monotonically() -> None:
    """Days must not go backwards, and 112 ticks must cover 28 days."""
    days = [clock.virtual_date(t) for t in range(clock.DEFAULT_HORIZON)]
    assert days == sorted(days)
    assert days[0] == VIRTUAL_EPOCH
    # 112 ticks is 672 hours, exactly 28 days of ELAPSED time -- but the grid
    # starts at 08:00, so the final tick falls at 02:00 on day 28 and the run
    # touches 29 calendar dates. Both statements are true; only the first is
    # the one the plan fixes.
    assert clock.DEFAULT_HORIZON * clock.HOURS_PER_TICK == 28 * 24
    assert (days[-1] - days[0]).days == 28
    assert clock.hour_of_day(clock.DEFAULT_HORIZON - 1) == 2


@pytest.mark.parametrize(
    "phrase",
    ["after the festival break", "in due course", "shortly", "once the season picks up", ""],
)
def test_unresolvable_promises_return_none(phrase: str) -> None:
    """Returning None matters as much as returning a tick.

    These are real things payers say and they are not dates. Suppressing
    contact on one would be a bug that looks like a feature.
    """
    assert clock.resolve_promise_phrase(phrase, 0) is None


@pytest.mark.parametrize(
    "phrase",
    [
        "by Friday",
        "within 7 working days",
        "before month end",
        "next week",
        "tomorrow",
        "in the next payment run, on the 25th",
        "in 2 weeks",
        "by the weekend",
    ],
)
def test_resolvable_promises_land_in_the_future(phrase: str) -> None:
    """A resolved deadline must be after the tick it was read on."""
    resolved = clock.resolve_promise_phrase(phrase, 20)
    assert resolved is not None, phrase
    assert resolved > 20, phrase


def test_a_deadline_resolves_to_the_end_of_its_day() -> None:
    """ "By Friday" is honoured at any point on Friday, not at 02:00."""
    friday = clock.resolve_promise_phrase("by Friday", 0)
    assert friday is not None
    assert clock.hour_of_day(friday) == 20
    assert clock.virtual_date(friday).weekday() == 4


# ---------------------------------------------------------------------------
# the state machine
# ---------------------------------------------------------------------------


def test_every_state_appears_in_the_transition_table() -> None:
    """A state missing from the table raises KeyError deep inside a run."""
    assert set(ALLOWED_TRANSITIONS) == set(RecordState)


def test_terminal_states_are_exactly_paid_and_written_off() -> None:
    """EXHAUSTED and HUMAN_QUEUE can still receive a payment. That is the design.

    Without it, STOP and WAIT are pure concessions and the agent can never win
    by declining to act -- which is the behaviour this project exists to show.
    """
    assert set(TERMINAL_STATES) == {RecordState.PAID, RecordState.WRITTEN_OFF}
    for state in TERMINAL_STATES:
        assert not ALLOWED_TRANSITIONS[state], f"{state} is not terminal"
    assert RecordState.PAID in ALLOWED_TRANSITIONS[RecordState.EXHAUSTED]
    assert RecordState.PAID in ALLOWED_TRANSITIONS[RecordState.HUMAN_QUEUE]


def test_stop_never_writes_off_a_case_a_human_owns() -> None:
    """STOP from HUMAN_QUEUE or DISPUTED is a no-op, not a demotion to EXHAUSTED.

    Marking those EXHAUSTED would feed them to `finalise` and write them off,
    turning an open commercial matter into a settled loss in the metric table.
    """
    for state in (RecordState.HUMAN_QUEUE, RecordState.DISPUTED):
        assert state_after_action(state, Intervention.STOP) is state


def test_state_after_action_never_proposes_an_illegal_move() -> None:
    """The pure function and the table must agree, for every pair."""
    for state in RecordState:
        for intervention in Intervention:
            target = state_after_action(state, intervention)
            assert target is state or target in ALLOWED_TRANSITIONS[state], (state, intervention)


def test_state_after_outcome_never_proposes_an_illegal_move() -> None:
    """Same, for everything the world can do back."""
    for state in RecordState:
        for outcome in OutcomeKind:
            target = state_after_outcome(state, outcome)
            assert target is state or target in ALLOWED_TRANSITIONS[state], (state, outcome)


def test_terminal_records_never_move() -> None:
    """Once PAID or WRITTEN_OFF, nothing changes a record."""
    for state in TERMINAL_STATES:
        for intervention in Intervention:
            assert state_after_action(state, intervention) is state
        for outcome in OutcomeKind:
            assert state_after_outcome(state, outcome) is state


def test_illegal_transition_raises_rather_than_silently_accepting() -> None:
    """A nonsense move must be a crash, not a surprise in the metric table."""
    ledger = Ledger(generate_batch(42).records[:3])
    record = ledger.records[0]
    ledger.transition(record, RecordState.PAID, 0)
    with pytest.raises(IllegalTransition):
        ledger.transition(record, RecordState.AT_RISK, 1)


def test_resolved_tick_is_stamped_once_and_only_at_terminal() -> None:
    """The metric table reads this; a second stamp would move a record's age."""
    ledger = Ledger(generate_batch(42).records[:3])
    record = ledger.records[0]
    ledger.transition(record, RecordState.CONTACTED, 5)
    assert record.resolved_tick is None
    ledger.transition(record, RecordState.PAID, 9)
    assert record.resolved_tick == 9


def test_a_promise_does_not_reclaim_a_case_from_a_human() -> None:
    """The phrase is recorded; the state does not move back into automation."""
    ledger = Ledger(generate_batch(42).records[:3])
    record = ledger.records[0]
    ledger.transition(record, RecordState.HUMAN_QUEUE, 4)
    ledger.set_promise(record, "by Friday", clock.resolve_promise_phrase("by Friday", 4), 4)
    assert record.state is RecordState.HUMAN_QUEUE
    assert record.promise_phrase == "by Friday"
    assert record.promise_due_tick is not None


def test_unattended_records_are_not_reviewed() -> None:
    """A record a human owns must leave the automated rotation.

    HUMAN_QUEUE reached by a COMPLAINT never had its review tick pushed out --
    only the ESCALATE_HUMAN action does that -- so without this filter the
    agent keeps proposing on cases a person already took over.
    """
    ledger = Ledger(generate_batch(42).records[:5])
    record = ledger.records[0]
    assert record in ledger.due_for_review(0)
    ledger.transition(record, RecordState.HUMAN_QUEUE, 0)
    assert RecordState.HUMAN_QUEUE in UNATTENDED_STATES
    assert record not in ledger.due_for_review(0)


def test_contacts_are_counted_per_payer_not_per_invoice() -> None:
    """A payer with nine open bills must not receive nine times the messages."""
    batch = generate_batch(42)
    grouped: dict[str, list[str]] = {}
    for record in batch.records:
        grouped.setdefault(record.payer_id, []).append(record.invoice_id)
    payer_id = next(p for p, ids in grouped.items() if len(ids) > 1)

    ledger = Ledger(batch.records)
    for invoice_id in grouped[payer_id]:
        ledger.record_action(ledger.get(invoice_id), Intervention.SOFT_REMINDER, 4)
    assert ledger.payer_contacts_since(payer_id, 0) == len(grouped[payer_id])


def test_a_vetoed_action_costs_nothing_but_a_review_slot() -> None:
    """The veto is the most interesting row in the log; it must not spend budget."""
    ledger = Ledger(generate_batch(42).records[:3])
    record = ledger.records[0]
    before = record.state
    action = ledger.record_action(record, Intervention.PAYMENT_LINK, 6, executed=False)
    assert action.executed is False
    assert action.contact_units == 0
    assert action.api_units == 0
    assert record.contact_ledger.count == 0
    assert record.contact_ledger.payment_links_sent == 0
    assert record.state is before
    assert record.next_review_tick > 6


def test_awaiting_write_off_selects_only_exhausted_records() -> None:
    """Pretending an open receivable is settled is the one thing metrics must not do."""
    ledger = Ledger(generate_batch(42).records[:6])
    records = ledger.records
    ledger.transition(records[0], RecordState.EXHAUSTED, 10)
    ledger.transition(records[1], RecordState.DISPUTED, 10)
    ledger.transition(records[2], RecordState.HUMAN_QUEUE, 10)

    awaiting = ledger.awaiting_write_off()
    assert [r.invoice_id for r in awaiting] == [records[0].invoice_id]

    # Nothing has moved yet: the write-off is the RUNNER's to apply, so that it
    # arrives with an audit row rather than as an implied side effect.
    assert records[0].state is RecordState.EXHAUSTED
    assert records[1].state is RecordState.DISPUTED
    assert records[2].state is RecordState.HUMAN_QUEUE
    assert records[3].state is RecordState.AT_RISK


def test_money_only_lands_through_record_outcome() -> None:
    """Recovery clamps at the invoice value; a partial then a full does not double-count."""
    ledger = Ledger(generate_batch(42).records[:3])
    record = ledger.records[0]
    half = record.amount_paise // 2
    ledger.record_outcome(
        record, OutcomeRecord(kind=OutcomeKind.PAID_PARTIAL, amount_paise=half), 3
    )
    assert record.recovered_paise == half
    assert record.state is not RecordState.PAID

    ledger.record_outcome(
        record, OutcomeRecord(kind=OutcomeKind.PAID_FULL, amount_paise=record.amount_paise), 7
    )
    assert record.recovered_paise == record.amount_paise
    assert record.outstanding_paise == 0
    assert record.state is RecordState.PAID


def test_is_terminal_agrees_with_the_table() -> None:
    """Two sources of truth about terminality would eventually disagree."""
    for state in RecordState:
        assert is_terminal(state) == (not ALLOWED_TRANSITIONS[state])


def test_first_and_last_tick_bracket_their_day() -> None:
    """Promise deadlines depend on this; an off-by-one moves every due date."""
    day = VIRTUAL_EPOCH + timedelta(days=3)
    last = clock.last_tick_on(day)
    assert clock.virtual_date(last) == day
    assert clock.hour_of_day(last) == 20
    assert isinstance(day, date)
