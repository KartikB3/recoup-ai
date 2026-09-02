"""The tick loop. Phase 2. The ONLY orchestrator.

Arm-agnostic. Everything else in this package is a component that this module
calls, which is what makes the baseline arm a short file rather than a fork of
the whole system.

INVARIANT 6 is the reason this file is worth reading closely. There is exactly
one tick loop in the project. The baseline does not get its own; the agent does
not get its own. They differ in one object -- the `Proposer` handed to
`run_batch` -- and in whether a `PolicyGate` is attached. Everything else, the
clock, the ledger, the adjudicator, the executor and the audit log, is shared.
If the two arms ever disagree about something other than what they proposed,
the comparison is measuring the runner and not the strategy.

Phase 1 status
--------------
This module is complete and exercised, with **no LLM in it**. The agent arm's
proposer arrives in Phase 2 as a component satisfying `Proposer`; until then
`NaiveChaser` and `AlwaysWait` drive it, which is enough to produce a real
audit log and put the replay acceptance test under load. The CLI `run` command
stays gated to Phase 2 on purpose: a `run` that silently means "baseline only"
would be a lie in the demo.

Order of business within one tick
---------------------------------
The sequence matters and is not arbitrary:

1. **Pending responses land.** A contact made earlier resolves now, after
   `RESPONSE_DELAY_TICKS`. Nobody replies in the same instant they are written
   to, and a run where they did would make the timeline view nonsense.
2. **Promises fall due.** Kept or broken, before anyone decides anything, so a
   broken promise is visible to the decision made moments later.
3. **The world moves on its own.** Spontaneous payment is drawn for every
   non-terminal record, contacted or not. This is what makes WAIT a real
   strategy rather than a forfeit.
4. **Only then does the agent act**, and only on records whose review tick has
   arrived and which are still open. A record that paid in step 3 is not
   chased in step 4, which is exactly the mistake a naive system makes.

Money and time
--------------
No `datetime.now()`, no `date.today()`. Every date in here comes from
`ledger.clock`, and every amount is integer paise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from recoup.audit.log import AuditLog
from recoup.domain.enums import (
    Arm,
    Intervention,
    OutcomeKind,
    RecordState,
    RowKind,
    VerdictKind,
)
from recoup.domain.interventions import spec
from recoup.domain.models import (
    Invoice,
    LLMProposal,
    PolicyVerdict,
    Tick,
    canonical_json,
)
from recoup.executor.base import Executor
from recoup.executor.simulated import SimulatedExecutor
from recoup.ledger.adjudicator import Adjudicator
from recoup.ledger.clock import (
    DEFAULT_HORIZON,
    VirtualClock,
    resolve_promise_phrase,
    virtual_date,
)
from recoup.ledger.ledger import CONTACT_WINDOW_TICKS, Ledger, is_terminal

#: Ticks between a contact going out and the payer's response landing. Two
#: ticks is twelve virtual hours: long enough that a reply is not instantaneous,
#: short enough that a 28-day run still shows several exchanges on one record.
RESPONSE_DELAY_TICKS: int = 2


@dataclass(frozen=True)
class Proposal:
    """What a proposer wants done, and its reasoning if it had any.

    `llm_proposal` is None for the deterministic arms and carries the model's
    structured output in Phase 2. Keeping it on the proposal rather than
    reaching for it later is what lets the audit row record what was proposed
    even when the policy engine vetoed it.
    """

    intervention: Intervention
    llm_proposal: LLMProposal | None = None


class Proposer(Protocol):
    """Decides what to do with one record. The ONLY thing the two arms differ in.

    Receives a SNAPSHOT, never the `Invoice`. That is a structural guarantee,
    not a convention: `to_snapshot` omits `payer_archetype`, `flags`,
    `provenance` and `spotlight`, so a proposer cannot read the simulation's
    answer key even by accident.
    """

    name: str
    arm: Arm

    def propose(self, snapshot: dict[str, Any], tick: Tick) -> Proposal:
        """Choose an intervention from the closed enum."""
        ...


class PolicyGate(Protocol):
    """The deterministic engine that can veto or modify a proposal. Phase 2.

    Phase 1 runs with this absent, which is why the Phase 1 gate says "no LLM
    and no policy engine": the tick loop must be provably correct on its own
    before anything is layered on it.
    """

    def adjudicate(self, record: Invoice, proposal: Proposal, tick: Tick) -> PolicyVerdict:
        """Approve, modify or veto."""
        ...


@dataclass
class RunResult:
    """Everything one arm's run produced. The metrics read this in Phase 2."""

    run_id: str
    arm: Arm
    seed: int
    ledger: Ledger
    log: AuditLog
    horizon: int
    contacts: int = 0
    api_units: int = 0
    vetoed: int = 0
    decisions: int = 0
    written_off: int = 0

    @property
    def records(self) -> list[Invoice]:
        """The final position of every record."""
        return self.ledger.records

    @property
    def recovered_paise(self) -> int:
        """Money collected across the batch. Integer paise."""
        return sum(r.recovered_paise for r in self.ledger.records)

    @property
    def billed_paise(self) -> int:
        """Total value of the book at intake."""
        return sum(r.amount_paise for r in self.ledger.records)


