# Recoup — Standing observations

Things that are **true and unresolved by design**. Not defects, not work items,
not history.

This file exists because the other four docs each refused these entries for a
good reason. `ISSUES.md` is a graded submission field about problems *hit* and
*fixed* — an entry there implies something went wrong, and nothing here did.
`ROADMAP.md` is work someone will do. `BUILD-LOG.md` is what happened in a
phase. These are properties of the system as it currently stands: measured
facts that constrain how later phases can be built and what the submission is
entitled to claim.

Each entry names what would change it. An observation that nothing could ever
change is a design decision and belongs in `IMPLEMENTATION-PLAN.md` §0 instead.

**Maintenance:** review at the close of every phase alongside the other four
docs. An observation that stops being true gets deleted, not amended — and if
it stopped being true because someone fixed it, that is an `ISSUES.md` entry.

Last updated: 2026-09-03, at the Phase 3 implementation checkpoint. Unless an
entry says otherwise, figures are measured on the four canonical
`runs/seed42/` artifacts using the no-key deterministic path.

---

## OBS-001 · The proposer is close to neutral; the policy engine carries the result

**Measured.** With the proposer held constant, policy moves 459 → 161 contacts,
104 → 23 false interventions and 62.3% → 56.5% value recovery. With policy held
constant, swapping the naive chaser for the deterministic ladder moves
161 → 157 contacts, 63 → 66 paid records and 56.5% → 57.8% value recovery — and
leaves false interventions at exactly 23. The ladder also spends 15 more
payment links (56 → 71) to get there.

**Why it matters.** ISS-029 records these numbers as proof the confound is
gone. The consequence is not recorded anywhere: **the four-arm table does not
support the claim "the agent recovers more money."** It supports "the policy
engine buys a 65% contact reduction and an 89% cut in disputed-invoice contacts
for 5.8 points of recovery, and the proposer is roughly neutral on top of
that."

