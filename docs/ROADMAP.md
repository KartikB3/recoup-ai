# Recoup — Roadmap

What is left in the build window, and what Recoup could become after it.
Two horizons, kept deliberately separate. Do not let the second one leak into the first.

**Maintenance:** re-scope at the close of every phase. Move completed items out of §1, move slipped items down, and add anything newly discovered.

Last updated: 2026-09-03 — **Phase 3 closed. Phase 4 is next.** The cache holds
real model output: 77 record proposals and one batch insight, for $2.09. The
cost-tiered arm in `runs/seed42-tiered/` cuts scored false interventions
**23 → 0** for 3.32 recovery points. The four canonical `runs/seed42/` arms are
untouched. The full-book model arm was deliberately not bought (ISS-038,
OBS-008). `v0.1-submittable` remains untouched. The public push remains
deliberately deferred to the user.

---

## 1. Remaining in the 7-day window

### P0 — no submission without these

| # | Item | Phase | State |
|---|---|---|---|
| 10 | Structured-output reasoner + input-hash cache; preserve the deterministic fallback that landed in Phase 2 | 3 | ✅ done — real cache seeded, spend guards shipped |
| 11 | Batch-level insight (§7b) — the cluster event. **Built in Phase 3; applied and rendered in Phase 6.** | 3 → 6 | 🟡 real model insight cached and policy-approved; Phase 6 application still pending |
| 12 | Dashboard: batch summary, invoice timeline, raw audit, and rule sources/caveats | 5 | ⬜ |
| 14 | Seven submission-form answers drafted | 6 | ⬜ |
| 15 | Five-minute video | 7 | ⬜ |
| 17 | Structured-output agent proposer over the same snapshot-only Protocol; the Phase 2 fallback already satisfies it | 3 | ✅ done — measured against held-out truth on 28 prose-only records |
| 18 | Write up the fatigue calibration (ISS-021) before a judge asks how those numbers were chosen | 6 | ⬜ |
| 19 | Create the public GitHub repository and push | user decision | ⬜ local history and tag are ready |

The four-arm comparison is now a standing contract. `AlwaysWait` preserves the
49.3% floor. The naive baseline gets 62.3% with 459 contacts; the identical
proposer behind policy gets 56.5% with 161; the deterministic agent behind the
same policy gets 57.8% with 157. Every later table must preserve all four
columns: the middle pair isolates policy value, and the final pair isolates
proposer value.

**A fifth column joined it in Phase 3.** `runs/seed42-tiered/` is the same four
arms with the agent using real model proposals at first review and the ladder
after — a cost-tiered architecture, not a compromise. It records 54.43% with 104
contacts and **0** scored false interventions against the ladder arm's 23. Report
it as a harm result with its recovery cost stated, never as a recovery beat
(ISS-038, OBS-008). Keep the two run directories distinct: `runs/seed42/` is
deterministic-fallback output and `runs/seed42-tiered/` is the only place model
output appears.

**New P0, discovered in Phase 3:** rule on `HARDSHIP_CLAIMED`. The model
suppresses only 58% of hardship contacts and is drawing a distinction the flag
cannot express (OBS-002). Either score the category or write the decision down —
a judge who reads `adjudicator.py` will ask, and "nobody decided" is the one
answer that costs marks.

### P1 — turns solid into winning

Cut from here first if behind. Listed in **drop order** — drop the top one first.

| # | Item | Phase | Why it is worth it | State |
|---|---|---|---|---|
| 1 | Failed-payment / mandate intake into the same ledger | 6 | Keeps the project inside payments vocabulary for a payments panel | ⬜ |
| 2 | Promise-to-pay tracking | 6 | Most human, most memorable feature on the list; showcases exactly what the LLM is for | ⬜ |
| 3 | Kill switch — anomaly → self-halt → dashboard shows why | 6 | Your "one failure handled gracefully" | ⬜ |
| 4 | Abstention below a confidence threshold | 6 | The agent declining to act is a stronger moment than the agent acting | ⬜ |
| 5 | Live Razorpay Payment Link + webhook round-trip, on video | 4 | The only genuinely live thing in the build. Drop last. | ⬜ |