@dataclass(order=True)
class _Pending:
    """A contact awaiting its response. Ordered so resolution is deterministic."""

    due_tick: Tick
    record_id: str
    intervention: Intervention = field(compare=False)
    contacts_at_send: int = field(compare=False, default=0)


class AlwaysWait:
    """The do-nothing control. Never contacts anybody.

    Not a straw man and not a joke: it is the floor the other arms have to beat,
    and on a book where most payers settle on their own cycle that floor is
    higher than anyone expects. Reporting the agent's recovery without it would
    flatter every arm equally.
    """

    name = "always-wait"
    arm = Arm.BASELINE

    def propose(self, snapshot: dict[str, Any], tick: Tick) -> Proposal:
        """WAIT, unconditionally."""
        return Proposal(intervention=Intervention.WAIT)


def run_batch(
    records: list[Invoice],
    proposer: Proposer,
    *,
    seed: int,
    run_id: str,
    horizon: int = DEFAULT_HORIZON,
    policy: PolicyGate | None = None,
    executor: Executor | None = None,
) -> RunResult:
    """Run one arm over one batch. The only tick loop in the project.

    The caller's `records` are NOT mutated: the run works on a deep copy, and
    the final position lives on `result.ledger.records`.

    An earlier version mutated in place and pushed the copying onto callers.
    That is a footgun, and it fired immediately -- `write_run(result, batch)`
    silently stored the CLOSING position as `batch.json`, because `batch.records`
    was the very list the run had just walked over. The opening batch then
    equalled the final one, and replaying from it double-applied every row. One
    `model_copy` per record costs nothing next to a 112-tick run and removes the
    entire class of error, including the worse version of it: running two arms
    off one batch and comparing them to each other.
    """
    ledger = Ledger([record.model_copy(deep=True) for record in records])
    adjudicator = Adjudicator(seed)
    log = AuditLog(run_id, proposer.arm)
    clock = VirtualClock(tick=0, horizon=horizon)
    runner_executor = executor or SimulatedExecutor(run_id)
    result = RunResult(
        run_id=run_id,
        arm=proposer.arm,
        seed=seed,
        ledger=ledger,
        log=log,
        horizon=horizon,
    )

    # Intake. One row per record, carrying the opening snapshot, so that a
    # reader of the log alone can see what the run started from.
    opening_date = virtual_date(0)
    for record in ledger.records:
        log.append(
            kind=RowKind.INTAKE,
            tick=0,
            record_id=record.invoice_id,
            input_snapshot=record.to_snapshot(opening_date, 0),
        )

    pending: list[_Pending] = []

    while not clock.exhausted:
        tick = clock.tick
        as_of = virtual_date(tick)

        pending = _land_responses(ledger, adjudicator, log, result, pending, tick)
        _resolve_promises(ledger, adjudicator, log, tick)
        _draw_spontaneous(ledger, adjudicator, log, tick)
        _take_decisions(
            ledger, proposer, policy, runner_executor, log, result, pending, tick, as_of
        )

        clock.advance()

    result.written_off = ledger.finalise(horizon)
    return result


