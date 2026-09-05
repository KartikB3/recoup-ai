# Recoup

**An autonomous B2B receivables recovery agent. Every customer contact and every
money action passes a deterministic, source-carrying policy engine that can veto
it — and the whole system is measured against a naive chaser *and* a do-nothing
control on the same seeded batch.**

Razorpay Buildathon · Track 03: AI Revenue Recovery

---

## The number most collection tools do not report

Chase 126 overdue B2B invoices on a fixed schedule and you recover **62.3%** of
Rs 2,52,97,406. That is the number that goes on the slide.

Do nothing at all and you recover **49.2%**. B2B customers pay late, not never.

So the fixed-schedule ladder is not worth 62 points. It is worth 13 — and it
buys them with **459 customer contacts, 104 of which land on someone who has
already paid or who has an open dispute on the invoice.**

Recoup prices that trade honestly, and then improves it.

## Results

Same seeded batch, ledger, virtual clock and simulated world across all four
arms. The control always waits. The naive chaser contacts every three days until
paid or five attempts. **"Chaser + policy" runs that identical proposer through
the policy engine**, which isolates what policy enforcement is worth. Recoup uses
a different proposer behind the same engine, which isolates what the proposer is
worth.

| Metric | Control<br>(do nothing) | Naive chaser | Chaser<br>+ policy | **Recoup** |
|---|---:|---:|---:|---:|
| Recovery rate (value) | 49.2% | **62.3%** | 56.5% | 56.7% |
| Recovery rate (records) | 42.9% | **55.6%** | 50.0% | 50.8% |
| Records paid | 54 | **70** | 63 | 64 |
| Rs recovered | 1,24,60,148 | **1,57,71,226** | 1,43,03,667 | 1,43,47,473 |
| Customer contacts | **0** | 459 | 161 | 137 |
| Payment links sent | **0** | 225 | 56 | 61 |
| **Wrong contacts** | **0** | 104 | 23 | 23 |
| — on disputed invoices | **0** | 76 | 8 | 8 |
| — on already-paid invoices | **0** | 28 | 15 | 15 |
| Policy vetoes | bypassed | bypassed | 247 merchant / 0 regulatory | 266 merchant / 6 regulatory |
| Policy modifications | bypassed | bypassed | 16 | 17 |
| Unresolved / written off | 72 / 0 | 37 / 19 | 63 / 0 | 62 / 0 |

**Recoup gives up 5.6 recovery points and takes 70% fewer customer contacts and
78% fewer wrong ones.** That is the trade, stated plainly. A finance team that
has to answer for its dunning behaviour is buying the fourth column, not the
second.

*"Wrong contacts" are scored against held-out ground truth the agent never sees:
40 of the 126 records carry a hidden `DISPUTED` (18), `HARDSHIP_CLAIMED` (12) or
`ALREADY_PAID_UNRECONCILED` (10) flag. No proposer can read them. They exist only
to score harm — which is why the batch is simulated.*

*The scored total covers 28 of those 40. **Hardship is reported, not scored**,
and deliberately so. Of the three hardship payers the agent contacts, **two asked
for a channel they could actually use** — one cannot add a beneficiary inside a
week, one has a per-beneficiary transfer limit below the invoice value — and the
third confirmed the transfer was already queued in their banking portal. Scoring
the flag would count sending a payment link to someone who asked for one as
harm. The rule the agent is held to instead — contact is service when the
obstacle is operational, pressure when a commercial question is open that it has
no authority to answer — is written out in [`docs/ISSUES.md`](docs/ISSUES.md)
ISS-048, with the cases that discriminate it.*

## Verify every number above, in three commands

No credentials, no network, no spend.

```bash
uv sync --extra dev

uv run recoup generate --seed 42 --count 126        # the book: fixed SHA-256, same bytes everywhere
uv run recoup run --seed 42 --arm all --no-model    # the four arms above, ~2 min
uv run recoup metrics seed42                        # recompute the table from stored artifacts
```

Then the claim that matters:

```bash
uv run recoup replay seed42/agent
```

