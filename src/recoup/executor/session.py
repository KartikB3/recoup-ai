"""The durable record of which real Razorpay objects a run created. Phase 4.

A live run makes objects that outlive the process. The payer pays them minutes
or hours later, through a browser, and the webhook that reports it arrives when
the tick loop is long finished. Something has to survive in between, and it has
to be enough to answer one question: *this `plink_...` just got paid -- which
invoice, in which run, in which arm, for how much?*

That is this file. One JSON document per arm, written beside the audit log it
belongs to, listing every live link with the ledger coordinates needed to
reconcile it. It is deliberately not the audit log: the log is append-only and
hash-chained and is the record of what the agent DECIDED, while this is an
index of external objects, rewritten as the run adds to it.

Both halves are needed. The audit row proves the agent made the decision; this
file is how a payment finds its way back to that row.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from recoup.domain.enums import Arm
from recoup.domain.models import Paise, Tick, canonical_json

#: Written beside `audit.jsonl` in the arm directory.
SESSION_FILENAME = "live-links.json"


class LiveLink(BaseModel):
    """One real Razorpay payment link, and where it came from."""

    model_config = ConfigDict(extra="forbid")

    payment_link_id: str
    """The Razorpay id. `plink_...`, and the key a webhook arrives carrying."""

    reference_id: str
    """Our id for it. Unique per account, so it is also the create-idempotency key."""

    short_url: str
    invoice_id: str
    run_id: str
    arm: Arm
    tick: Tick
    """The virtual tick the agent decided on. Not a wall-clock time; there isn't one."""

    amount_paise: Paise
    status: str
    """Razorpay's status at creation. Almost always `created`."""


class LiveSession(BaseModel):
    """Every live link one arm of one run created."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    arm: Arm
    key_id: str
    """Which test-mode account owns these objects. Never the secret."""

    links: list[LiveLink] = []

    def find(self, payment_link_id: str) -> LiveLink | None:
        """The link with this Razorpay id, or None."""
        return next((link for link in self.links if link.payment_link_id == payment_link_id), None)


def write_session(session: LiveSession, arm_dir: Path) -> Path:
    """Persist the session beside the arm's audit log."""
    arm_dir.mkdir(parents=True, exist_ok=True)
    path = arm_dir / SESSION_FILENAME
    path.write_text(
        canonical_json(session.model_dump(mode="json")) + "\n", encoding="utf-8", newline=""
    )
    return path


def read_session(arm_dir: Path) -> LiveSession | None:
    """Read one arm's session, or None if that arm made no live links."""
    path = arm_dir / SESSION_FILENAME
    if not path.exists():
        return None
    return LiveSession.model_validate(json.loads(path.read_text(encoding="utf-8")))


def find_link(runs_root: Path, payment_link_id: str) -> tuple[Path, LiveSession, LiveLink] | None:
    """Locate a payment link across every run on disk.

    The webhook receives a `plink_...` and nothing else -- Razorpay has no idea
    which run made it -- so the lookup is a scan. It is cheap (a handful of
    small files) and it means the receiver needs no configuration beyond the
    runs directory, which matters when the thing is started in a hurry behind a
    tunnel while a screen recording is running.
    """
    for path in sorted(runs_root.glob(f"*/*/{SESSION_FILENAME}")):
        session = LiveSession.model_validate(json.loads(path.read_text(encoding="utf-8")))
        link = session.find(payment_link_id)
        if link is not None:
            return path.parent, session, link
    return None