# ---------------------------------------------------------------------------
# one tick, in four steps
# ---------------------------------------------------------------------------


def _land_responses(
    ledger: Ledger,
    adjudicator: Adjudicator,
    log: AuditLog,
    result: RunResult,
    pending: list[_Pending],
    tick: Tick,
) -> list[_Pending]:
    """Step 1. Resolve contacts whose response is due, and return what is left.

    Sorted before resolution so that two runs of the same arm land responses in
    the same order regardless of how the list was built.
    """
    due = sorted(item for item in pending if item.due_tick <= tick)
    remaining = [item for item in pending if item.due_tick > tick]

    for item in due:
        record = ledger.get(item.record_id)
        if is_terminal(record.state):
            continue
        outcome = adjudicator.resolve_response(
            record,
            tick,
            item.intervention,
            recent_contacts=item.contacts_at_send,
        )
        _apply_outcome(ledger, log, record, outcome, tick)

    return remaining


def _resolve_promises(ledger: Ledger, adjudicator: Adjudicator, log: AuditLog, tick: Tick) -> None:
    """Step 2. Promises that fall due are kept or broken, before anyone decides."""
    for record in ledger.active():
        outcome = adjudicator.resolve_promise(record, tick)
        if outcome is not None:
            _apply_outcome(ledger, log, record, outcome, tick)


def _draw_spontaneous(ledger: Ledger, adjudicator: Adjudicator, log: AuditLog, tick: Tick) -> None:
    """Step 3. The world moves whether or not anyone chased it.

    Runs for EVERY non-terminal record in both arms. See the adjudicator's
    module docstring on why this is a separate hash channel: without it, a
    record nobody contacted could never pay, and WAIT would be a forfeit.
    """
    for record in ledger.active():
        outcome = adjudicator.resolve_spontaneous(record, tick)
        if outcome is not None:
            _apply_outcome(ledger, log, record, outcome, tick)


def _take_decisions(
    ledger: Ledger,
    proposer: Proposer,
    policy: PolicyGate | None,
    executor: Executor,
    log: AuditLog,
    result: RunResult,
    pending: list[_Pending],
    tick: Tick,
    as_of: Any,
) -> None:
    """Step 4. Review what is due, propose, adjudicate, act, log.

    The decision-cadence gate is `due_for_review`, and it is what keeps the
    Phase 2 reasoner at a few hundred calls per run instead of one per record
    per tick. A record that settled earlier in this same tick is already
    terminal and is not reviewed.
    """
    for record in ledger.due_for_review(tick):
        snapshot = record.to_snapshot(as_of, tick)
        proposal = proposer.propose(snapshot, tick)

        verdict: PolicyVerdict | None = None
        final: Intervention | None = proposal.intervention
        if policy is not None:
            verdict = policy.adjudicate(record, proposal, tick)
            final = verdict.final if verdict.verdict is not VerdictKind.VETOED else None

        result.decisions += 1

        if final is None:
            # Vetoed. The review slot is spent, no contact is made, no budget
            # moves, and the state does not change. Logged in full, because the
            # veto is the most interesting row in the file.
            action = ledger.record_action(record, proposal.intervention, tick, executed=False)
            result.vetoed += 1
            log.append(
                kind=RowKind.DECISION,
                tick=tick,
                record_id=record.invoice_id,
                input_snapshot=snapshot,
                llm_proposal=proposal.llm_proposal,
                policy_verdict=verdict,
                policy_rule=verdict.rule_id if verdict else None,
                action=action,
            )
            continue

        details = spec(final)
        contacts_at_send = ledger.payer_contacts_since(
            record.payer_id, max(0, tick - CONTACT_WINDOW_TICKS)
        )
        external_ref = executor.perform(record, final, tick) if details.is_contact else None

        action = ledger.record_action(record, final, tick, executed=True)
        action = action.model_copy(update={"executor": executor.kind, "external_ref": external_ref})
        result.contacts += action.contact_units
        result.api_units += action.api_units

        log.append(
            kind=RowKind.DECISION,
            tick=tick,
            record_id=record.invoice_id,
            input_snapshot=snapshot,
            llm_proposal=proposal.llm_proposal,
            policy_verdict=verdict,
            policy_rule=verdict.rule_id if verdict else None,
            action=action,
        )

        if details.is_contact:
            pending.append(
                _Pending(
                    due_tick=tick + RESPONSE_DELAY_TICKS,
                    record_id=record.invoice_id,
                    intervention=final,
                    contacts_at_send=contacts_at_send,
                )
            )