That rebuilds every invoice's final state from the append-only audit log **and
no other input**, then diffs it against the ledger the run actually produced.
806 rows, hash chain verified, replay matches the ledger. It is an enforced
acceptance test, not a README assertion.

```bash
uv run recoup dashboard                             # portfolio, payer timeline, raw audit
```

---

## The thing a rules engine cannot do

Some invoices are unpayable for reasons that appear only in prose. One in this
batch is 25 days overdue and the ladder wants to send a reminder — but the payer
has already explained that the place of supply on the invoice puts the GST credit
in the wrong state, so their accounts team physically cannot process it. No
reminder ever fixes that. It is a document error and it needs a person.

Recoup sends the record to Claude, which reads the free text and routes it to a
human. The proposer receives a **snapshot** — never the underlying invoice — so
neither the model nor the fallback can see the held-out flags.

Model calls are the expensive tier, so they are spent where they change the
outcome: the model triages at first review and the deterministic ladder follows
through.

| | Chaser + policy | Recoup, rules only | **Recoup, model triage** |
|---|---:|---:|---:|
| Recovery rate | 56.5% | 56.7% | 54.1% |
| Customer contacts | 161 | 137 | **89** |
| Wrong contacts | 23 | 23 | **0** |

**Wrong contacts fall to zero, for 2.6 recovery points.** Reproduce it from 77
committed real model proposals, with no key and no spend:

```bash
uv run recoup run --seed 42 --arm all --cache-only --run-id seed42-tiered
```

Two honest caveats on that column. The recovery metric scores an escalation to a
human as money not collected, because the simulation contains no human collector
— so 54.1% is a floor on the model's value, not an estimate of it. And the
deterministic arm is not a strawman: it is the same policy engine, precisely
measured, which is what makes 23 → 0 legible instead of confounded.

---

## Architecture

```
[1] Generator  →  [2] Ledger + Virtual Clock  →  [3] Reasoner (Claude or deterministic)
                                                       ↓ proposes
                                              [4] Policy Engine
                                                       ↓ approves / modifies / vetoes
                                              [5] Executor  →  Razorpay test API
                                                       ↓
                                              [6] Audit Log  →  Dashboard + Metrics
```

Two seams carry the design:

**`Proposer`** receives a ground-truth-free snapshot and returns a proposal.
Claude and the deterministic fallback implement the same protocol, so the
complete system runs with no API key at all.

**`PolicyGate`** receives the full record and ledger and can approve, reduce or
veto. Policy logic never moves into the reasoner.

The action space is a closed enum — `WAIT`, `SOFT_REMINDER`, `PAYMENT_LINK`,
`PHONE_FOLLOWUP`, `ESCALATE_HUMAN`, `STOP`. The model cannot invent a seventh
action, and **it never supplies a money amount, a date calculation, or a final
decision.** If a feature cannot survive that sentence, it is not in the build.

All money is integer paise. All dates are virtual — no wall clock reaches the
domain, ledger, policy or reasoner code.

## Compliance is a data structure, not a prompt

Eleven rules run in a fixed, tested order. Each carries its citation, its
`verified` flag and the caveat on its scope, and each is labelled **regulatory**
or **merchant-configured** — never confused. Unverified sources render with a
visible warning. No cap on retry attempts is claimed to be regulatory, because no
verified source for one was found.

Six contacts in the canonical run were vetoed under `rbi-contact-hours` for
landing outside the 08:00–19:00 window, each with the circular on screen. That
circular governs lending recovery by regulated entities, so Recoup **adopts**
the window as a standard rather than claiming to be legally bound by it — and
that caveat travels with the citation into the UI, not just into this document.

Full mapping: [`docs/POLICY-SOURCES.md`](docs/POLICY-SOURCES.md).

## Account-level decisions bind, and are logged

The aggregate path reads the whole opening book as the same ground-truth-free
snapshots and identifies nine invoices across six companies under one parent
group as correlated silence from a single account event. The policy engine
independently re-checks every invoice ID, the complete group scope and the
minimum payer breadth before approving anything.

