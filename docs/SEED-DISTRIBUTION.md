# Seed Distribution

Exactly what `recoup generate --seed 42 --count 126` produces, so the batch is
reproducible by anyone and auditable by a judge.

**Command:** `uv run recoup generate --seed 42 --count 126`
**Output:** `data/batches/seed-42-n126.json`
**SHA-256:** `c903d91724d1c4566cb5c0a67ecf308eb6a0636772fe4a744a6b3f423188dd6f`

The same bytes appear in `runs/*/batch.json`, and a test asserts it -- the two
were briefly written by different serialisers, which cost nothing functionally
and would have failed exactly the check a reader is most likely to run. ISS-022.

Verified byte-identical across three separate interpreters under
`PYTHONHASHSEED` 0, 1 and 12345. That specific check exists because
`Invoice.flags` is a `set` and set iteration order varies with the hash seed; a
single-process comparison would have passed while the file differed on another
machine. Enforced by `tests/test_generator.py::test_byte_identical_across_processes_and_hash_seeds`.

---

## Headline

| | |
|---|---|
| Records | **126** (spec floor is 120) |
| Distinct payers | 46 (40 general + 6 cluster members) |
| Merchant | Ashwatth Industrial Supplies Pvt Ltd (invented) |
| Book value | **Rs 2,52,97,406.40** (2,529,740,640 paise) |
| Virtual epoch | 2026-04-06, a Monday |
| Horizon | 112 ticks = 28 virtual days, 1 tick = 6 virtual hours |

Every name, company, GSTIN, contact and phone number in this repo is invented.
No real entity appears anywhere in the corpus.

---

## Archetype mix

| Archetype | Count | Share | What it is for |
|---|---|---|---|
| `RELIABLE_BUT_SLOW` | 34 | 27.0% | Pays on its own cycle regardless. Chasing buys nothing — this is the population the agent wins on by choosing WAIT. |
| `CHRONIC_LATE` | 30 | 23.8% | Chasing genuinely works. This is why the naive baseline is not a straw man. |
| `SILENT` | 22 | 17.5% | Rarely answers. Contact is close to a pure cost. |
| `DISPUTING` | 18 | 14.3% | Contact converts a commercial objection into a formal dispute and a human-queue item. |
| `DISTRESSED` | 12 | 9.5% | Pressure *lowers* the odds of payment and raises the odds of a complaint. |
| `PAID_UNRECONCILED` | 10 | 7.9% | The money already left the payer. Every contact is a false intervention. |

The mix was chosen backwards from the Phase 2 metric table so that no row of it
comes out empty. `PAID_UNRECONCILED` gives *false interventions* a real
denominator; `DISPUTING` gives the hard-stop rule something to fire on;
`DISTRESSED` gives escalation-to-human its mass.

**Archetype is ground truth.** It never appears in `Invoice.to_snapshot()`, so
no reasoner can read it. The metrics *do* read it — scoring is allowed to see a
held-out label the agent is not, and that asymmetry is the point of having one.

---

## Amounts

All money is integer paise. GST is applied exactly as `taxable_rupees * 118`,
so every amount is a whole number of rupees plus 18% with no fractional paise
and no floating point anywhere in the pipeline.

| | Paise | Rupees |
|---|---|---|
| min | 1,229,560 | Rs 12,295.60 |
| p25 | 5,083,440 | Rs 50,834.40 |
| median | 10,522,060 | Rs 1,05,220.60 |
| p90 | 50,013,120 | Rs 5,00,131.20 |
| max | 131,836,680 | Rs 13,18,366.80 |

Log-uniform within each archetype's bounds, rounded to ten rupees. **14 records
sit above the Rs 5,00,000 merchant escalation reference**, so that the Phase 2
escalation rule has real records to fire on rather than lying dormant.

## Days overdue at tick 0

| min | p25 | median | p90 | max |
|---|---|---|---|---|
| 3 | 23 | 37 | 87 | 130 |

Every record is already past due at intake — this is an at-risk book, not a
ledger of open invoices.

## Flag incidence

| Flag | Count |
|---|---|
| `DISPUTED` | 18 |
| `HARDSHIP_CLAIMED` | 12 |
| `ALREADY_PAID_UNRECONCILED` | 10 |

Flags are ground truth and are excluded from the snapshot, exactly as archetype
is.

---

## Free text — the part that matters

Without this the records carry only amounts and dates, `if days_overdue > 30`
reproduces the agent exactly, and the project is a rules engine with an API
bill. It is the highest-leverage artifact in the build.

| | |
|---|---|
| Templates | **54** across five files |
| Distinct renderings available | **8,333** via slot variation |
| Templates actually drawn on seed 42 | 53 of 54 |
| Records carrying a payer note | 99 |
| Email replies emitted | 104, across 76 records |
| Records with a visible `dispute_description` | 12 |
| **Records carrying no free text at all** | **17** |

Those 17 matter as much as the other 109. Silence is itself a signal, and a
corpus where every record talks is a corpus that flatters the reasoner.