### P2 — only if genuinely ahead

Hinglish drafting · voice channel · multi-turn dialogue with the payer · merchant config UI.

Realistically none of these ship in seven days solo. They are listed so that "we chose not to" is a decision on the record rather than an omission.

### Permanently out of scope

Real money · real customers · real PII · anything where the LLM decides a number · anything requiring Razorpay account feature activation.

---

## Completed gates

| # | Item | Evidence |
|---|---|---|
| 1–4 | Generator, corpus, clock, ledger, append-only audit and replay | Phase 1; 126 records, 54 templates, zero replay divergences |
| 5 | TRAI + RBI citations verified at the issuing body | `docs/POLICY-SOURCES.md`; ISS-024 and ISS-025 |
| 6, 16 | Policy engine and `PolicyGate` wiring | Ten fixed-order rules; sources attached to firing verdicts; UI rendering remains part of #12 |
| 7 | Naive baseline on the same seed | 62.3% recovered, 459 contacts |
| 8 | Full four-arm metric table, losses and rule run-status notes included | `runs/seed42/metrics.{json,md}` |
| 9 | Complete no-LLM floor | `v0.1-submittable` |
| 13 | README boundary and metric table above the fold | Landed early at Phase 2 close |

---

## 2. Beyond the buildathon

Not part of the seven days. Written down because the "what's next" slide in a submission is usually thin, and because most of these follow directly from architecture that already exists.

### 2.1 Directly enabled by what gets built

**Replay-driven policy regression testing.**
The audit log already reconstructs any invoice's full history from the log alone. That means a recorded run is a test fixture: change a policy rule, replay the committed log, and diff the verdicts. You get a regression suite over compliance behaviour almost free. This is the single highest-value follow-on and it is maybe half a day of work.

**Counterfactual analysis.**
Same seeded world, different policy configurations, run in parallel. "What does moving the escalation threshold from ₹50k to ₹2L cost us in recovery, and buy us in contacts avoided?" The harness already supports two arms — supporting *n* arms is a loop.

**Policy-as-config.**
The merchant-policy rules are currently code. Lifting them to a declarative file makes them auditable by a compliance team rather than an engineer, and turns the merchant config UI (P2) into a form over a schema.

**Calibration measurement.**
The reasoner emits a confidence on every proposal and the ledger records what actually happened. Those two columns are a calibration curve. If the model says 0.8 and is right 55% of the time, the abstention threshold is wrong — and you can prove it rather than guess it.

### 2.2 Needs work the buildathon does not justify

**Real-instrument execution.** Recurring Payments S2S and the mandate retry lane, once the account features are activated (ISS-004). Everything above the executor interface already works; only `executor/live_razorpay.py` grows.

**Multi-channel contact.** SMS and WhatsApp through a DLT-registered header, with the TRAI category classification the policy engine already computes actually enforced end to end rather than simulated.

**Learned adjudication.** The ledger's outcome probabilities are hand-authored per archetype. With real recovery data they become a fitted model — and the simulation becomes a genuine forecasting tool rather than a demonstration harness.

**Human queue as a real product surface.** `ESCALATE_HUMAN` currently routes to a list. The interesting version is a work queue with the agent's reasoning, the policy verdict, and a one-click accept/override that feeds back as a labelled example.

**Portfolio-level allocation.** Today the batch insight detects one cluster. The general form is treating the whole receivables book as an allocation problem under a contact budget — which is where the LLM's aggregate reasoning would actually earn its keep at scale, rather than as a demo beat.

### 2.3 Deliberately not on this list

Autonomous negotiation over amounts. Any path where the LLM proposes a settlement figure. That is the one line the thesis in spec §1 draws, and crossing it later would invalidate the argument the whole project makes.
