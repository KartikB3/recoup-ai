"""Executor interface. Simulated in Phase 2, live in Phase 4.

The executor owns the OUTSIDE-WORLD half of an action and nothing else. It
does not cost the action, does not move state, and does not touch the contact
ledger -- `ledger.Ledger` does all of that, for both executors alike, so that a
live run and a simulated run are book-kept by identical code and remain
comparable.

What an executor returns is therefore small: an external reference, or None.
For a simulated run that is a synthetic id; for a live run it is the Razorpay
payment-link id. The runner stamps it onto the `ActionRecord` and the audit row
carries it, which is what makes a live row traceable back to a real object in
the Razorpay dashboard -- the only reason `ExecutorKind.LIVE` exists.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from recoup.domain.enums import ExecutorKind, Intervention
from recoup.domain.models import Invoice, Tick


@runtime_checkable
class Executor(Protocol):
    """Performs the real-world part of an approved action.

    Called only for actions the policy engine approved and only for
    interventions that reach the payer. A veto never gets this far, which is
    the structural reason a vetoed proposal cannot cost money.
    """

    kind: ExecutorKind

    def perform(self, record: Invoice, intervention: Intervention, tick: Tick) -> str | None:
        """Do the outside-world work. Return an external reference, or None.

        Must not mutate `record`. Raising is permitted and is the honest
        response to an API failure: the runner logs the row and does not
        pretend the contact was made.
        """
        ...
