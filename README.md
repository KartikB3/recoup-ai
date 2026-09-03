# Recoup

**An autonomous receivables recovery agent where every money action and customer contact passes a deterministic, source-carrying policy engine that can veto it — measured against both a naive chaser and a do-nothing control on the same seeded batch.**

Razorpay Buildathon · Track 03: AI Revenue Recovery · solo build.

> ⚠️ **Status.** Phases 0–3 and Phase 5 are complete: the structured proposer, validated
> disk cache, model-failure circuit breaker and policy-approved batch insight
> are wired, the cache holds 77 real model proposals and one real batch
> insight, and an empty `ANTHROPIC_API_KEY` still reproduces the four-arm
> Phase 2 numbers exactly. `v0.1-submittable` remains the untouched
> deterministic floor. The three-view dashboard reads only local run artifacts
> and keeps the real-model result visibly separate as a fifth arm.
>
> **Phase 4's live slice is built and verified offline. The one round trip
> through the real Razorpay API has not been run yet** — see *Closing the live
> loop* below for exactly what is and is not proven, and how to finish it.

---

## The Razorpay integration boundary

Stated up front, because it is a design decision and not an apology.

> The batch runs against a deterministic simulation harness which is **the system of record**. A bounded subset of interventions executes as **real Razorpay test-mode Payment Links**, closing the loop through live webhooks. The scarcity of that budget is modelled as a real constraint the agent must allocate.

**What is real:** Standard Payment Links API, server-side, test mode · callback URL with `razorpay_signature` verification · webhooks for payment events, reconciled back into the ledger.

**Precisely how much of a live run is real:** only the payment links, and only the funded ones. A 112-tick run at `--live-budget 3` executes 52 payment links and 337 other actions, of which **3 rows carry `executor: LIVE`**. Reminders and phone follow-ups have no live counterpart in any mode — Recoup sends no email, no SMS and places no calls — so `LIVE` is a property of the individual action rather than of the run, and the audit log answers "which rows were real?" exactly. See [`docs/OBSERVATIONS.md`](docs/OBSERVATIONS.md) OBS-010.

**What is simulated, and why:** everything else — because test mode closes the doors. Payment Links are capped at 30 per business; UPI Payment Links are unsupported in test mode; error-simulation cards require clicking through a mock bank page and cannot be driven headlessly; Recurring Payments S2S needs account activation; subscription retry is untestable (3-day token expiry, and halted subscriptions issue an invoice instead of charging).

Each of those is documented with its evidence and its design consequence in **[`docs/ISSUES.md`](docs/ISSUES.md)**.

---

## Four-way comparison: policy value and proposer value

Same seeded batch, ledger, clock and simulated world. Control always waits. The
baseline contacts every three days until paid or five attempts. **Baseline +
policy runs that exact same proposer through the policy engine**, so it isolates
what policy enforcement buys. The agent uses a different proposer behind the
same policy engine, isolating proposer value.

| Metric | Control | Baseline | Baseline + policy | Agent |
|---|---:|---:|---:|---:|
| Recovery rate (value) | 49.3% | **62.3%** | 56.5% | 57.8% |
| Recovery rate (records) | 42.9% | **55.6%** | 50.0% | 52.4% |
| Records paid | 54 | **70** | 63 | 66 |
| Rs recovered | Rs 1,24,60,148.75 | **Rs 1,57,71,226.15** | Rs 1,43,03,667.23 | Rs 1,46,10,185.33 |
| Contacts made | **0** | 459 | 161 | 157 |
| Payment links sent | **0** | 225 | 56 | 71 |
| **False interventions** | **0** | 104 | 23 | 23 |
| - disputed invoices | **0** | 76 | 8 | 8 |
| - already paid / unreconciled | **0** | 28 | 15 | 15 |
| Policy vetoes | bypassed | bypassed | 247 merchant / 0 regulatory | 223 merchant / 8 regulatory |
| Policy modifications | bypassed | bypassed | 16 | 16 |
| Unresolved / written off | 72 / 0 | 37 / 19 | 63 / 0 | 60 / 0 |

Policy alone cuts the naive ladder's contacts by **64.9%** and false
interventions by **77.9%**, at a 5.8-point value-recovery cost. With policy held
constant, the agent proposer adds 3 paid records and 1.2 recovery points while
using four fewer contacts. Its disputed-invoice contacts fall **76 → 8**; the
remaining 15 already-paid/unreconciled contacts are not detectable from its
snapshot.

The zero write-offs in both policy-enabled arms are **28-day horizon
truncation**: deferred contacts keep them mid-ladder and neither proposes STOP.
The rule table labels policy bypasses, disabled configuration, defensive guards
and unreachable Phase 2 proposal shapes separately in
[`runs/seed42/metrics.md`](runs/seed42/metrics.md).

## The batch-level insight