This is the correct framing to carry into Phase 3, and it is a good position
rather than a weak one — the bar is now precisely measured (57.8% value at 157
contacts, 23 false interventions), so any model gain is legible instead of
confounded. But it means Phase 3 cannot justify itself on per-record recovery.
It has to earn its place on what the ladder structurally *cannot* do: reading
the free text (see OBS-002 and OBS-003) and the batch-level cluster insight
(spec §7b, ROADMAP P0 #11). Both are already P0. This observation is the
argument for why they, not recovery percentage, are the Phase 3 headline.

**What would change it.** A Phase 3 arm that beats 57.8% at ≤157 contacts, or —
more likely and more interesting — one that holds recovery flat while cutting
the residual harm categories below.

**Phase 3 checkpoint.** The structured proposer is now wired, but no Anthropic
key is configured and the canonical agent still uses the exact deterministic
per-record fallback. These numbers therefore remain the bar for the model, not
model performance, and must not be relabelled as an LLM result.

---

## OBS-002 · `HARDSHIP_CLAIMED` is modelled as harm and scored by nothing

**Measured.** The book carries three held-out flags: `DISPUTED` (18 records),
`HARDSHIP_CLAIMED` (12) and `ALREADY_PAID_UNRECONCILED` (10). The
false-intervention metric counts contacts against the first and third. It does
not count the second.

The simulation nonetheless models pressing these payers as actively harmful.
`adjudicator.PROFILES[Archetype.DISTRESSED]` carries `complaint=0.090` — 4.5×
its own `dispute_raised=0.020` — and the module comment is explicit: *"DISTRESSED
pays LESS when pressed and complains more. Pressure is counterproductive; time
and a human do better."*

Contacts landing on hardship records:

| Arm | Contacts | Distinct records |
|---|---:|---:|
| Baseline | 49 | 12 / 12 |
| Baseline + policy | 16 | 6 / 12 |
| Agent | 16 | 6 / 12 |

**Why it matters.** Two things, pulling in opposite directions.

It is an **unclaimed win**: policy already cuts hardship contact by 67% and
halves the number of distressed payers touched at all. That result is sitting
in the logs unreported.

It is also an **unmeasured harm**: a third of the held-out harm vocabulary does
not appear in the metric table, so "23 false interventions" understates total
harm on a definition the project itself chose. A judge who reads
`adjudicator.py` and then the metric table can ask why one modelled harm is
scored and another is not, and the honest answer today is that nobody decided.

Note also that the figure is **identical** between baseline + policy and agent
(16 across 6), which is OBS-001 showing up again in a third dimension.

**What would change it.** Either scoring it — a `harm-weighted contacts` row,
or a third false-intervention subtype — or an explicit written decision that
hardship contact is legitimate because the payer still owes the money and the
merchant is entitled to ask. Both are defensible. Silence is not, because the
flag exists and the behaviour model uses it.

Hardship is also the strongest Phase 3 case in the book: it is signalled in
prose (`corpus/payer_notes.yaml`, `corpus/email_replies.yaml` carry `HARDSHIP`
signals) and nowhere in the structured fields, so it is exactly the thing a
snapshot-reading ladder cannot catch and a text-reading model can.

---

## OBS-003 · False interventions have an information floor near 15, not zero

**Measured.** Splitting the agent's 23 false interventions by whether the
snapshot carries any signal at all:

| Flag | Signal in snapshot? | Records contacted (agent) | Suppression |
|---|---|---:|---:|
| `DISPUTED` | Yes — `state == DISPUTED` or `free_text.dispute_description` | 3 / 18 | 83% |
| `ALREADY_PAID_UNRECONCILED` | **No** — the ledger shows money outstanding | 8 / 10 | 20% |

**Why it matters.** The two numbers are not comparable and should never be read
as one. Where the agent has a signal it suppresses 83% of contacts; where it
has none it suppresses 20%, and that 20% is incidental — a by-product of
contacting less overall, not of detection.

This sets a floor. Under the current snapshot, no contacting arm can drive
false interventions to zero, because ~15 of them are against records whose only
distinguishing fact is held out by construction. Reporting "23" without this
split invites the question "why not zero?", and the answer is a ceiling, not a
failure.

It also means the residual 8 disputed contacts — not the 15 — are the real
Phase 3 target, and they are a small number. Phase 1 found 6 of 18 disputes are
prose-only; those are where the remaining headroom is.

**What would change it.** A reconciliation signal in the snapshot (a bank-feed
or settlement-status field) would make already-paid detectable and move the
floor. That is a real product feature, not a demo one, and belongs in
`ROADMAP.md` §2.2 rather than the seven days.

---

## OBS-004 · The terminal path is unexercised in both policy arms

**Measured.** Baseline makes 36 `STOP` decisions and writes off 19 records.
Both policy arms make **zero** `STOP` decisions and write off nothing: after
231 (agent) and 247 (baseline + policy) deferred vetoes, the 28-day horizon
ends with every unpaid record still mid-ladder.

**Why it matters.** The metric report already labels the zero write-offs as
horizon truncation (ISS-028), which covers the misreading risk. What is not
recorded is the coverage consequence: `STOP` → `EXHAUSTED` → write-off, and the
`high-value-escalation` rule that guards it, are **exercised only by an arm
that bypasses the policy engine**. The engine's own terminal behaviour has unit
tests and no end-to-end evidence.

This compounds with ISS-030. The threshold bug is fixed and 14 of 126 records
now clear ₹5,00,000, so the rule is reachable in principle — but no canonical
run reaches it, so the fix is verified by a regression test rather than by a
firing.

**What would change it.** A longer-horizon run (`--ticks` above 112) would
reach `STOP` and exercise the path. It would produce a non-canonical artifact,
which is why it has not been done — but it is cheap, and a single committed
`seed42-t224` run would convert "tested" into "demonstrated" for the entire
terminal path. Worth considering in Phase 6 if the fatigue sensitivity table
(ROADMAP P0 #18) is being produced anyway, since that is the same shape of
work.

---

## OBS-005 · Phase 3 unit economics, and what the cache does not do

**Measured.** The canonical agent run logs **472 `DECISION` rows** — one model
call each, before caching. Snapshots are ~1,118 bytes (~280 tokens).

**Estimate.** At `claude-opus-5` with adaptive thinking and
`output_config.effort: "medium"`, thinking tokens bill as output and dominate
the cost. A full agent run is realistically **$10–25**, with the spread driven
almost entirely by thinking-token volume rather than by input size. The batch
insight at `"high"` is one additional call and is negligible against that.

**The cache caveat.** `BUILD-LOG.md` "Carried forward" #2 records the mechanism;
the planning consequence is worth stating plainly. The snapshot contains `tick`,
`as_of` and `days_overdue`, so a SHA-256 over it changes on **every review of
every record**. The disk cache is therefore a *cross-run* accelerator and the
offline-demo mechanism — it is not an in-run one, and it cannot be. The first
full run pays full price, and so does any run whose snapshots shift.

**Phase 3 checkpoint.** The wrapper now performs 473 lookups on the canonical
agent run: 472 record decisions plus one aggregate call. With no key and no real
cache entries it reports 0 hits, 0 model calls and 473 fallbacks. A full-book
fake-transport test proves 100% hits and zero client calls on a second identical
run, but that is implementation evidence, not a seeded demo cache. ISS-033 keeps
the real cache/evaluation gate open.

**Why it matters.** Do not budget Phase 3 as though caching amortises within a
run. Assume full price per full run, and expect to want several — a schema
change, a prompt change, or any generator change invalidates the whole cache at
once.

**What would change it.** Nothing that should be done. Excluding the volatile
fields from the cache key would raise the hit rate and silently return a
proposal computed for a different day, which is worse than the cost.

---

## OBS-006 · The unverified-source path has no live example to render

**Measured.** `sources.py::unverified()` returns an empty list: both regulatory
sources were verified at the issuing body in Phase 2, and the P1 e-mandate
rules were never written because the mandate lane did not ship.

**Why it matters.** Invariant 7's visible enforcement mechanism is the caveat
chip an unverified rule renders with in the dashboard. Phase 5 will build that
chip, and there is nothing in the data that triggers it — so the code path
ships exercised only by unit fixtures, and the demo cannot show the mechanism
working on a real citation.

The function's own docstring already argues, correctly, that an empty list is a
truthful answer a hardcoded "none" is not. That reasoning is sound and this is
not a request to weaken it. It is a note that the *rendering* has no live case.

Related and lower stakes: `RuleSource.scope_caveat` **is** populated on all
three regulatory sources, including the load-bearing RBI one. That is the
honesty mechanism that does have live data, and it is the one to put on screen.

**What would change it.** Shipping the mandate lane (ROADMAP P1 #1) would
introduce ISS-006's unverified e-mandate source and give the chip a real
subject. Absent that, Phase 5 should render the scope caveats prominently and
treat the unverified chip as a tested-but-dormant path — and say so, rather
than implying the dashboard has been seen doing it.

---

## OBS-007 · `--arm both` now selects four arms

`cli.py` keeps `both` as the documented Phase 2 gate spelling while it now
expands to control, baseline, baseline + policy and agent. There is an inline
comment saying so and `all` is available as the honest synonym.

Harmless, and deliberately preserved so the gate command in
`IMPLEMENTATION-PLAN.md` keeps working. Noted only because "both" naming four
things is the kind of detail that reads as sloppiness to someone encountering
it cold in a demo, and the mitigation is to type `--arm all` on video.
