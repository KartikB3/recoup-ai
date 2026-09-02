# Recoup

**An autonomous receivables recovery agent where the LLM reasons and drafts, but every money action and every customer contact passes a deterministic policy engine that can veto it — and the whole thing is measured against a naive baseline on the same seeded batch.**

Razorpay Buildathon · Track 03: AI Revenue Recovery · solo build.

> 🚧 **Phase 0.** Scaffold only. No results yet. This README is structured for the judge-facing version: the boundary and the metric table go above the fold, because judges skim. Everything marked *(pending)* gets filled in as the phases land — see `docs/ROADMAP.md` for what is left.

---

## The Razorpay integration boundary

Stated up front, because it is a design decision and not an apology.

> The batch runs against a deterministic simulation harness which is **the system of record**. A bounded subset of interventions executes as **real Razorpay test-mode Payment Links**, closing the loop through live webhooks. The scarcity of that budget is modelled as a real constraint the agent must allocate.

**What is real:** Standard Payment Links API, server-side, test mode · callback URL with `razorpay_signature` verification · webhooks for payment events, reconciled back into the ledger.

**What is simulated, and why:** everything else — because test mode closes the doors. Payment Links are capped at 30 per business; UPI Payment Links are unsupported in test mode; error-simulation cards require clicking through a mock bank page and cannot be driven headlessly; Recurring Payments S2S needs account activation; subscription retry is untestable (3-day token expiry, and halted subscriptions issue an invoice instead of charging).

Each of those is documented with its evidence and its design consequence in **[`docs/ISSUES.md`](docs/ISSUES.md)**.

---

## Baseline vs agent

Same seeded batch, same ledger, same virtual clock. One run through a naive fixed-schedule chaser (contact every 3 days until paid or 5 attempts), one through the agent.

| Metric | Baseline | Agent |
|---|---|---|
| Recovery rate | *(pending)* | *(pending)* |
| ₹ recovered | *(pending)* | *(pending)* |
| Contacts made | *(pending)* | *(pending)* |
| Contacts per ₹ recovered | *(pending)* | *(pending)* |
| **False interventions** (chased an already-paid or disputed invoice) | *(pending)* | *(pending)* |
| Policy vetoes | — | *(pending)* |
| Escalated to human | *(pending)* | *(pending)* |
| Unresolved / written off | *(pending)* | *(pending)* |

The rows where the agent loses are reported too. An honest exception list is explicitly in the track's bar.

---

## Why not just a rules engine?

The LLM reads unstructured signal — payer notes, email replies, dispute reasons, free-text promise-to-pay — and drafts communication. **Every number, every rupee amount, and every go/no-go decision is deterministic.**

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
cp .env.example .env                      # fill in Razorpay TEST keys

recoup generate --seed 42                 # Phase 1
recoup run --seed 42 --arm both           # Phase 2
recoup metrics <run-id>                   # Phase 2
recoup dashboard                          # Phase 5
```

`recoup check-razorpay` creates one test-mode Payment Link to confirm credentials. It costs one unit of the 30-link budget.

The full batch runs with `ANTHROPIC_API_KEY` unset — the reasoner has a disk cache and a deterministic fallback path, because the API will be down exactly when the video is being recorded.

---

## Repository map

| Path | What lives there |
|---|---|
| `src/recoup/domain/` | Frozen data contracts. All money is `int` paise; all dates are virtual. |
| `src/recoup/generator/` | Seeded batch generator + the free-text corpus the LLM actually reads |
| `src/recoup/ledger/` | Virtual clock, state machine, seeded outcome adjudication |
| `src/recoup/policy/` | **The policy engine.** Rules, ordering, and their citations |
| `src/recoup/reasoner/` | Structured-output LLM layer, cache, deterministic fallback |
| `src/recoup/executor/` | Simulated and live-Razorpay execution, scarce-budget allocation |
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