The aggregate path reads the complete opening book as the same ground-truth-free
snapshots used per record. On the offline canonical run it identifies all nine
open invoices under `GRP-SURYODAYA` as correlated silence consistent with one
account-level process event. The deterministic policy engine independently
checks every ID, the complete group scope and minimum payer breadth before
approving one consolidated relationship escalation.

The full proposal and source-carrying verdict are committed in
[`runs/seed42/agent/batch-insight.json`](runs/seed42/agent/batch-insight.json).
It truthfully records `applied_to_ledger: false`: Phase 6 is where the approved
suppression is applied and rendered, so the Phase 3 artifact does not pretend
to have changed the four-arm metrics.

---

## Why not just a rules engine?

The Phase 2 tag deliberately uses a deterministic fallback so the complete
system works with no key. Phase 3 adds a structured-output Claude proposer to
read payer notes, replies, dispute reasons and promise language. Model output is
cacheable but never authoritative: every proposal still passes the deterministic
policy engine. **The model never supplies a money amount, a date calculation, or
a final decision.**

If a feature cannot survive that sentence, it is not in the build.

---

## Architecture

```
[1] Generator  →  [2] Ledger + Virtual Clock  →  [3] LLM Reasoner
                                                       ↓ proposes
                                              [4] Policy Engine
                                                       ↓ approves / modifies / vetoes
                                              [5] Executor  →  Razorpay test API
                                                       ↓
                                              [6] Audit Log  →  Dashboard + Metrics
```

The ledger is the system of record, not Razorpay. The audit log is append-only, and **any single invoice's complete history can be reconstructed from the log alone, with no other state.** That is an enforced acceptance test, not an aspiration.

---

## Quickstart

```bash
uv sync                                   # or: pip install -e ".[dev]"
cp .env.example .env                      # fill in test keys as needed

recoup generate --seed 42 --count 126     # Phase 1, published seed-42 book
recoup run --seed 42 --arm all --no-model # reproduces runs/seed42 exactly
recoup metrics seed42                     # recompute from stored artifacts
recoup dashboard                          # offline; canonical seed42 + tiered fifth arm
```

`recoup check-razorpay` creates one test-mode Payment Link to confirm credentials. It costs one unit of the 30-link budget.

### Which command reproduces which run

`data/llm_cache/` holds **real committed model output** — 77 record proposals
and one batch insight. It is read whether or not `ANTHROPIC_API_KEY` is set, so
the flag you pass decides which of the two committed runs you get (ISS-043):

| Command | Reproduces | Model output |
|---|---|---|
| `recoup run --seed 42 --arm all --no-model` | `runs/seed42/` — the deterministic four arms | none: no cache reads, no API calls |
| `recoup run --seed 42 --arm all --cache-only --run-id seed42-tiered` | `runs/seed42-tiered/` — the cost-tiered arm | the 77 committed proposals, replayed from disk |

Both are byte-identical to what is committed, and **neither can spend money**.
Omit both flags only when you intend to buy new model output; without
`--cache-only` a configured key bills for every uncached record (ISS-035).

Only successful validated model outputs are ever written under
`data/llm_cache/`; errors, refusals, truncation and missing credentials use the
deterministic fallback and are never cached as if they came from the model.

### Dashboard

`recoup dashboard [RUN_ID] --port 8501` launches three views entirely from
`runs/<id>/`; it never constructs a model or Razorpay client.

- **Portfolio summary:** all four canonical arms remain side by side. When a
  sibling `<id>-tiered` artifact exists, its real-model agent appears as a
  labelled fifth column rather than replacing the deterministic agent. Losses,
  bypassed policy and meaningful zeroes stay visible.
- **Payer timeline:** selected by payer name, then invoice. The canonical
  opening story is Netra Optics & Lenses: six `WAIT` decisions followed by a
  veto under the verified RBI-hours source, with the circular's scope caveat on
  screen.
- **Raw audit:** filterable over the actual `audit.jsonl`, with exact-row JSON
  inspection and a filtered JSONL download.

The default is `seed42` when it exists, even if `seed42-tiered` was written
later, because that is the recoverable deterministic floor the fifth arm must
sit beside. Pass another run id to inspect a rehearsal or reconciled run.

---

## Closing the live loop

The scarce-budget allocation, the live executor, the signature verification and
the ledger reconciliation are built and tested. **The whole path runs against a
fake client unless you pass `--confirm`**, so all of it can be rehearsed without
spending a single one of the 30 test-mode Payment Links (ISS-001, still at 1 of
30 consumed).

```bash
# Rehearse everything. Zero network, zero links, real code path.
recoup run --seed 42 --arm agent --ticks 24 --cache-only \
           --executor live --live-budget 3 --run-id live-rehearsal
```

That prints the links it would create, each labelled **payable** or **settled**:

