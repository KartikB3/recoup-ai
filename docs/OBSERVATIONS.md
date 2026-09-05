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

Last updated: 2026-09-03, at the Phase 5 close. Unless an entry says
otherwise, figures are measured on the four canonical `runs/seed42/`
artifacts, which use the no-key deterministic path. Figures for the
cost-tiered arm come from `runs/seed42-tiered/`, where the agent uses 77
real model proposals at first review and the deterministic ladder after.

---

## OBS-001 · The policy engine carries the result; the proposer trades recovery for harm

**Measured.** With the proposer held constant, policy moves 459 → 161 contacts,
104 → 23 false interventions and 62.3% → 56.5% value recovery. With policy held
constant, swapping the naive chaser for the deterministic ladder moves
161 → 137 contacts, 63 → 64 paid records and 56.54% → 56.72% value recovery — and
leaves false interventions at exactly 23. Most of that contact reduction is the
approved account-level suppression binding, not the per-record ladder:
`batch-cluster-suppression` fires 54 times.

**Why it matters.** ISS-029 records these numbers as proof the confound is
gone. The consequence is not recorded anywhere: **the four-arm table does not
support the claim "the agent recovers more money."** It supports "the policy
engine buys a 65% contact reduction and an 89% cut in disputed-invoice contacts
for 5.8 points of recovery, and the proposer is roughly neutral on top of
that."

This is the correct framing to carry into Phase 3, and it is a good position
rather than a weak one — the bar is now precisely measured (56.72% value at 137
contacts, 23 false interventions), so any model gain is legible instead of
confounded. But it means Phase 3 cannot justify itself on per-record recovery.
It has to earn its place on what the ladder structurally *cannot* do, and that
is **one thing, not two**: reading the free text (see OBS-002, and ISS-036 for
the result).