### The templates

| File | Kind | Templates |
|---|---|---|
| `payer_notes.yaml` | `PAYER_NOTE` | 20 |
| `email_replies.yaml` | `EMAIL_REPLY` | 12 |
| `dispute_descriptions.yaml` | `DISPUTE_DESCRIPTION` | 6 |
| `cluster_notes.yaml` | `PAYER_NOTE` (CLUSTER pool) | 8 |
| `cluster_emails.yaml` | `EMAIL_REPLY` (CLUSTER pool) | 8 |

The rule the corpus is built around: **a template body must not contain its own
signal's vocabulary.** "We dispute this invoice" is a regex; "the GRN quantity
does not tally with your challan so the lot is held at gate" is a reasoning
task.

### Eighteen disputes, twelve of them visible

Of the 18 `DISPUTING` records, **12 carry a structured `dispute_description`
and 6 do not**. Those 6 are the whole argument for the LLM: their objection
exists only in prose, so a rule keyed on a structured field misses them and a
reader does not.

### Sample — the spotlight record

`ASH-2026-0010` · Meridian Polymers Pvt Ltd · **Rs 4,38,960.00** · due
2026-03-15, **22 days overdue** at tick 0, 45-day terms.

> Their standard terms are 60 days from GRN, not from invoice date. They count
> from inward, and inward happened after the plant shutdown. Same pattern as the
> last four bills.

and by email:

> The bill is booked at our end and is in the queue for release. Payments to
> vendors are released twice a month, on the 10th and the 25th, and this one
> falls in the next cycle. Please do not send repeated reminders on this; it
> will be released in course.

Nothing in the structured fields says any of that. `days_overdue = 22` on a
45-day-terms invoice looks like an ordinary delinquency; the prose says it is a
payer on a different clock who will pay without being chased. The baseline
contacts this record five times. Both arms end up paid; only one spent the
contacts.

---

## The cluster event

Nine invoices, one parent group, all going quiet inside one virtual week.

**Group:** `GRP-SURYODAYA` · **Quiet window:** 2026-03-27 to 2026-04-02
(every cluster record's last inbound message lands inside it, and nothing
arrives after).

| Invoice | Payer | Archetype | Hint |
|---|---|---|---|
| ASH-2026-0001 | Suryodaya Textiles Ltd | SILENT | WEAK |
| ASH-2026-0002 | Suryodaya Retail Ventures Pvt Ltd | RELIABLE_BUT_SLOW | **STRONG** |
| ASH-2026-0003 | Suryodaya Infra Services Pvt Ltd | SILENT | WEAK |
| ASH-2026-0004 | Suryodaya Agro Processing Ltd | CHRONIC_LATE | MEDIUM |
| ASH-2026-0005 | Suryodaya Logistics Pvt Ltd | SILENT | *none* |
| ASH-2026-0006 | Suryodaya Speciality Yarns Ltd | RELIABLE_BUT_SLOW | **STRONG** |
| ASH-2026-0007 | Suryodaya Textiles Ltd | CHRONIC_LATE | MEDIUM |
| ASH-2026-0008 | Suryodaya Retail Ventures Pvt Ltd | SILENT | *none* |
| ASH-2026-0009 | Suryodaya Infra Services Pvt Ltd | RELIABLE_BUT_SLOW | MEDIUM |

The true cause is that the group moved payment authority to a central desk.
**No template says so.** The CLUSTER pool bans a specific word list outright —
*freeze, frozen, procurement, payment hold, on hold, suspended, moratorium,
stopped payment, blocked payment* — and `tests/test_corpus.py` fails the build
if any of them appears in a template body, a subject line **or any slot value**,
drawn or not.

The hints are graded on purpose: **two STRONG, three MEDIUM, two WEAK, two
silent.** If all nine announced a centralised payment desk, the batch-level
insight would be a keyword search. Two of nine means the other seven have to be
connected by co-occurrence — one parent group, one quiet week — rather than by
reading the loudest note twice.

The archetypes are drawn *from* the population totals, not added to them: the
cluster is part of the book, not a bolt-on. None of the nine is `DISPUTING`,
because a dispute would give the insight an easier answer than it deserves.

All nine draw **distinct templates**. An earlier version let two of them land on
the same template pair and read as copy-paste, in precisely the passage a judge
looks at hardest — see ISS-015.

---

## A caveat worth stating plainly

Every number in the archetype and behaviour tables is a **modelling choice, not
a measured quantity**. There is no real receivables dataset behind them. What is
defensible is the *ordering* — reliable payers settle without chasing, chronic
late payers respond to it, disputing payers are made worse by it, distressed
payers complain — and the ordering is what the comparison in Phase 2 rests on.
The absolute recovery rates are a property of this simulation and should not be
read as a forecast of anything.

The behaviour parameters live in `ledger/adjudicator.py` and one pair of them
was explicitly calibrated; the reasoning is written out at
`FATIGUE_COMPLAINT_STEP` rather than left implicit.