def _apply_outcome(
    ledger: Ledger,
    log: AuditLog,
    record: Invoice,
    outcome: Any,
    tick: Tick,
) -> None:
    """Apply one outcome to the ledger and append the row that records it.

    PROMISED is the one case that does not go through `record_outcome`: the
    payer's PHRASE is what was said, and the clock -- not the model, not the
    adjudicator -- turns it into a due tick. Invariant 3, in the one place a
    date could otherwise sneak in from outside.
    """
    if outcome.kind is OutcomeKind.PROMISED:
        phrase = outcome.detail
        ledger.set_promise(record, phrase, resolve_promise_phrase(phrase, tick), tick)
    else:
        ledger.record_outcome(record, outcome, tick)

    log.append(
        kind=RowKind.OUTCOME,
        tick=tick,
        record_id=record.invoice_id,
        outcome=outcome,
    )


def write_run(result: RunResult, batch: Any, out_dir: Path) -> Path:
    """Persist a run so `recoup replay` has something real to work on.

    Four files, and the split between them is the point:

        batch.json    the OPENING position, byte-identical to the generator's
        audit.jsonl   the append-only log
        final.json    the CLOSING position the replay must reproduce
        summary.json  the headline numbers, for a human

    `final.json` is what makes replay a test rather than an exercise. Without a
    stored closing position, replaying a log can only be checked against
    itself, which proves the reader and the writer agree and nothing more.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "batch.json").write_text(
        canonical_json(batch.model_dump(mode="json")), encoding="utf-8", newline=""
    )
    result.log.write(out_dir / "audit.jsonl")
    (out_dir / "final.json").write_text(
        canonical_json([r.model_dump(mode="json") for r in result.ledger.records]),
        encoding="utf-8",
        newline="",
    )
    (out_dir / "summary.json").write_text(
        canonical_json(summarise(result)), encoding="utf-8", newline=""
    )
    return out_dir


def summarise(result: RunResult) -> dict[str, Any]:
    """A compact, printable summary. Not the Phase 2 metric table.

    Deliberately thin: the real comparison lives in `metrics.compute`, which
    also reads ground-truth flags this summary has no business touching.
    """
    states: dict[str, int] = {}
    for record in result.ledger.records:
        states[str(record.state)] = states.get(str(record.state), 0) + 1
    paid = sum(1 for r in result.ledger.records if r.state is RecordState.PAID)
    return {
        "run_id": result.run_id,
        "arm": str(result.arm),
        "proposer_records": len(result.ledger.records),
        "decisions": result.decisions,
        "contacts": result.contacts,
        "api_units": result.api_units,
        "vetoed": result.vetoed,
        "paid_records": paid,
        "written_off": result.written_off,
        "recovered_paise": result.recovered_paise,
        "billed_paise": result.billed_paise,
        "audit_rows": len(result.log),
        "states": dict(sorted(states.items())),
    }
