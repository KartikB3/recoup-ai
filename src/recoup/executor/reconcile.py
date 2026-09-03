"""A real payment, reconciled into the ledger as an ordinary outcome. Phase 4.

The last quarter of the loop. A payment link the agent created was paid on
Razorpay's mock page, the webhook arrives, and the money has to land where
every other rupee in this system lands: in the ledger, through
`Ledger.record_outcome`, recorded as a new append-only audit row. Invariant 8
says the ledger is the system of record, not Razorpay -- so a Razorpay event is
an input to the ledger, never a substitute for it.

What makes this safe to run against a committed artifact
--------------------------------------------------------
Three things, in order, before anything is written:

1. **Protected runs are refused.** `runs/seed42/` and `runs/seed42-tiered/` are
   the canonical comparison and a webhook may not touch them, whatever it
   carries.
2. **The log is replayed and checked against the closing position it claims.**
   If the stored `final.json` cannot be reproduced from `batch.json` plus the
   rows, something is already wrong and this is not the moment to append to it.
   The replay is also what produces the ledger the payment is applied to, so
   the mutation happens to a position derived from the log rather than to a
   file trusted on sight.
3. **Terminal records are refused.** `Ledger.record_outcome` adds money BEFORE
   transitioning, and `state_after_outcome` returns early on a terminal state.
   A payment onto a WRITTEN_OFF record would therefore increase recovered money
   and leave the record written off -- replay would stay green while the metric
   table counted the same rupees as both recovered and lost. Refused explicitly
   and reported, never silently no-opped.

Idempotency comes out of the log
--------------------------------
Razorpay retries webhooks, and a demo gets refreshed. The Razorpay payment id
is written into `OutcomeRecord.detail`, so "have we already applied this
payment?" is answered by reading the log -- no side table, no extra field on
`ActionRecord` (`extra="forbid"`, and `audit.replay` compares a fixed field
list, so a new field is a schema change that would break byte-comparison with
every committed run).

On time
-------
There is no wall clock here. The run's virtual horizon has passed, so the
outcome is recorded at the last tick the log contains: the close of the run.
The real-world instant lives in `reconciliation.jsonl` beside it, where it is
metadata about an external event rather than a virtual date the ledger reasons
with (invariant 2).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from recoup.audit.log import AuditLog, read_log
from recoup.audit.replay import compare
from recoup.audit.replay import replay as replay_rows
from recoup.domain.enums import OutcomeKind, RowKind
from recoup.domain.models import Invoice, OutcomeRecord, Paise, canonical_json
from recoup.executor.session import read_session, write_session
from recoup.generator.generate import load_batch
from recoup.ledger.ledger import is_terminal

#: Run directories a webhook may never write to, whatever it carries. These are
#: the committed comparison the whole submission rests on.
PROTECTED_RUN_IDS = frozenset({"seed42", "seed42-tiered"})

#: The external events this arm has accepted. Beside the audit log, not in it.
RECONCILIATION_FILENAME = "reconciliation.jsonl"


class ReconcileRefused(RuntimeError):
    """The payment was understood and deliberately not applied."""


@dataclass(frozen=True)
class Reconciled:
    """What one reconciliation did, for the caller to report."""

    invoice_id: str
    run_id: str
    arm: str
    payment_id: str
    payment_link_id: str
    amount_paise: Paise
    state_before: str
    state_after: str
    row_id: int
    already_applied: bool = False

    def as_dict(self) -> dict[str, Any]:
        """A JSON-safe view, for the receiver's response and its event log."""
        return {
            "invoice_id": self.invoice_id,
            "run_id": self.run_id,
            "arm": self.arm,
            "payment_id": self.payment_id,
            "payment_link_id": self.payment_link_id,
            "amount_paise": self.amount_paise,
            "state_before": self.state_before,
            "state_after": self.state_after,
            "audit_row_id": self.row_id,
            "already_applied": self.already_applied,
        }


def _payment_already_applied(rows: list[Any], payment_id: str) -> int | None:
    """The row id that already recorded this payment, or None."""
    for row in rows:
        outcome = row.outcome
        if outcome is not None and payment_id and payment_id in outcome.detail:
            return int(row.row_id)
    return None


