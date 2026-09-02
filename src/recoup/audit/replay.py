"""Log replay. Phase 1.

ACCEPTANCE TEST: reconstruct(invoice_id, log) returns the final state of that
invoice from the log alone, with no other state, and it must equal the ledger
state. If the two ever diverge, the log is wrong. Runs over all 126 records in
CI.

Why this replays through the Ledger and not through the pure functions
----------------------------------------------------------------------
The obvious implementation re-derives `RecordState` with `state_after_action`
and `state_after_outcome` and compares that. It would pass, and it would prove
much less than it appears to.

`RecordState` is not the only thing a run mutates. `recovered_paise`,
`contact_ledger.attempts`, `payment_links_sent`, `next_review_tick`,
`promise_phrase` and `promise_due_tick` all move too -- and those, not the
state, are what the Phase 2 metric table reads. A replay that compares state
alone goes green while recovered money silently diverges, which is the failure
mode most likely to embarrass this project in front of a judge.

So replay builds a **fresh `Ledger` from the batch file** and re-applies every
row through the very same `record_action`, `record_outcome` and `set_promise`
methods the live run used. No transition logic is duplicated here; if it were,
the copy could agree with itself while both disagreed with the ledger. Then
`compare` diffs the whole reconstructed record set against the live one, field
by field.

The standard this holds the log to
----------------------------------
**Every field the metrics read must be reconstructible from the audit rows
alone.** Two consequences already visible in the contracts:

  * `action` carries the whole `ActionRecord`, including `executed`. A vetoed
    proposal consumes a review slot but makes no contact and spends no budget,
    so dropping that flag would corrupt every contact count.
  * a PROMISED outcome carries the payer's words in `outcome.detail`. Replay
    feeds that phrase back through `clock.resolve_promise_phrase` at the row's
    own tick to recover the due tick -- the clock is deterministic and pure, so
    the tick does not need storing, but the PHRASE does. This is invariant 3
    in miniature: the log keeps the words, the clock computes the date.

Nothing here touches a wall clock or an RNG. Replay is a pure function of
(batch, rows).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from recoup.audit.log import verify_chain
from recoup.domain.enums import OutcomeKind, RecordState, RowKind
from recoup.domain.models import AuditRow, Invoice
from recoup.ledger.clock import resolve_promise_phrase
from recoup.ledger.ledger import Ledger

#: Fields compared record-by-record when a replay is checked against a live
#: run. This list is the operational definition of "the log is sufficient":
#: adding a mutable field to `Invoice` without adding it here is how a future
#: divergence gets missed.
COMPARED_FIELDS: tuple[str, ...] = (
    "state",
    "recovered_paise",
    "next_review_tick",
    "promise_phrase",
    "promise_due_tick",
    "resolved_tick",
)


class ReplayMismatch(RuntimeError):
    """The log does not reproduce the run. Carries every differing field."""

    def __init__(self, differences: list[Difference]) -> None:
        head = "; ".join(str(d) for d in differences[:5])
        suffix = f" (and {len(differences) - 5} more)" if len(differences) > 5 else ""
        super().__init__(f"replay diverged from the ledger: {head}{suffix}")
        self.differences = differences


@dataclass(frozen=True)
class Difference:
    """One field of one record that replay did not reproduce."""

    record_id: str
    field_name: str
    live: Any
    replayed: Any

    def __str__(self) -> str:
        return f"{self.record_id}.{self.field_name}: live={self.live!r} replay={self.replayed!r}"


@dataclass
class ReplayResult:
    """The reconstructed ledger and what it took to get there."""

    ledger: Ledger
    rows_applied: int
    contacts: int = 0
    api_units: int = 0
    vetoed: int = 0
    differences: list[Difference] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when the reconstruction matched the run it was compared against."""
        return not self.differences


