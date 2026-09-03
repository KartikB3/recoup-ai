"""Executor interface. Simulated in Phase 2, live in Phase 4.

The executor owns the OUTSIDE-WORLD half of an action and nothing else. It
does not cost the action, does not move state, and does not touch the contact
ledger -- `ledger.Ledger` does all of that, for both executors alike, so that a
live run and a simulated run are book-kept by identical code and remain
comparable.

What an executor returns is therefore small: an `ExecutionResult` carrying an
external reference and the kind of execution that produced it. For a simulated
run that is a synthetic id; for a live run it is the Razorpay payment-link id.
The runner stamps both onto the `ActionRecord` and the audit row carries them,
which is what makes a live row traceable back to a real object in the Razorpay
dashboard -- the only reason `ExecutorKind.LIVE` exists.

Why the KIND travels with the result and not with the executor
--------------------------------------------------------------
It used to be a class attribute the runner read once per action, which was
correct only while every executor was uniform. The live executor is not, and
cannot be:

  * Only `PAYMENT_LINK` has a live counterpart at all. `api_units` is 1 for a
    link and 0 for `SOFT_REMINDER` and `PHONE_FOLLOWUP` -- Recoup sends no
    email, no SMS and places no calls, in any mode. A class-level `LIVE` stamp
    would mark every reminder row in a live run as real when nothing left the
    process.
  * The link budget is scarce and allocated (ISS-001), so even among links,
    some rows are real and some are not.

The Phase 4 gate says a judge must be able to see exactly which rows were real.
That sentence is only true if `LIVE` means "a Razorpay object exists for this
row", which is a property of the action, not of the executor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from recoup.domain.enums import ExecutorKind, Intervention
from recoup.domain.models import Invoice, Tick


@dataclass(frozen=True)
class ExecutionResult:
    """The outside-world half of one action, and how much of it was real."""

    kind: ExecutorKind
    """SIMULATED unless a real external object was created for THIS action."""

    external_ref: str | None = None
    """The id of that object. `plink_...` for a live Razorpay payment link."""

    detail: str = ""
    """Why a live executor did not go live. Empty when nothing needs saying."""


#: Nothing left the process. The common case, and the safe default.
NOT_EXECUTED = ExecutionResult(kind=ExecutorKind.SIMULATED)


@runtime_checkable
class Executor(Protocol):
    """Performs the real-world part of an approved action.

    Called only for actions the policy engine approved and only for
    interventions that reach the payer. A veto never gets this far, which is
    the structural reason a vetoed proposal cannot cost money.
    """

    def perform(self, record: Invoice, intervention: Intervention, tick: Tick) -> ExecutionResult:
        """Do the outside-world work. Return what was actually done.

        Must not mutate `record`. Raising is permitted and is the honest
        response to an API failure: the runner logs the row and does not
        pretend the contact was made.
        """
        ...