The batch-level cluster insight (spec §7b, ROADMAP P0 #11) was assumed to be the
second, and it is not. The deterministic fallback proposes the **identical**
group — `GRP-SURYODAYA`, the same nine invoice ids — because `parent_group_id`
is a structured field and grouping on it needs no prose at all. What the model
adds there is the quality of the *diagnosis*, not the detection: it names six
separate payer entities in different cities and reads their replies as one
account-level condition, where the fallback says only "correlated silence is
consistent with one account-level process event."

That is a real difference for a human reading the artifact, and it is not a
capability difference. The cluster mechanism is worth demonstrating — it now
binds, suppressing 54 duplicate contacts through a logged policy decision — but
it must be presented as *the policy engine acting on an account-level pattern*,
never as something only the model could find.

**What would change it.** A Phase 3 arm that beats 56.72% at ≤137 contacts, or —
more likely and more interesting — one that holds recovery flat while cutting
the residual harm categories below.

**Phase 3 result.** The bar held and the model did not clear it on recovery,
which is the outcome this observation predicted. With 77 real model proposals at
first review, `runs/seed42-tiered/` records 54.09% value recovery against the
ladder's 56.72% — the proposer *costs* 2.63 points. It buys 137 → 89 contacts
and 23 → 0 scored false interventions.

So the framing above is confirmed rather than overturned, with one correction:
the model's contribution is not "roughly neutral", it is a **deliberate trade of
recovery for harm**, of the same shape and smaller size than the trade the
policy engine already makes. The four canonical `runs/seed42/` numbers remain
deterministic-fallback numbers and must never be relabelled as an LLM result;
the model numbers live in `runs/seed42-tiered/` and are labelled as a
cost-tiered arm. Note also ISS-038: the recovery column cannot reward correct
escalation, so 54.09% is a floor on the model's real-world value, not a
measurement of it.

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

**Phase 3 evidence.** All 12 hardship records were seeded and scored. The ladder
contacts 12 of 12; the model contacts 5, so 58% suppression — much the weakest
of the three categories, against 100% for both scored ones. The five are reasoned
rather than missed. On `ASH-2026-0089` the model's stated ground is that *"the
payer has explicitly asked for a card link, so sending one addresses the named
obstacle rather than adding pressure."*

**Owner: Phase 6, ROADMAP P0 item 22.** Assigned at the Phase 3 close so it cannot become the thing nobody did.

That sharpens the open question instead of answering it. The model is drawing a
distinction the flag cannot express — hardship that needs breathing room versus
hardship where the payer has named the mechanism they want — and the project
still has not decided which of those counts as harm. Deciding it is now a
prerequisite for scoring the category, not merely an option.

Hardship is also the strongest Phase 3 case in the book: it is signalled in
prose (`corpus/payer_notes.yaml`, `corpus/email_replies.yaml` carry `HARDSHIP`
signals) and nowhere in the structured fields, so it is exactly the thing a
snapshot-reading ladder cannot catch and a text-reading model can.

---

## OBS-004 · `high-value-escalation` cannot fire, because balances decay faster than the ladder exhausts

**Measured.** The rule converts a `STOP` into `ESCALATE_HUMAN` when
`outstanding_paise` exceeds the ₹5,00,000 merchant threshold. It fires **zero**
times in every arm, on both the 112-tick canonical run and the 224-tick
sensitivity run — even though 14 of 126 records are billed above the threshold.

The reason is now measured rather than assumed. In `seed42-t224` the policy
baseline stops `ASH-2026-0045`, billed at ₹5,00,131.20 — above the threshold.
At the moment of that `STOP` its *outstanding* balance was **₹1,61,692.43**,
because the payer had already paid most of it. The rule correctly declined. A
receivable large enough to need human review before abandonment is, by
construction, one that attracts enough partial payment to fall under the
threshold before automation gives up on it.

**Why it matters.** This is the one policy rule with no end-to-end firing
anywhere, and ISS-044 shows a longer horizon does not fix it. It is guarded by a
regression test (ISS-030, after the ₹50 lakh digit-grouping bug) and by unit
tests, and that is all the evidence there is. Anything the submission says about
it must be phrased as "tested", never "demonstrated".

**What would change it.** Either a threshold set against `amount_paise` rather
than `outstanding_paise` — which would be wrong, since the question is how much
money is still at stake — or a book containing a large receivable that attracts
no partial payment at all. The second is a generator change and would be
honest; it is not worth doing inside the build window, and doing it to
manufacture a firing would be worse than the gap.

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

**Phase 3 measurement.** The estimate above was high at the top of its range.
Measured against a real balance, a record call at `effort: "medium"` costs about
**$0.021**, so a full 472-call arm is about **$10** rather than $25. Actual spend
was **$2.09** in total: one batch insight at roughly $0.45, and 77 record calls.
Measured inputs are 1,330 tokens per record call (841 system, ~454 snapshot) and
about 57,800 tokens for the whole opening book on the aggregate call.

Two things the numbers did not change. Caching is still cross-run only, for the
reason above. And the first full run still pays full price — which is precisely
why no full run was bought.

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
chip an unverified rule renders with in the dashboard. Phase 5 built that chip,
and there is nothing in the data that triggers it — so the code path ships
exercised only by a synthetic source fixture, and the demo cannot show the
mechanism working on a real citation.

The function's own docstring already argues, correctly, that an empty list is a
truthful answer a hardcoded "none" is not. That reasoning is sound and this is
not a request to weaken it. It is a note that the *rendering* has no live case.

Related and lower stakes: `RuleSource.scope_caveat` **is** populated on all
three regulatory sources, including the load-bearing RBI one. That is the
honesty mechanism that does have live data, and it is the one to put on screen.

**Phase 5 result.** `source_status` returns a visible *Unverified · exclude from
demo* state and an acceptance test pins it with a regulatory fixture. The
summary and timeline render the scope caveat carried by every live regulatory
source. On the default Netra timeline the RBI-hours veto therefore displays
both *Verified at issuing body* and the limiting fact that the circular governs
regulated-loan recovery rather than a merchant's own trade receivables.

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

## OBS-008 · Escalation is unrewarded, so the recovery column understates the reasoner

**Measured.** `ESCALATE_HUMAN` carries `ends_automation=True` and
`review_ticks=REVIEW_NEVER`, and moves a record to `HUMAN_QUEUE`. The model
proposes it for 49 of the 77 seeded records — Rs 1,01,38,277, about 40% of book
value — at first review. The simulation models no human collector, so no record
is ever recovered *because* it was escalated.

**Why it matters.** The reasoner's single most characteristic behaviour is
recognising a blocker that automated chasing cannot clear — a place-of-supply
error crediting GST to the wrong state, a vendor-master rebuild, a payer who has
already paid — and handing it to a person. In the metric table every one of
those scores as forgone recovery. The 2.63-point cost in `runs/seed42-tiered/`
is therefore a **floor on the model's value, not a measurement of it**, and the
gap is not small: it is whatever fraction of Rs 1.01 crore a human collector
would actually resolve.

This is why Phase 3 does not report a recovery beat, and why the plan's original
"beat the policy baseline on recovery" task was retired rather than failed. A
full model arm would have produced a number that looks like a verdict on the
reasoner and is really a verdict on the simulation's boundary. See ISS-038.

**What would change it.** A modelled human-resolution rate on `HUMAN_QUEUE` —
even a crude one, say a fixed probability of resolution within N ticks, stated as
an assumption — would let escalation earn recovery and make the comparison fair.
That is a simulation change, not a product change, and it is the single highest-
value thing an evaluation phase could add. It must be introduced as a *declared
assumption with a sensitivity range*, never as a silent constant, or it becomes a
dial that manufactures the result.

---

## OBS-009 · The link allocator works because the world is replayable, not because it forecasts

**Measured.** At `--live-budget 3` the allocator fills 3 of 3 units, on the
three largest of the 30 records that requested a payment link
(Rs 6,35,583 · Rs 5,44,133 · Rs 5,11,034). Perfect utilisation and a correct
ranking — and both come from a property the production version would not have.

**Why it matters.** Demand is *revealed*, not predicted: the arm is run once
with the simulated executor to see which records ask for a link, and the live
pass then funds the largest of those. That is exact here because the simulation
is deterministic and no decision reads the executor, so the rehearsal is the
same run. Against real payers there is no rehearsal. The general form is an
online problem — a value threshold that spends a unit when a request is good
enough, accepting that a better one may arrive later — and this build does not
solve it. ISS-040 records why the obvious alternative (rank the biggest
invoices at intake) is worse than doing nothing: on this book it funds zero
links.

Two further honest limits in the same area:

- **There is no calibrated recovery probability.** Expected recovery is
  `p × outstanding`, and with `p` taken as constant across requesting records
  the ranking reduces to amount outstanding. That is what the code does and
  what its docstring says. "Ranked by expected recovery" without that sentence
  would imply a model that does not exist.
- **One real link per invoice.** A defensible rule — a second link to one payer
  is worth less than a first to another — but it is a judgement, not a result.

**What would change it.** The ledger already records a confidence on every
proposal and what actually happened, which is a calibration curve waiting to be
fitted (ROADMAP §2.1). Fitting it turns `p` into a measured quantity and turns
the threshold rule into something with a defensible cutoff. Neither is seven-day
work, and neither is needed for the claim the submission actually makes, which
is about allocating a capped resource rather than about forecasting.

---

## OBS-010 · A live run is mostly simulated, and the audit log is where that is visible

**Measured.** A 112-tick live run at `--live-budget 3` executes 52 payment
links and 337 other actions. Three rows carry `executor: LIVE`. Everything else
— every reminder, every phone follow-up, and 49 of the 52 links — is
`SIMULATED`.

**Why it matters.** This is the shape of the Razorpay integration boundary the
README promises, and the number is small on purpose: the cap is 30 for the
whole account (ISS-001) and the demo needs the loop to close once, not at
volume. The risk is not the ratio, it is describing it loosely. "The agent
creates Razorpay payment links" is true; "the agent's contacts are real" is
not, and the two are one careless sentence apart.

The mechanism that keeps it honest is that `LIVE` is a property of the action
rather than of the run (ISS-041), so the audit log answers the question exactly:
three rows, three `plink_` references, each traceable to an object in the
Razorpay dashboard. `runs/<id>/<arm>/link-allocation.json` states the same thing
from the other side — what the budget was, who requested one, who got funded.

**What would change it.** Nothing available. UPI links are unsupported in test
mode (ISS-002), error-simulation cards are browser-bound (ISS-003), and Recoup
sends no email, SMS or voice in any mode, so reminders have no live counterpart
to acquire. A raised cap would change the ratio and not the boundary — and
ISS-001 explains why the cap was deliberately not raised.

---
## OBS-011 · The canonical horizon truncates the patient arms, and the deficit is mostly that

**Measured.** The same four arms, deterministic proposer, at two horizons:

| Arm | 112 ticks (28d) | 224 ticks (56d) |
|---|---|---|
| control | 49.25% · 0 contacts | 58.47% · 0 |
| baseline | 62.34% · 459 | 66.99% · 459 |
| baseline + policy | 56.54% · 161 | 65.82% · 233 |
| agent | 56.72% · 137 | **66.50% · 199** |

The agent trails naive chasing by **5.62 points** at 28 days and by **0.49
points** at 56 days, using roughly a third to a half of the contacts either way.

**Why it matters.** The headline four-arm table costs the policy arms about four
points of recovery, and ISS-028 already labels the zero write-offs as horizon
truncation. What the 224-tick run adds is that the *recovery* gap is largely the
same artifact: the policy arms defer rather than chase, and a 28-day window
closes before the deferral pays. The strategy is patience, and the canonical
horizon cuts it off mid-strategy.

This is a genuine finding and also a trap. **The canonical horizon stays 112
ticks** — it is a §0 locked decision, and choosing the horizon that flatters
your own arm is exactly what a careful judge looks for. Reported as a
sensitivity result beside the canonical table it is strong; promoted to the
headline it reads as horizon shopping and costs more than it gains.

Note the other direction too: false interventions rise with horizon (baseline
104, both policy arms 31 at 224 ticks against 23 for the agent at 112). Longer
runs recover more *and* do more harm. There is no horizon at which every number
improves.

**What would change it.** Nothing that should be done. A canonical horizon is a
modelling choice that has to be fixed before the results are seen, and this one
was.

---

## OBS-012 · A rehearsal audit log is indistinguishable from a confirmed one

**Measured.** `recoup run --executor live --live-budget 3` without `--confirm`
runs against `FakePaymentLinkClient` and produces three audit rows carrying
`executor: LIVE` with `external_ref` values like `plink_cd03eff60147e0`. A
`--confirm` run produces rows of exactly the same shape. Nothing in
`audit.jsonl`, `summary.json` or `final.json` records which of the two happened.

**Why it happens, and why it is not simply a bug.** `LiveRazorpayExecutor`
stamps `ExecutorKind.LIVE` when `client.create()` returns a usable `plink_` id.
That is the correct rule — ISS-041 is precisely the argument that `LIVE` must
mean "a Razorpay object exists for this row" rather than being a per-run or
per-executor property. The fake client satisfies the `PaymentLinkClient`
protocol faithfully, which is what makes the whole live path rehearsable for
free; the executor cannot tell the two apart without breaking the seam that
makes it testable.

**Why it matters.** The audit log is the artifact this project asks to be
trusted, and the README invites a reader to run the rehearsal because it costs
nothing. That reader ends up holding a log which asserts three real Razorpay
objects that do not exist. The claim "the audit log answers which rows were real,
exactly" is true of a confirmed run and false of a rehearsal, and the README now
says so rather than relying on the operator remembering which command they ran.

**What would change it.** Recording the confirm flag in `summary.json` as a
`live_mode: rehearsal | confirmed` field. It does not touch `ExecutorKind`, so
ISS-041 stays intact.

It is also smaller than it first appears, and an earlier draft of this entry
deferred it on a rationale that was simply wrong — that it would rewrite the
summary artifact of every committed run. It would not. `RunResult` gains one
optional field which `summarise` emits only when it is set, so every committed
simulated run keeps its bytes and the byte-identical reproduction check still
passes untouched. No committed artifact changes at all, because no live run is
committed. The real cost is one dataclass field, one line on the live path, one
line in `summarise`, and a test.

Worth doing before the video rather than after, because the live beat is
precisely where a row stamped `LIVE` has to mean something.

---
