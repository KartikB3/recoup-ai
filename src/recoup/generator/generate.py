"""Seeded batch generator. Phase 1.

Reproducible: the same seed produces byte-identical output. Emits to
data/batches/.

Owns the deliberate cluster event: nine invoices sharing one parent_group_id,
all going silent in the same week, whose free text HINTS at a payment
centralisation without naming it. The LLM must infer it, or the batch-level
insight in build spec section 7b is worthless.

How determinism is achieved
---------------------------
Every record is generated from its own RNG, seeded on the string
`"{seed}|record|{index}"`. `random.Random` hashes a string seed with SHA-512, so
the stream does not depend on `PYTHONHASHSEED` and does not shift when an
unrelated part of the generator changes. Two consequences worth having:

  * changing how emails are drawn cannot silently reshuffle every amount;
  * a single record can be regenerated in isolation while debugging.

The remaining hazard is set iteration order, which is why `Invoice.flags` has an
explicit sorted serialiser. Without it the byte-identical gate fails across
processes, intermittently. See tests/test_generator.py.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from datetime import timedelta
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from recoup.domain.enums import (
    Archetype,
    FreeTextKind,
    PaymentEventKind,
    RecordSource,
    SignalKind,
)
from recoup.domain.models import (
    VIRTUAL_EPOCH,
    ContactLedger,
    EmailReply,
    FreeText,
    Invoice,
    PaymentEvent,
    TextProvenance,
    VirtualDate,
)
from recoup.generator.archetypes import (
    BATCH_SIZE,
    CLUSTER_ARCHETYPES,
    CLUSTER_HINT_PLAN,
    CLUSTER_SIZE,
    GST_MULTIPLIER_PAISE,
    PROFILES,
    ArchetypeProfile,
)
from recoup.generator.freetext import Corpus, Rendering, Template

#: Emission order of the archetypes. Fixed, because apportionment remainders are
#: handed out in this order and the batch must not depend on dict iteration.
ARCHETYPE_ORDER: tuple[Archetype, ...] = (
    Archetype.RELIABLE_BUT_SLOW,
    Archetype.CHRONIC_LATE,
    Archetype.DISPUTING,
    Archetype.DISTRESSED,
    Archetype.SILENT,
    Archetype.PAID_UNRECONCILED,
)

#: How many payers serve each archetype in a full-size batch. Sums to the 40
#: general payers in corpus/entities.yaml.
PAYERS_PER_ARCHETYPE: dict[Archetype, int] = {
    Archetype.RELIABLE_BUT_SLOW: 11,
    Archetype.CHRONIC_LATE: 9,
    Archetype.DISPUTING: 6,
    Archetype.DISTRESSED: 4,
    Archetype.SILENT: 6,
    Archetype.PAID_UNRECONCILED: 4,
}

#: The week the parent group goes quiet, as day offsets before the epoch. Every
#: cluster record's last inbound message lands inside this window and nothing
#: arrives after it. The co-occurrence is the signal.
QUIET_WINDOW_DAYS_BEFORE_EPOCH: tuple[int, int] = (10, 4)

#: The spotlight record. Phase 5's timeline view is keyed by payer name, so one
#: memorable payer is pinned here rather than left to the RNG: a reliable payer
#: on a 45-day-from-GRN cycle, whose invoice the baseline chases five times and
#: the agent leaves alone. Both arms end up paid; only one spent the contacts.
SPOTLIGHT_PAYER_ID = "PYR-001"
SPOTLIGHT_TAXABLE_RUPEES = 372_000
SPOTLIGHT_DAYS_OVERDUE = 22
SPOTLIGHT_TERMS_DAYS = 45
SPOTLIGHT_NOTE_TEMPLATE = "PN-02-grn-cycle"
SPOTLIGHT_EMAIL_TEMPLATE = "ER-01-in-the-run"


class BatchMeta(BaseModel):
    """Everything needed to reproduce and audit a batch. Written into the file."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    seed: int
    record_count: int
    epoch: VirtualDate
    parent_group_id: str
    cluster_invoice_ids: list[str]
    quiet_window: list[VirtualDate]
    spotlight_invoice_id: str
    merchant_legal_name: str


