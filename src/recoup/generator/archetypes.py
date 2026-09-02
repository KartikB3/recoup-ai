"""Payer archetype distributions. Phase 1.

Six archetypes per build spec section 1, each a distribution over amount, days
overdue, prior payment behaviour and free-text propensity. Documented in
docs/SEED-DISTRIBUTION.md.

These govern GENERATION only. How a payer responds to being chased lives in
`ledger.adjudicator`, keyed by the same enum. The split is deliberate: the
generator writes the world, the adjudicator runs it, and neither imports the
other.

The batch composition was chosen backwards from the metric table
-----------------------------------------------------------------
Every row of the table in build spec section 7a needs non-zero mass, or the
Phase 2 gate produces a table with empty cells and proves nothing:

  * `PAID_UNRECONCILED` gives *false interventions* a real denominator. Ten of
    them, every one carrying the hidden flag, so chasing one is a measurable
    error rather than a rhetorical one.
  * `DISPUTING` gives the hard-stop rule something to fire on. Eighteen, of
    which only twelve carry a visible `dispute_description`. **The other six
    are the whole argument for the LLM**: their objection exists only in the
    prose, so a rule keyed on a structured field misses them and a reader
    does not.
  * `DISTRESSED` gives escalation-to-human and the hardship path their mass.
  * Amounts are shaped so that a meaningful number of records sit above the
    merchant escalation threshold, rather than leaving that rule dormant.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from recoup.domain.enums import Archetype, Flag

#: Total records emitted. The spec floor is 120.
BATCH_SIZE: int = 126

#: The parent-group cluster: nine invoices, one group, all quiet in one week.
CLUSTER_SIZE: int = 9

#: Merchant escalation threshold used when shaping the amount distribution, so
#: that the Phase 2 rule has records to fire on. Paise. Rs 5,00,000.
ESCALATION_REFERENCE_PAISE: int = 50_000_000

#: GST at 18%, applied exactly. `taxable_rupees * 118` is the invoice value in
#: paise with no floating point anywhere, and it makes the emitted amounts look
#: like real tax invoices rather than round numbers.
GST_MULTIPLIER_PAISE: int = 118


@dataclass(frozen=True)
class ArchetypeProfile:
    """Everything the generator needs to emit one payer of this kind."""

    count: int
    """How many records of this archetype in the batch, cluster records included."""

    taxable_rupees_range: tuple[int, int]
    """Log-uniform bounds on the pre-tax invoice value, in whole rupees."""

    days_overdue_range: tuple[int, int]
    """Days past due at tick 0. Uniform."""

    payment_terms_days: tuple[int, ...]
    """Credit terms the invoice was issued on. Chosen uniformly."""

    prior_invoices_range: tuple[int, int]
    """How many settled invoices of this payer appear in `history`."""

    prior_lateness_range: tuple[int, int]
    """Days late those prior invoices were settled. The payer's track record."""

    prior_partial_rate: float
    """Share of prior invoices settled short of the full value."""

    note_rate: float
    """Probability the record carries a payer note."""

    email_rate: float
    """Probability the record carries at least one email reply."""

    second_email_rate: float
    """Probability of a second reply, given there is a first."""

    flags: frozenset[Flag] = field(default_factory=frozenset)
    """Ground-truth flags every record of this archetype carries."""

    visible_dispute_rate: float = 0.0
    """Share of records whose objection also appears in `dispute_description`.

    Below 1.0 on purpose for DISPUTING. The remainder carry the objection only
    in prose, which is exactly the population a structured-field rule misses.
    """


