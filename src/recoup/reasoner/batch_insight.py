"""Deterministic fallback for the portfolio-level insight.

The model path lives in :mod:`recoup.reasoner.client`; this component guarantees
the batch call has the same offline posture as per-record reasoning.  It reads
only the aggregate of reasoner snapshots and describes the group correlation as
an inference.  The returned recommendation still has no effect until policy
validates it.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from recoup.domain.models import Tick
from recoup.reasoner.schemas import BatchInsight

MIN_CANDIDATE_RECORDS = 3
MIN_CANDIDATE_PAYERS = 3


class DeterministicBatchFallback:
    """Find an explicit parent group without using simulation ground truth."""

    name = "deterministic-batch-fallback"

    def analyze(self, snapshots: list[dict[str, Any]], tick: Tick) -> BatchInsight:
        """Return the largest credible open parent group, deterministically."""
        del tick
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for snapshot in snapshots:
            group_id = snapshot.get("parent_group_id")
            if group_id and int(snapshot.get("outstanding_paise", 0)) > 0:
                grouped[str(group_id)].append(snapshot)

        candidates = [
            (group_id, rows)
            for group_id, rows in grouped.items()
            if len(rows) >= MIN_CANDIDATE_RECORDS
            and len({str(row["payer_id"]) for row in rows}) >= MIN_CANDIDATE_PAYERS
        ]
        if not candidates:
            return BatchInsight(
                pattern_found=False,
                diagnosis="No defensible parent-group pattern was found.",
                confidence=1.0,
                reasoning="No open parent group met the minimum breadth checks.",
            )

        group_id, rows = min(candidates, key=lambda item: (-len(item[1]), item[0]))
        invoice_ids = sorted(str(row["invoice_id"]) for row in rows)
        return BatchInsight(
            pattern_found=True,
            diagnosis="Correlated silence is consistent with one account-level process event.",
            parent_group_id=group_id,
            invoice_ids=invoice_ids,
            confidence=0.70,
            reasoning=(
                "Several open invoices across distinct payers share one explicit parent group; "
                "treating them independently would duplicate contact before relationship review."
            ),
            suppression_recommended=True,
        )