def reconcile_payment(
    arm_dir: Path,
    *,
    invoice_id: str,
    payment_id: str,
    payment_link_id: str,
    amount_paise: Paise,
    received_at: str = "",
) -> Reconciled:
    """Apply one real payment to one arm's ledger. The only writer in Phase 4.

    Raises `ReconcileRefused` for anything it will not do, so the caller can
    answer a webhook honestly instead of returning 200 for a payment nothing
    happened to.
    """
    log_path = arm_dir / "audit.jsonl"
    batch_path = arm_dir / "batch.json"
    final_path = arm_dir / "final.json"
    for required in (log_path, batch_path, final_path):
        if not required.exists():
            raise ReconcileRefused(f"{arm_dir} is not a complete run directory: {required} missing")

    rows = read_log(log_path)
    if not rows:
        raise ReconcileRefused(f"{log_path} is empty")
    run_id = rows[0].run_id
    if run_id in PROTECTED_RUN_IDS:
        raise ReconcileRefused(
            f"{run_id} is a protected canonical run and is never written to by a webhook"
        )

    applied_at = _payment_already_applied(rows, payment_id)
    if applied_at is not None:
        record = _stored_record(final_path, invoice_id)
        return Reconciled(
            invoice_id=invoice_id,
            run_id=run_id,
            arm=str(rows[0].arm),
            payment_id=payment_id,
            payment_link_id=payment_link_id,
            amount_paise=amount_paise,
            state_before=str(record.state),
            state_after=str(record.state),
            row_id=applied_at,
            already_applied=True,
        )

    # Rebuild the closing position from the log, and check it against the one
    # the run stored. Mutating a `final.json` that the log cannot reproduce
    # would write a state nothing can audit.
    replayed = replay_rows(load_batch(batch_path).records, rows)
    stored = [
        Invoice.model_validate(item) for item in json.loads(final_path.read_text(encoding="utf-8"))
    ]
    differences = compare(stored, replayed.ledger.records)
    if differences:
        raise ReconcileRefused(
            f"{arm_dir} does not replay to its own final.json ({len(differences)} divergences); "
            "refusing to append to a run that is already inconsistent"
        )

    ledger = replayed.ledger
    try:
        record = ledger.get(invoice_id)
    except KeyError as exc:
        raise ReconcileRefused(f"{invoice_id} is not in {arm_dir}") from exc

    state_before = str(record.state)
    if is_terminal(record.state):
        raise ReconcileRefused(
            f"{invoice_id} is already {state_before}; applying a payment to a terminal record "
            "would add recovered money without moving the state, and the same rupees would be "
            "counted as both recovered and lost"
        )

    outstanding = record.outstanding_paise
    if amount_paise <= 0:
        raise ReconcileRefused(f"a payment of {amount_paise} paise is not a payment")
    kind = OutcomeKind.PAID_FULL if amount_paise >= outstanding else OutcomeKind.PAID_PARTIAL
    outcome = OutcomeRecord(
        kind=kind,
        amount_paise=amount_paise,
        # The payment id is the idempotency key and it lives here so that the
        # log alone answers "did we already apply this?".
        detail=f"razorpay payment {payment_id} settling link {payment_link_id}",
    )

    tick = max(row.tick for row in rows)
    ledger.record_outcome(record, outcome, tick)

    log = AuditLog.resume(rows)
    row = log.append(
        kind=RowKind.OUTCOME,
        tick=tick,
        record_id=invoice_id,
        outcome=outcome,
    )
    log.write(log_path)
    final_path.write_text(
        canonical_json([r.model_dump(mode="json") for r in ledger.records]),
        encoding="utf-8",
        newline="",
    )
    _refresh_summary(arm_dir, ledger.records, len(log))
    _mark_link_paid(arm_dir, payment_link_id)
    _append_event(
        arm_dir,
        {
            "payment_id": payment_id,
            "payment_link_id": payment_link_id,
            "invoice_id": invoice_id,
            "amount_paise": amount_paise,
            "audit_row_id": row.row_id,
            "received_at": received_at,
            "state_before": state_before,
            "state_after": str(record.state),
        },
    )

    return Reconciled(
        invoice_id=invoice_id,
        run_id=run_id,
        arm=str(rows[0].arm),
        payment_id=payment_id,
        payment_link_id=payment_link_id,
        amount_paise=amount_paise,
        state_before=state_before,
        state_after=str(record.state),
        row_id=row.row_id,
    )


def _stored_record(final_path: Path, invoice_id: str) -> Invoice:
    """One record from a stored closing position."""
    for item in json.loads(final_path.read_text(encoding="utf-8")):
        if item.get("invoice_id") == invoice_id:
            return Invoice.model_validate(item)
    raise ReconcileRefused(f"{invoice_id} is not in {final_path}")


def _refresh_summary(arm_dir: Path, records: list[Invoice], audit_rows: int) -> None:
    """Update the fields a payment changed, and leave the rest alone.

    Deliberately a merge rather than a regeneration. `summary.json` also
    carries the batch-insight block and the run's decision counters, none of
    which a later payment touches, and rebuilding it from a replay would drop
    what it cannot reconstruct.
    """
    path = arm_dir / "summary.json"
    if not path.exists():
        return
    summary = json.loads(path.read_text(encoding="utf-8"))
    states: dict[str, int] = {}
    for record in records:
        states[str(record.state)] = states.get(str(record.state), 0) + 1
    summary["states"] = dict(sorted(states.items()))
    summary["paid_records"] = states.get("PAID", 0)
    summary["recovered_paise"] = sum(r.recovered_paise for r in records)
    summary["audit_rows"] = audit_rows
    path.write_text(canonical_json(summary), encoding="utf-8", newline="")


def _mark_link_paid(arm_dir: Path, payment_link_id: str) -> None:
    """Record the settlement on the live-link index, for the dashboard."""
    session = read_session(arm_dir)
    if session is None:
        return
    link = session.find(payment_link_id)
    if link is None:
        return
    link.status = "paid"
    write_session(session, arm_dir)


def _append_event(arm_dir: Path, event: dict[str, Any]) -> None:
    """Log the external event beside the run. Append-only, like everything else."""
    path = arm_dir / RECONCILIATION_FILENAME
    with path.open("a", encoding="utf-8", newline="") as handle:
        handle.write(canonical_json(event))
        handle.write("\n")