Adjudicating and applying are separate: `adjudicate_batch` decides whether a
recommendation is *allowed*; `arm_batch_suppression` is the runner asking for it
to be *applied*. A caller cannot apply what the engine refused. Once armed, the
first contact against the group becomes one consolidated `ESCALATE_HUMAN` and
every later one is vetoed — **54 logged decisions carrying a rule id and a
reason, not 54 silent skips.**

## Knowing when to stop

Over 56 virtual days the naive chaser writes off 15 invoices; Recoup, on the
identical policy engine, stops on 3.

```bash
uv run recoup run --seed 42 --arm all --no-model --ticks 224 --run-id seed42-t224
```

**The canonical horizon is 28 days and was fixed before any of these results
existed.** The longer run is a sensitivity check, not a headline — Recoup scores
better at 56 days, which is exactly why it is not the number in the table above.

---

## What is real, and what is simulated

> The batch runs against a deterministic simulation harness which is **the system
> of record**. A bounded subset of interventions executes as **real Razorpay
> test-mode Payment Links**, closing the loop through live webhooks. The scarcity
> of that budget is modelled as a constraint the agent must allocate.

**Real:** Standard Payment Links API, server-side, test mode · callback URL with
`razorpay_signature` verification · `payment_link.paid` webhooks, reconciled back
into the ledger as ordinary append-only outcome rows.

**Precisely how much:** only payment links, and only funded ones. A 112-tick run
at `--live-budget 3` executes 61 payment links and 153 other actions, of which
**3 rows carry `executor: LIVE`**. Reminders and phone follow-ups have no live
counterpart in any mode — Recoup sends no email, no SMS and places no calls — so
`LIVE` is a property of the individual action rather than of the run.

One caveat, stated because the audit log is the thing this project asks to be
trusted. **A rehearsal stamps that same `LIVE` label.** The fake client stands in
for the real one and returns a deterministic `plink_…` id, so the executor
genuinely cannot tell them apart. A rehearsal log is therefore not evidence that
a Razorpay object exists — only a `--confirm` run's is, and those ids are the
ones checkable in the Razorpay dashboard. The run says which: `summary.json`
carries `live_mode: rehearsal | confirmed`, written by the only component that
knows. The rows still do not, deliberately, and that trade is argued in
[`docs/ISSUES.md`](docs/ISSUES.md) ISS-049.

**Simulated, and why:** everything else, because test mode closes the doors.
Payment Links cap at 30 per business; UPI Payment Links are unsupported in test
mode; error-simulation cards need a mock bank page and cannot be driven
headlessly; Recurring Payments S2S needs account activation; subscription retry
is untestable. Each is documented with its evidence in
[`docs/ISSUES.md`](docs/ISSUES.md).

Recoup never touches live mode: the client refuses any key not prefixed
`rzp_test_`.

### Running the live loop

The whole path runs against a fake client unless `--confirm` is passed, so
allocation, the session index, audit rows and reconciliation can be rehearsed
without creating a single real object.

```bash
uv run recoup webhook                              # terminal 1
cloudflared tunnel --url http://localhost:8000     # terminal 2 — set RAZORPAY_CALLBACK_BASE_URL

# rehearsal: real code path, fake client, zero links
uv run recoup run --seed 42 --arm agent --ticks 16 --cache-only \
                  --executor live --live-budget 3 --run-id live-rehearsal

# the real thing
uv run recoup run --seed 42 --arm agent --ticks 16 --cache-only \
                  --executor live --live-budget 3 --run-id live-demo --confirm
```

Use a short `--ticks`. Over the full horizon the simulated payer settles every
funded record before a human could pay it, and a webhook for an already-`PAID`
invoice is correctly refused. A `--confirm` run checks this **before creating
anything** and refuses outright if no funded record would still be open, because
the 30 links are not recoverable. It also refuses if the callback URL is unset.

Each retry needs a fresh `--run-id`: link reference ids are deterministic in
`(run_id, invoice_id, tick)` and unique per account. The receiver refuses every
delivery it cannot verify, refuses to write to the canonical runs at all, and is
idempotent on the Razorpay payment id.

