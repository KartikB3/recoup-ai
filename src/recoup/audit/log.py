"""Append-only audit log, JSONL. Phase 1.

One row per decision, never updated. Outcomes arrive as new rows.

Fields: tick, record_id, input_snapshot, llm_proposal, policy_verdict,
policy_rule, action, outcome, plus run_id, arm, row_id, prev_row_hash.

INVARIANT 5, enforced mechanically
----------------------------------
`AuditLog` exposes `append` and nothing else that writes. There is no `update`,
no `amend`, no row lookup that hands back something mutable. When a record's
outcome arrives three ticks after the decision that caused it, that is a NEW
row referring to the same `record_id` -- the decision row is left exactly as it
was written.

The hash chain
--------------
Each row stores the hash of the row before it. Row 0 stores `GENESIS_HASH`.
Verification walks the file recomputing hashes, so editing any row in place
breaks the link at the following row and `verify_chain` names the row that
broke. This is a tamper-evidence property, not a security one: anyone able to
rewrite the file can rewrite the chain with it. It exists so that an accidental
edit -- a hand-fixed number, a partial write, two runs interleaved into one
file -- is caught loudly rather than quietly believed.

What the log has to be sufficient for
-------------------------------------
`audit.replay` rebuilds the entire run from these rows and the batch file, with
no other input. That is a harder requirement than "the log is readable", and it
is the reason `action` carries the full `ActionRecord` including `executed`
(a vetoed proposal spends a review slot but no contact) and the reason a
PROMISED outcome carries the payer's phrase in `detail` (the phrase is what the
clock resolves into a due tick). If a field the metrics read cannot be
reconstructed from these rows, the log is incomplete and the replay test is
what should say so.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from recoup.domain.enums import Arm, RowKind
from recoup.domain.models import (
    ActionRecord,
    AuditRow,
    LLMProposal,
    OutcomeRecord,
    PolicyVerdict,
    Tick,
    canonical_json,
)

#: `prev_row_hash` of the first row in a run. A literal, so a truncated file
#: that happens to start mid-run is detectable.
GENESIS_HASH: str = "0" * 32


def row_hash(row: AuditRow) -> str:
    """Content hash of one row, over its canonical JSON.

    Canonical because `dict` ordering and float formatting must not change the
    chain: the same run replayed on another machine has to produce the same
    hashes or the whole device is decorative.
    """
    payload = canonical_json(row.model_dump(mode="json"))
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=16).hexdigest()


class AuditLog:
    """The append-only log for one arm of one run.

    Rows are held in memory and flushed to JSONL. A run of 126 records over 112
    ticks produces a few thousand rows, which is small enough that streaming
    buys nothing and keeping them addressable buys the replay test a lot.
    """

    def __init__(self, run_id: str, arm: Arm) -> None:
        self.run_id = run_id
        self.arm = arm
        self._rows: list[AuditRow] = []
        self._last_hash: str = GENESIS_HASH

    @classmethod
    def resume(cls, rows: list[AuditRow]) -> AuditLog:
        """Continue a log read back from disk, so a later event can be appended.

        The Phase 4 webhook is why this exists. A payer settles a real payment
        link after the run has finished, and that outcome belongs in the same
        log as the decision that sent the link -- as a NEW row, which is what
        invariant 5 has always said outcomes are. Reconstructing the chain here
        rather than in the reconciler keeps every `prev_row_hash` in this file.

        Verifies before continuing: appending to a log whose chain is already
        broken would bury the break under a valid-looking row.
        """
        if not rows:
            raise ValueError("cannot resume an empty log")
        verify_chain(rows)
        log = cls(rows[0].run_id, rows[0].arm)
        log._rows = list(rows)
        log._last_hash = row_hash(rows[-1])
        return log

    def __len__(self) -> int:
        return len(self._rows)

    def __iter__(self) -> Iterator[AuditRow]:
        """Rows in the order they were written. Read-only by convention."""
        return iter(self._rows)

    @property
    def rows(self) -> list[AuditRow]:
        """A copy. Callers get no handle on the list the log appends to."""
        return list(self._rows)

    def append(
        self,
        *,
        kind: RowKind,
        tick: Tick,
        record_id: str,
        input_snapshot: dict[str, Any] | None = None,
        llm_proposal: LLMProposal | None = None,
        policy_verdict: PolicyVerdict | None = None,
        policy_rule: str | None = None,
        action: ActionRecord | None = None,
        outcome: OutcomeRecord | None = None,
    ) -> AuditRow:
        """Write one row. The only mutating operation on this class."""
        row = AuditRow(
            run_id=self.run_id,
            arm=self.arm,
            row_id=len(self._rows),
            prev_row_hash=self._last_hash,
            kind=kind,
            tick=tick,
            record_id=record_id,
            input_snapshot=input_snapshot,
            llm_proposal=llm_proposal,
            policy_verdict=policy_verdict,
            policy_rule=policy_rule,
            action=action,
            outcome=outcome,
        )
        self._rows.append(row)
        self._last_hash = row_hash(row)
        return row

    # -- persistence ---------------------------------------------------------

    def write(self, path: Path) -> Path:
        """Flush to JSONL, one row per line.

        `newline=""` so that Windows does not rewrite `\\n` as `\\r\\n` and change
        the bytes of a file whose whole purpose is to be compared.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            for row in self._rows:
                handle.write(canonical_json(row.model_dump(mode="json")))
                handle.write("\n")
        return path


def read_log(path: Path) -> list[AuditRow]:
    """Read a JSONL log back into rows. Blank lines are skipped, not tolerated silently."""
    rows: list[AuditRow] = []
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                rows.append(AuditRow.model_validate(json.loads(text)))
            # Broad on purpose: a malformed line is a malformed line, and the
            # file position is the part that helps whoever has to fix it.
            except Exception as exc:
                raise ValueError(f"{path}:{number}: not a valid audit row: {exc}") from exc
    return rows


class ChainBroken(RuntimeError):
    """The hash chain does not verify. Names the row where it broke."""

    def __init__(self, row_id: int, expected: str, found: str) -> None:
        super().__init__(
            f"audit chain broken at row {row_id}: "
            f"prev_row_hash is {found}, but the preceding row hashes to {expected}"
        )
        self.row_id = row_id


def verify_chain(rows: list[AuditRow]) -> None:
    """Walk the chain and raise on the first break. Returns None when intact.

    Checks three things, because a chain that only checks hashes still admits a
    file with rows missing from the middle: the hash link, the `row_id`
    sequence, and that every row belongs to the same run and arm.
    """
    previous = GENESIS_HASH
    for index, row in enumerate(rows):
        if row.row_id != index:
            raise ChainBroken(index, f"row_id {index}", f"row_id {row.row_id}")
        if rows and (row.run_id != rows[0].run_id or row.arm is not rows[0].arm):
            raise ChainBroken(
                row.row_id,
                f"{rows[0].run_id}/{rows[0].arm}",
                f"{row.run_id}/{row.arm}",
            )
        if row.prev_row_hash != previous:
            raise ChainBroken(row.row_id, previous, row.prev_row_hash)
        previous = row_hash(row)