```
live links: 3 created of a 3 budget, allocated across 22 records that requested one.
  payable  ASH-2026-0011  tick 0   closed CONTACTED  plink_...  https://rzp.io/i/...
  payable  ASH-2026-0035  tick 0   closed CONTACTED  plink_...  https://rzp.io/i/...
  settled  ASH-2026-0051  tick 12  closed PAID       plink_...  https://rzp.io/i/...
```

**Use a short `--ticks`.** Over the full 112-tick horizon the simulated payer
settles every funded record before a human could pay it, and a webhook for an
already-`PAID` invoice is refused — correctly, because the rupees are already in
the ledger. At 24 ticks two of the three funded links are still payable. This is
[ISS-039](docs/ISSUES.md), and it is the reason the CLI labels them.

You do not have to remember that. A `--confirm` run checks it **before creating
anything** and refuses outright if no funded record would still be open, because
the links are capped at 30 for the account and are not recoverable. It also
refuses if `RAZORPAY_CALLBACK_BASE_URL` is unset or still the placeholder, which
would otherwise send the payer's browser nowhere after they paid.

To do it for real:

```bash
recoup webhook                                    # terminal 1
cloudflared tunnel --url http://localhost:8000    # terminal 2, note the URL
```

Set `RAZORPAY_CALLBACK_BASE_URL` to that URL, add a webhook in the Razorpay
dashboard for `payment_link.paid` pointing at `<tunnel>/razorpay/webhook`, and
put the secret you choose there into `RAZORPAY_WEBHOOK_SECRET`. Then:

```bash
recoup run --seed 42 --arm agent --ticks 24 --cache-only \
           --executor live --live-budget 3 --run-id live-demo --confirm
```

Open a **payable** link, pay it with any test card, and the receiver moves the
record to `PAID`, appends the outcome row and marks the link settled. Verify:

```bash
recoup replay live-demo/agent      # the log must still reproduce the ledger
```

`recoup reconcile <payload.json>` applies a saved `payment_link.paid` delivery
offline — for a webhook that arrived while the tunnel was down, or to rehearse
the reconciliation without spending anything.

Two operational notes. A reconciliation moves recovery, so regenerate the run's
metric table with `recoup metrics <id>` afterwards — it is what the dashboard
reads. And a retried `--confirm` run needs a **fresh `--run-id`**: payment-link
reference ids are deterministic in `(run_id, invoice_id, tick)` and unique per
Razorpay account, so a second attempt under the same id collides on every create
and produces nothing. No budget is burned when that happens.

The receiver refuses every delivery it cannot verify, refuses to write to
`runs/seed42/` or `runs/seed42-tiered/` at all, and is idempotent: the Razorpay
payment id is recorded in the outcome row, so a redelivery changes nothing.

---

## Repository map

| Path | What lives there |
|---|---|
| `src/recoup/domain/` | Frozen data contracts. All money is `int` paise; all dates are virtual. |
| `src/recoup/generator/` | Seeded batch generator + the free-text corpus the LLM actually reads |
| `src/recoup/ledger/` | Virtual clock, state machine, seeded outcome adjudication |
| `src/recoup/policy/` | **The policy engine.** Rules, ordering, and their citations |
| `src/recoup/reasoner/` | Structured Claude proposer, validated committed cache, aggregate insight, deterministic fallbacks |
| `src/recoup/executor/` | Simulated and live-Razorpay execution, scarce-budget allocation, signature verification, payment reconciliation |
| `webhook/` | FastAPI receiver: verified `payment_link.paid` → ledger |
| `src/recoup/audit/` | Append-only log and its replay acceptance test |
| `src/recoup/baseline/` | The naive chaser the agent is measured against |
| `src/recoup/runner/` | The tick loop — the only orchestrator |
| `dashboard/` | Batch summary, invoice timeline, raw audit view |
| `docs/` | Plan, build log, issues, roadmap, seed distribution, policy sources |

---

## Documentation

| Doc | What it is for |
|---|---|
| [`docs/IMPLEMENTATION-PLAN.md`](docs/IMPLEMENTATION-PLAN.md) | The phased build plan, contracts, and risk register |
| [`docs/BUILD-LOG.md`](docs/BUILD-LOG.md) | What was built, when, and why |
| [`docs/ISSUES.md`](docs/ISSUES.md) | Obstacles, dead ends, and their design consequences |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | What is left, and what Recoup could become after |
| `docs/SEED-DISTRIBUTION.md` | The generator's distribution *(Phase 1)* |
| `docs/POLICY-SOURCES.md` | Every rule mapped to its citation and verification status *(Phase 2)* |

---

## A note on the regulatory citations

Rules are labelled **regulatory** or **merchant-configured**, and never confused. Every regulatory rule carries a source with a `verified` flag; unverified sources render with a visible warning in the UI and do not appear in the demo. No cap on retry attempts is claimed to be regulatory, because no verified source for one was found.

---

## Out of scope, permanently

Real money · real customers · real PII · anything where the LLM decides a number · anything requiring Razorpay account feature activation.