def replay(records: list[Invoice], rows: list[AuditRow], *, verify: bool = True) -> ReplayResult:
    """Rebuild a run from the batch and the log, and nothing else.

    `records` must be freshly loaded from the batch file -- the pristine
    starting position, not the objects the run mutated. Passing the live ones
    would make the comparison vacuous, so callers load the batch again.
    """
    if verify:
        verify_chain(rows)

    ledger = Ledger(records)
    result = ReplayResult(ledger=ledger, rows_applied=0)

    for row in rows:
        record = ledger.get(row.record_id)
        match row.kind:
            case RowKind.INTAKE:
                # The opening snapshot. Nothing to apply: the batch file already
                # is the opening position, and that is the point of comparing.
                pass
            case RowKind.DECISION:
                _apply_decision(ledger, record, row, result)
            case RowKind.OUTCOME:
                _apply_outcome(ledger, record, row, result)
        result.rows_applied += 1

    return result


def _apply_decision(ledger: Ledger, record: Invoice, row: AuditRow, result: ReplayResult) -> None:
    """Re-apply one decision row through the ledger's own writer."""
    if row.action is None:
        # A row that reached a verdict but produced no action at all -- the
        # policy engine returning nothing to do. It still moved no state.
        return
    ledger.record_action(record, row.action.intervention, row.tick, executed=row.action.executed)
    if row.action.executed:
        result.contacts += row.action.contact_units
        result.api_units += row.action.api_units
    else:
        result.vetoed += 1


def _apply_outcome(ledger: Ledger, record: Invoice, row: AuditRow, result: ReplayResult) -> None:
    """Re-apply one outcome row, including the promise the phrase implies."""
    if row.outcome is None:
        return
    if row.outcome.kind is OutcomeKind.PROMISED:
        # The phrase is in the log; the tick is recomputed. See the module
        # docstring on why that split is deliberate rather than an economy.
        phrase = row.outcome.detail
        ledger.set_promise(record, phrase, resolve_promise_phrase(phrase, row.tick), row.tick)
        return
    ledger.record_outcome(record, row.outcome, row.tick)


def compare(live: list[Invoice], replayed: list[Invoice]) -> list[Difference]:
    """Diff two record sets field by field over `COMPARED_FIELDS`.

    Also compares the contact ledger, which is not a scalar: the count, the
    payment links, and the tick of every attempt. Two runs that agree on state
    and money but disagree on how many messages were sent are not the same run,
    and the contact budget is half the story this project is telling.
    """
    differences: list[Difference] = []
    by_id = {record.invoice_id: record for record in replayed}

    for record in live:
        other = by_id.get(record.invoice_id)
        if other is None:
            differences.append(Difference(record.invoice_id, "<record>", "present", "missing"))
            continue
        for name in COMPARED_FIELDS:
            live_value = getattr(record, name)
            replay_value = getattr(other, name)
            if live_value != replay_value:
                differences.append(Difference(record.invoice_id, name, live_value, replay_value))

        live_contacts = [
            (a.tick, a.intervention, a.channel) for a in record.contact_ledger.attempts
        ]
        replay_contacts = [
            (a.tick, a.intervention, a.channel) for a in other.contact_ledger.attempts
        ]
        if live_contacts != replay_contacts:
            differences.append(
                Difference(
                    record.invoice_id, "contact_ledger.attempts", live_contacts, replay_contacts
                )
            )
        if record.contact_ledger.payment_links_sent != other.contact_ledger.payment_links_sent:
            differences.append(
                Difference(
                    record.invoice_id,
                    "contact_ledger.payment_links_sent",
                    record.contact_ledger.payment_links_sent,
                    other.contact_ledger.payment_links_sent,
                )
            )

    return differences


def reconstruct(invoice_id: str, records: list[Invoice], rows: list[AuditRow]) -> RecordState:
    """The final state of ONE invoice, from the log alone.

    The signature the acceptance test in the module docstring names. It is a
    thin wrapper over `replay`, kept because a single-record answer is what a
    reader wants when a comparison has already failed and they are working out
    which record broke.
    """
    mine = [row for row in rows if row.record_id == invoice_id]
    result = replay(records, mine, verify=False)
    return result.ledger.get(invoice_id).state
