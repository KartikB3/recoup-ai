# Recoup

**An autonomous receivables recovery agent where every money action and customer contact passes a deterministic, source-carrying policy engine that can veto it — measured against both a naive chaser and a do-nothing control on the same seeded batch.**

Razorpay Buildathon · Track 03: AI Revenue Recovery · solo build.

> ✅ **`v0.1-submittable`.** The complete deterministic floor is tagged: 126 records, three arms, verified policy sources, replayable logs, JSON/Markdown metrics, and no LLM on the execution path. The structured model layer is Phase 3 upside, not a dependency of this result.

---

## The Razorpay integration boundary

Stated up front, because it is a design decision and not an apology.

> The batch runs against a deterministic simulation harness which is **the system of record**. A bounded subset of interventions executes as **real Razorpay test-mode Payment Links**, closing the loop through live webhooks. The scarcity of that budget is modelled as a real constraint the agent must allocate.

**What is real:** Standard Payment Links API, server-side, test mode · callback URL with `razorpay_signature` verification · webhooks for payment events, reconciled back into the ledger.

**What is simulated, and why:** everything else — because test mode closes the doors. Payment Links are capped at 30 per business; UPI Payment Links are unsupported in test mode; error-simulation cards require clicking through a mock bank page and cannot be driven headlessly; Recurring Payments S2S needs account activation; subscription retry is untestable (3-day token expiry, and halted subscriptions issue an invoice instead of charging).

Each of those is documented with its evidence and its design consequence in **[`docs/ISSUES.md`](docs/ISSUES.md)**.

---

## Control vs baseline vs agent

Same seeded batch, ledger, clock and simulated world. Control always waits. The baseline contacts every three days until paid or five attempts. The deterministic agent proposes from observable ledger facts and every proposal passes the policy engine.

| Metric | Control | Baseline | Agent |
|---|---:|---:|---:|
| Recovery rate | 49.3% | **62.3%** | 57.8% |
| ₹ recovered | Rs 1,24,60,148.75 | **Rs 1,57,71,226.15** | Rs 1,46,10,185.33 |
| Contacts made | **0** | 459 | 157 |
| Contacts per ₹ recovered | **0.00000000** | 0.00002910 | 0.00001075 |
| **False interventions** | **0** | 104 | 23 |
| Policy vetoes | 0 | 0 | 231 |
| Escalated to human (agent-selected) | 0 | 0 | 16 |
| Human queue from payer response | **0** | 28 | 5 |
| Unresolved / written off | 72 / 0 | 37 / 19 | 60 / 0 |

The agent loses 4.6 recovery points to the baseline and that loss stays in the table. It uses **65.8% fewer contacts**, makes **77.9% fewer false interventions**, and still beats the do-nothing floor by 8.5 points. Definitions and all ten per-rule firing counts, including zeroes, are in [`runs/seed42/metrics.md`](runs/seed42/metrics.md).

---

## Why not just a rules engine?

The Phase 2 tag deliberately uses a deterministic fallback so the complete system works with no key. Phase 3 adds a structured-output model to read payer notes, replies, dispute reasons and promise language. **Every number, every rupee amount, and every go/no-go decision remains deterministic.**

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
recoup metrics seed42                     # recompute from stored artifacts
recoup dashboard                          # Phase 5
```

`recoup check-razorpay` creates one test-mode Payment Link to confirm credentials. It costs one unit of the 30-link budget.

The full batch runs with `ANTHROPIC_API_KEY` empty or unset. In `v0.1-submittable` the agent is the deterministic fallback; Phase 3 adds a disk-cached model path without changing the policy, runner or replay contracts.

---

## Repository map

| Path | What lives there |
|---|---|
| `src/recoup/domain/` | Frozen data contracts. All money is `int` paise; all dates are virtual. |
| `src/recoup/generator/` | Seeded batch generator + the free-text corpus the LLM actually reads |
| `src/recoup/ledger/` | Virtual clock, state machine, seeded outcome adjudication |
| `src/recoup/policy/` | **The policy engine.** Rules, ordering, and their citations |
| `src/recoup/reasoner/` | Deterministic fallback now; structured-output model and cache in Phase 3 |
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