class Batch(BaseModel):
    """A generated batch: metadata plus records. This is what lands on disk."""

    model_config = ConfigDict(extra="forbid")

    meta: BatchMeta
    records: list[Invoice] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _rng(seed: int, *parts: object) -> random.Random:
    """A sub-stream keyed by purpose, so unrelated changes do not reshuffle the batch."""
    return random.Random("|".join([str(seed), *(str(p) for p in parts)]))


def _entities() -> dict[str, Any]:
    """Load corpus/entities.yaml."""
    path = resources.files("recoup.generator") / "corpus" / "entities.yaml"
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data


def apportion(count: int) -> dict[Archetype, int]:
    """Split `count` records across archetypes in the profile-table proportions.

    Exact at the default size; largest-remainder apportionment otherwise, so
    `--count 150` stays a legitimate batch rather than a broken one.
    """
    if count == BATCH_SIZE:
        return {a: PROFILES[a].count for a in ARCHETYPE_ORDER}
    total = sum(PROFILES[a].count for a in ARCHETYPE_ORDER)
    exact = {a: count * PROFILES[a].count / total for a in ARCHETYPE_ORDER}
    counts = {a: int(exact[a]) for a in ARCHETYPE_ORDER}
    remainder = count - sum(counts.values())
    for archetype in sorted(ARCHETYPE_ORDER, key=lambda a: (-(exact[a] - counts[a]), a.value)):
        if remainder <= 0:
            break
        counts[archetype] += 1
        remainder -= 1
    return counts


def _split_evenly(total: int, buckets: int) -> list[int]:
    """Distribute `total` items across `buckets` as evenly as possible."""
    if buckets <= 0:
        return []
    base, extra = divmod(total, buckets)
    return [base + (1 if i < extra else 0) for i in range(buckets)]


def _log_uniform_rupees(rng: random.Random, bounds: tuple[int, int]) -> int:
    """A plausible invoice value: log-uniform, rounded to ten rupees."""
    low, high = bounds
    value = round(math.exp(rng.uniform(math.log(low), math.log(high))))
    return max(low, value - value % 10)