PROFILES: dict[Archetype, ArchetypeProfile] = {
    # Will pay, on their own cycle, whichever way you chase them. Chasing them
    # early buys nothing and spends contact budget. The agent's best move here
    # is usually WAIT, and proving that is half the thesis.
    Archetype.RELIABLE_BUT_SLOW: ArchetypeProfile(
        count=34,
        taxable_rupees_range=(21_000, 1_020_000),
        days_overdue_range=(3, 40),
        payment_terms_days=(30, 45, 45, 60),
        prior_invoices_range=(4, 6),
        prior_lateness_range=(12, 45),
        prior_partial_rate=0.03,
        note_rate=0.85,
        email_rate=0.70,
        second_email_rate=0.30,
    ),
    # Pays eventually and responds to pressure. This is the population where
    # chasing genuinely works, and the baseline arm does well on it.
    Archetype.CHRONIC_LATE: ArchetypeProfile(
        count=30,
        taxable_rupees_range=(13_000, 680_000),
        days_overdue_range=(15, 75),
        payment_terms_days=(30, 30, 45),
        prior_invoices_range=(3, 6),
        prior_lateness_range=(28, 85),
        prior_partial_rate=0.15,
        note_rate=0.80,
        email_rate=0.60,
        second_email_rate=0.35,
    ),
    # Will not pay until the commercial objection is settled. Contacting them
    # converts an objection into a formal dispute and a human queue item.
    Archetype.DISPUTING: ArchetypeProfile(
        count=18,
        taxable_rupees_range=(34_000, 1_530_000),
        days_overdue_range=(25, 140),
        payment_terms_days=(30, 45, 60),
        prior_invoices_range=(2, 5),
        prior_lateness_range=(20, 70),
        prior_partial_rate=0.35,
        note_rate=0.90,
        email_rate=0.80,
        second_email_rate=0.45,
        flags=frozenset({Flag.DISPUTED}),
        visible_dispute_rate=0.667,
    ),
    # Genuine hardship. Pressure lowers the odds of payment and raises the odds
    # of a complaint; time and a human do better.
    Archetype.DISTRESSED: ArchetypeProfile(
        count=12,
        taxable_rupees_range=(8_500, 340_000),
        days_overdue_range=(20, 110),
        payment_terms_days=(30, 45),
        prior_invoices_range=(3, 5),
        prior_lateness_range=(35, 95),
        prior_partial_rate=0.45,
        note_rate=0.90,
        email_rate=0.80,
        second_email_rate=0.40,
        flags=frozenset({Flag.HARDSHIP_CLAIMED}),
    ),
    # No replies, ever. Most of these carry no free text at all -- silence is
    # itself the signal, and a corpus where every record talks is a corpus that
    # flatters the reasoner.
    Archetype.SILENT: ArchetypeProfile(
        count=22,
        taxable_rupees_range=(6_800, 510_000),
        days_overdue_range=(10, 95),
        payment_terms_days=(30, 45, 60),
        prior_invoices_range=(1, 3),
        prior_lateness_range=(25, 90),
        prior_partial_rate=0.20,
        note_rate=0.35,
        email_rate=0.15,
        second_email_rate=0.10,
    ),
    # The money already left them. Every contact is a false intervention and
    # the metric table counts it as one.
    Archetype.PAID_UNRECONCILED: ArchetypeProfile(
        count=10,
        taxable_rupees_range=(17_000, 425_000),
        days_overdue_range=(5, 35),
        payment_terms_days=(30, 45),
        prior_invoices_range=(4, 6),
        prior_lateness_range=(5, 30),
        prior_partial_rate=0.05,
        note_rate=0.90,
        email_rate=0.85,
        second_email_rate=0.35,
        flags=frozenset({Flag.ALREADY_PAID_UNRECONCILED}),
    ),
}

#: Archetypes of the nine cluster records, in emission order. These are drawn
#: FROM the counts above, not added to them: the cluster is part of the book,
#: not a bolt-on. A group that has gone quiet reads as silence or as slippage
#: from otherwise sound payers -- never as a dispute, because a dispute would
#: give the batch insight an easier answer than it deserves.
CLUSTER_ARCHETYPES: tuple[Archetype, ...] = (
    Archetype.SILENT,
    Archetype.RELIABLE_BUT_SLOW,
    Archetype.SILENT,
    Archetype.CHRONIC_LATE,
    Archetype.SILENT,
    Archetype.RELIABLE_BUT_SLOW,
    Archetype.CHRONIC_LATE,
    Archetype.SILENT,
    Archetype.RELIABLE_BUT_SLOW,
)

#: Hint strength carried by each cluster record, in the same order. Two STRONG,
#: three MEDIUM, four WEAK-or-silent. If every one of the nine announced a
#: centralised payment desk, the batch insight would be a keyword search.
CLUSTER_HINT_PLAN: tuple[str, ...] = (
    "WEAK",
    "STRONG",
    "WEAK",
    "MEDIUM",
    "NONE",
    "STRONG",
    "MEDIUM",
    "NONE",
    "MEDIUM",
)


def general_counts() -> dict[Archetype, int]:
    """Archetype counts for the non-cluster records.

    The cluster's nine are subtracted from the population totals so that
    `PROFILES[a].count` remains the truthful batch-wide figure.
    """
    counts = {a: p.count for a, p in PROFILES.items()}
    for archetype in CLUSTER_ARCHETYPES:
        counts[archetype] -= 1
    return counts


def total_records() -> int:
    """Batch size implied by the profile table. Must equal BATCH_SIZE."""
    return sum(p.count for p in PROFILES.values())