`recoup reconcile <payload.json>` applies a saved delivery offline.

**Status:** the live slice is built and verified end to end against a fake client
— `CONTACTED → PAID`, replay clean. The one round trip through the real Razorpay
API has not been recorded yet, and nothing here claims otherwise.

---

## Known limitations

- **It is a simulation.** Deliberately: wrong contacts cannot be measured on real
  data, because nobody labels which invoices were already paid. The held-out
  ground truth is what makes the harm metric possible.
- **The recovery metric cannot reward correct escalation.** Routing an invoice to
  a human scores as money not collected. The recovery column understates the
  agent and is reported that way rather than quietly benefited from.
- **Already-paid-but-unreconciled invoices are invisible to the ledger by
  construction.** The model catches them by reading the customer's own words; a
  real deployment would want a bank feed.
- **Model output covers first-review triage**, 77 committed proposals. The
  full-book model arm was not bought, because the recovery column would score it
  as a verdict on the simulation rather than on the reasoner.

---

## Which command reproduces which run

`data/llm_cache/` holds **real committed model output** — 77 record proposals and
one batch insight. It is read whether or not `ANTHROPIC_API_KEY` is set, so the
flag decides which committed run you get:

| Command | Reproduces | Model output |
|---|---|---|
| `recoup run --seed 42 --arm all --no-model` | `runs/seed42/` — the deterministic four arms | none: no cache reads, no API calls |
| `recoup run --seed 42 --arm all --cache-only --run-id seed42-tiered` | `runs/seed42-tiered/` — the model-triage arm | the 77 committed proposals, replayed from disk |

Both are byte-identical to what is committed and **neither can spend money**.
Only successful validated model output is ever cached; errors, refusals,
truncation and missing credentials fall back deterministically and are never
cached as if they came from the model.

277 tests, all offline. No network on any test path.

## Repository map

| Path | What lives there |
|---|---|
| `src/recoup/domain/` | Frozen data contracts. All money is `int` paise; all dates are virtual |
| `src/recoup/generator/` | Seeded batch generator and the free-text corpus the model reads |
| `src/recoup/ledger/` | Virtual clock, state machine, seeded outcome adjudication |
| `src/recoup/policy/` | **The policy engine** — rules, ordering, citations |
| `src/recoup/reasoner/` | Structured Claude proposer, validated cache, aggregate insight, deterministic fallbacks |
| `src/recoup/executor/` | Simulated and live execution, scarce-budget allocation, signature verification, reconciliation |
| `webhook/` | FastAPI receiver: verified `payment_link.paid` → ledger |
| `src/recoup/audit/` | Append-only log and its replay acceptance test |
| `src/recoup/baseline/` | The naive chaser the agent is measured against |
| `src/recoup/runner/` | The tick loop — the only orchestrator |
| `dashboard/` | Portfolio summary, payer timeline, raw audit |

## Documentation

| Doc | What it is for |
|---|---|
| [`docs/POLICY-SOURCES.md`](docs/POLICY-SOURCES.md) | Every rule mapped to its citation and verification status |
| [`docs/ISSUES.md`](docs/ISSUES.md) | Obstacles, dead ends and their design consequences |
| [`docs/OBSERVATIONS.md`](docs/OBSERVATIONS.md) | Measured facts that are true and unresolved by design |
| [`docs/IMPLEMENTATION-PLAN.md`](docs/IMPLEMENTATION-PLAN.md) | Build plan, contracts and risk register |
| [`docs/BUILD-LOG.md`](docs/BUILD-LOG.md) | What was built, when, and why |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | What is left, and what Recoup could become |
| [`docs/SUBMISSION.md`](docs/SUBMISSION.md) | Drafted answers to the buildathon form |
| `docs/SEED-DISTRIBUTION.md` | The generator's distribution, and how the fatigue constants were calibrated |

## Out of scope, permanently

Real money · real customers · real PII · anything where the model decides a
number · anything requiring Razorpay account feature activation.