def _rupees_str(amount_paise: int) -> str:
    """Indian-grouped rupees with no symbol, for use inside free text."""
    digits = str(amount_paise // 100)
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    parts: list[str] = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join([*parts, tail])


def _prior_history(
    rng: random.Random,
    profile: ArchetypeProfile,
    issued_on: VirtualDate,
    amount_paise: int,
    payer_index: int,
) -> list[PaymentEvent]:
    """The payer's track record: how they settled their previous bills.

    One event per prior invoice, carrying how many days past due it was
    settled. This is the structured half of the signal; the free text is the
    other half, and the two are meant to be read together.
    """
    events: list[PaymentEvent] = []
    n_prior = rng.randint(*profile.prior_invoices_range)
    for index in range(n_prior, 0, -1):
        terms = rng.choice(profile.payment_terms_days)
        prior_issued = issued_on - timedelta(days=34 * index + rng.randint(0, 11))
        prior_due = prior_issued + timedelta(days=terms)
        days_late = rng.randint(*profile.prior_lateness_range)
        settled_on = prior_due + timedelta(days=days_late)
        partial = rng.random() < profile.prior_partial_rate
        value = int(amount_paise * rng.uniform(0.35, 1.6))
        value -= value % 100
        paid = int(value * rng.uniform(0.4, 0.85)) if partial else value
        paid -= paid % 100
        events.append(
            PaymentEvent(
                kind=PaymentEventKind.PAID_PARTIAL if partial else PaymentEventKind.PAID_FULL,
                on=settled_on,
                amount_paise=paid,
                reference=f"ASH-{prior_issued.year}-{payer_index:03d}{index:02d}",
                note=(
                    f"terms {terms}d, settled {days_late} days past due"
                    + (f", short by {_rupees_str(value - paid)}" if partial else "")
                ),
            )
        )
    return events


def _reserved_slots(
    invoice_no: str,
    payer: dict[str, str],
    contact: dict[str, str],
    merchant: dict[str, str],
    amount_paise: int,
    days_overdue: int,
) -> dict[str, str]:
    """Values the generator supplies to every template."""
    return {
        "invoice_no": invoice_no,
        "payer_name": payer["name"],
        "city": payer["city"],
        "contact_name": contact["name"],
        "contact_role": contact["role"],
        "merchant_short": merchant["short_name"],
        "merchant_legal": merchant["legal_name"],
        "amount_rupees": _rupees_str(amount_paise),
        "days_overdue": str(days_overdue),
    }


def _email_from(
    rendering: Rendering, received_on: VirtualDate, contact: dict[str, str]
) -> EmailReply:
    """Wrap a rendering as an email reply."""
    return EmailReply(
        received_on=received_on,
        from_name=contact["name"],
        from_role=contact["role"],
        subject=rendering.subject or "RE: payment reminder",
        body=rendering.body,
    )


# ---------------------------------------------------------------------------
# generation
# ---------------------------------------------------------------------------


def _without(candidates: list[Template], spent: frozenset[str]) -> list[Template]:
    """Drop already-used templates, unless that would empty the pool.

    Nine companies in one group do not send the same sentence nine times, and
    one payer does not send the same template twice in a fortnight. Repetition
    inside the cluster is the one place it reads as a generator artifact rather
    than as texture, because those nine records are read side by side. Across
    the other 117 it is ordinary and left alone.

    Falling back to the unfiltered list matters: exhausting a narrow strength
    band must degrade to a repeat, never to a record with no free text, which
    would silently change the cluster's shape.
    """
    remaining = [t for t in candidates if t.id not in spent]
    return remaining or candidates


def _build_record(
    *,
    seed: int,
    index: int,
    invoice_no: str,
    archetype: Archetype,
    payer: dict[str, str],
    payer_index: int,
    contact: dict[str, str],
    merchant: dict[str, str],
    corpus: Corpus,
    parent_group_id: str | None,
    cluster_strength: str | None,
    visible_dispute: bool,
    spotlight: bool,
    avoid: frozenset[str] = frozenset(),
) -> Invoice:
    """Emit one invoice. Deterministic in (seed, index, avoid).

    `avoid` names templates already spent by earlier records in the same
    cluster. It is a set of ids the caller accumulates in a fixed order, so
    determinism survives; see `_without` for why it exists.
    """
    profile = PROFILES[archetype]
    rng = _rng(seed, "record", index)

    if spotlight:
        taxable = SPOTLIGHT_TAXABLE_RUPEES
        days_overdue = SPOTLIGHT_DAYS_OVERDUE
        terms = SPOTLIGHT_TERMS_DAYS
    else:
        taxable = _log_uniform_rupees(rng, profile.taxable_rupees_range)
        days_overdue = rng.randint(*profile.days_overdue_range)
        terms = rng.choice(profile.payment_terms_days)

    amount_paise = taxable * GST_MULTIPLIER_PAISE
    due_on = VIRTUAL_EPOCH - timedelta(days=days_overdue)
    issued_on = due_on - timedelta(days=terms)

    history = _prior_history(rng, profile, issued_on, amount_paise, payer_index)
    reserved = _reserved_slots(invoice_no, payer, contact, merchant, amount_paise, days_overdue)

    pool = "CLUSTER" if cluster_strength is not None else "GENERAL"
    template_ids: list[str] = []
    signals: list[SignalKind] = []
    note = ""
    replies: list[EmailReply] = []
    dispute: str | None = None

    def record_rendering(rendering: Rendering) -> None:
        template_ids.append(rendering.template_id)
        signals.extend(rendering.signals)

    # --- payer note --------------------------------------------------------
    if cluster_strength == "NONE":
        # Silence. Nothing arrives from this payer at all, which is precisely
        # what makes the cluster hard: four of the nine say nothing.
        pass
    elif spotlight:
        rendering = corpus.render_by_id(SPOTLIGHT_NOTE_TEMPLATE, rng, reserved)
        note = rendering.body
        record_rendering(rendering)
    else:
        candidates = _without(
            corpus.select(FreeTextKind.PAYER_NOTE, archetype, pool=pool, strength=cluster_strength),
            avoid,
        )
        if candidates and rng.random() < (1.0 if pool == "CLUSTER" else profile.note_rate):
            rendering = corpus.render(rng.choice(candidates), rng, reserved)
            note = rendering.body
            record_rendering(rendering)

    # --- email replies -----------------------------------------------------
    earliest = max(3, min(45, (VIRTUAL_EPOCH - issued_on).days - 1))
    if cluster_strength == "NONE":
        pass
    else:
        if spotlight:
            picks = [corpus.by_id(SPOTLIGHT_EMAIL_TEMPLATE)]
        else:
            candidates = _without(
                corpus.select(
                    FreeTextKind.EMAIL_REPLY, archetype, pool=pool, strength=cluster_strength
                ),
                avoid,
            )
            picks = []
            if candidates and rng.random() < (1.0 if pool == "CLUSTER" else profile.email_rate):
                picks.append(rng.choice(candidates))
                if rng.random() < profile.second_email_rate:
                    # A payer chasing the same bill twice writes two different
                    # letters. Drawing the same template twice reads as a bug.
                    picks.append(rng.choice(_without(candidates, frozenset({picks[0].id}))))
        for template in picks:
            rendering = corpus.render(template, rng, reserved)
            if pool == "CLUSTER":
                # Everything from this group stops inside one week. That
                # co-occurrence, not any single sentence, is the insight.
                late, early = QUIET_WINDOW_DAYS_BEFORE_EPOCH
                offset = rng.randint(early, late)
            else:
                offset = rng.randint(3, earliest)
            replies.append(_email_from(rendering, VIRTUAL_EPOCH - timedelta(days=offset), contact))
            record_rendering(rendering)
        replies.sort(key=lambda r: r.received_on)

    # --- dispute description ----------------------------------------------
    if visible_dispute:
        candidates = corpus.select(FreeTextKind.DISPUTE_DESCRIPTION, archetype)
        if candidates:
            rendering = corpus.render(rng.choice(candidates), rng, reserved)
            dispute = rendering.body
            record_rendering(rendering)

    flags = set(profile.flags)

    return Invoice(
        invoice_id=invoice_no,
        parent_group_id=parent_group_id,
        payer_id=payer["id"],
        payer_name=payer["name"],
        payer_city=payer["city"],
        payer_contact_name=contact["name"],
        payer_contact_role=contact["role"],
        payer_archetype=archetype,
        flags=flags,
        provenance=TextProvenance(
            template_ids=template_ids,
            signals=sorted(set(signals), key=lambda s: s.value),
            cluster_hint_strength=cluster_strength,
        ),
        spotlight=spotlight,
        amount_paise=amount_paise,
        issued_on=issued_on,
        due_on=due_on,
        source=RecordSource.INVOICE,
        history=history,
        free_text=FreeText(payer_notes=note, email_replies=replies, dispute_description=dispute),
        contact_ledger=ContactLedger(),
    )


def generate_batch(seed: int = 42, count: int = BATCH_SIZE) -> Batch:
    """Build a complete batch. Pure: same (seed, count) gives the same object."""
    entities = _entities()
    corpus = Corpus.load()
    merchant: dict[str, str] = entities["merchant"]
    contacts: list[dict[str, str]] = entities["contacts"]
    all_payers: list[dict[str, str]] = entities["payers"]
    cluster_cfg = entities["cluster"]
    cluster_members: list[dict[str, str]] = cluster_cfg["members"]
    parent_group_id: str = cluster_cfg["parent_group_id"]

    cluster_size = min(CLUSTER_SIZE, count)
    targets = apportion(count)
    for archetype in CLUSTER_ARCHETYPES[:cluster_size]:
        targets[archetype] -= 1
    if any(v < 0 for v in targets.values()):
        raise ValueError(f"count={count} is too small to carry the {cluster_size}-record cluster")

    # Payers are shuffled into archetype pools once, with the spotlight payer
    # pinned to the front of its own pool so the demo record is stable.
    pool_rng = _rng(seed, "payer-pools")
    spotlight_payer = next(p for p in all_payers if p["id"] == SPOTLIGHT_PAYER_ID)
    shuffled = [p for p in all_payers if p["id"] != SPOTLIGHT_PAYER_ID]
    pool_rng.shuffle(shuffled)
    shuffled.insert(0, spotlight_payer)

    payer_pools: dict[Archetype, list[dict[str, str]]] = {}
    cursor = 0
    for archetype in ARCHETYPE_ORDER:
        size = PAYERS_PER_ARCHETYPE[archetype]
        payer_pools[archetype] = shuffled[cursor : cursor + size]
        cursor += size

    # DISPUTING records whose objection is also filed as a formal dispute. The
    # remainder carry it only in prose, and are the population a rule keyed on
    # a structured field cannot see.
    disputing_total = targets[Archetype.DISPUTING] + CLUSTER_ARCHETYPES[:cluster_size].count(
        Archetype.DISPUTING
    )
    visible_count = round(disputing_total * PROFILES[Archetype.DISPUTING].visible_dispute_rate)

    records: list[Invoice] = []
    cluster_ids: list[str] = []
    spotlight_id = ""
    index = 0
    disputing_seen = 0

    def next_invoice_no() -> str:
        return f"{merchant['invoice_prefix']}-2026-{index + 1:04d}"

    # --- the cluster, first, so its ids are stable and easy to point at ----
    # `spent` walks forward through the nine so no two of them reach for the
    # same template. The loop order is fixed, so this stays deterministic.
    spent: frozenset[str] = frozenset()
    for slot in range(cluster_size):
        archetype = CLUSTER_ARCHETYPES[slot]
        payer = cluster_members[slot % len(cluster_members)]
        contact = contacts[(slot * 3 + 1) % len(contacts)]
        invoice_no = next_invoice_no()
        record = _build_record(
            seed=seed,
            index=index,
            invoice_no=invoice_no,
            archetype=archetype,
            payer=payer,
            payer_index=900 + slot,
            contact=contact,
            merchant=merchant,
            corpus=corpus,
            parent_group_id=parent_group_id,
            cluster_strength=CLUSTER_HINT_PLAN[slot],
            visible_dispute=False,
            spotlight=False,
            avoid=spent,
        )
        records.append(record)
        spent |= frozenset(record.provenance.template_ids)
        cluster_ids.append(invoice_no)
        index += 1

    # --- the rest of the book ---------------------------------------------
    for archetype in ARCHETYPE_ORDER:
        pool = payer_pools[archetype]
        per_payer = _split_evenly(targets[archetype], len(pool))
        for payer_slot, n_records in enumerate(per_payer):
            payer = pool[payer_slot]
            for k in range(n_records):
                contact = contacts[(index * 5 + payer_slot) % len(contacts)]
                invoice_no = next_invoice_no()
                is_spotlight = payer["id"] == SPOTLIGHT_PAYER_ID and k == 0
                visible_dispute = False
                if archetype is Archetype.DISPUTING:
                    visible_dispute = disputing_seen < visible_count
                    disputing_seen += 1
                records.append(
                    _build_record(
                        seed=seed,
                        index=index,
                        invoice_no=invoice_no,
                        archetype=archetype,
                        payer=payer,
                        payer_index=payer_slot,
                        contact=contact,
                        merchant=merchant,
                        corpus=corpus,
                        parent_group_id=None,
                        cluster_strength=None,
                        visible_dispute=visible_dispute,
                        spotlight=is_spotlight,
                    )
                )
                if is_spotlight:
                    spotlight_id = invoice_no
                index += 1

    late, early = QUIET_WINDOW_DAYS_BEFORE_EPOCH
    meta = BatchMeta(
        seed=seed,
        record_count=len(records),
        epoch=VIRTUAL_EPOCH,
        parent_group_id=parent_group_id,
        cluster_invoice_ids=cluster_ids,
        quiet_window=[
            VIRTUAL_EPOCH - timedelta(days=late),
            VIRTUAL_EPOCH - timedelta(days=early),
        ],
        spotlight_invoice_id=spotlight_id,
        merchant_legal_name=merchant["legal_name"],
    )
    return Batch(meta=meta, records=records)


# ---------------------------------------------------------------------------
# persistence
# ---------------------------------------------------------------------------


def serialise(batch: Batch) -> str:
    """Render a batch as the exact text that goes on disk.

    Indented and in declaration order, because a judge reads this file. Field
    order is stable because Pydantic preserves it and because the one set-valued
    field has an explicit sorted serialiser.
    """
    payload = batch.model_dump(mode="json")
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def batch_filename(seed: int, count: int) -> str:
    """Canonical filename for a batch. Encodes what reproduces it."""
    return f"seed-{seed}-n{count}.json"


def write_batch(batch: Batch, out_dir: Path) -> tuple[Path, str]:
    """Write a batch and return its path and the SHA-256 of the bytes written.

    `newline=""` keeps Windows from turning the emitted `\\n` into `\\r\\n`,
    which would make the byte-identical gate pass on Linux and fail here.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    text = serialise(batch)
    path = out_dir / batch_filename(batch.meta.seed, batch.meta.record_count)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return path, hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_batch(path: Path) -> Batch:
    """Read a batch back. The runner and the tests both start here."""
    return Batch.model_validate_json(path.read_text(encoding="utf-8"))
