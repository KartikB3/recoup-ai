"""Simulated executor. The default. Phase 2.

Everything happens in the ledger. Used for the full batch.

There is deliberately almost nothing here. Every consequence of an action --
the cost, the state move, the contact ledger entry -- lives in `Ledger`, and
what the payer does about it lives in `ledger.adjudicator`. This class exists
to occupy the same seam a live Razorpay call will occupy in Phase 4, so that
swapping one for the other changes one constructor argument and no logic.

The reference it returns is derived, not random: the same action in the same
run always produces the same id, so a simulated run stays byte-reproducible.
"""

from __future__ import annotations

from recoup.domain.enums import ExecutorKind, Intervention
from recoup.domain.interventions import spec
from recoup.domain.models import Invoice, Tick
from recoup.executor.base import NOT_EXECUTED, ExecutionResult


class SimulatedExecutor:
    """Performs nothing outside the process. Satisfies `Executor`."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id

    def perform(self, record: Invoice, intervention: Intervention, tick: Tick) -> ExecutionResult:
        """Mint a deterministic reference for actions that produce an artifact.

        Only the payment link produces something a merchant could later look
        up, so only it gets a reference. A reminder that returns an id would
        imply an object exists somewhere, and nothing in a simulated run does.

        The kind is always SIMULATED, which is what the whole four-arm
        comparison rests on: none of it touched an external system.
        """
        if not spec(intervention).api_units:
            return NOT_EXECUTED
        return ExecutionResult(
            kind=ExecutorKind.SIMULATED,
            external_ref=f"sim_link_{self.run_id}_{record.invoice_id}_{tick}",
        )
