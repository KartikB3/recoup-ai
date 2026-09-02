# Recoup — Roadmap

What is left in the build window, and what Recoup could become after it.
Two horizons, kept deliberately separate. Do not let the second one leak into the first.

**Maintenance:** re-scope at the close of every phase. Move completed items out of §1, move slipped items down, and add anything newly discovered.

Last updated: 2026-09-02 · Phase 0 scaffold committed (`8233ff6`). Phase 0 gate still open on three items that need your Razorpay account and a public push — see docs/BUILD-LOG.md, "Carried forward".

---

## 1. Remaining in the 7-day window

### P0 — no submission without these

| # | Item | Phase | State |
|---|---|---|---|
| 1 | Seeded generator, 120+ records, documented distribution | 1 | ⬜ |
| 2 | Free-text corpus — 25–30 varied templates | 1 | ⬜ |
| 3 | Virtual clock + ledger state machine | 1 | ⬜ |
| 4 | Append-only audit log + replay acceptance test | 1 | ⬜ |
| 5 | TRAI + RBI Fair Practices citations verified at source | 2 | ⬜ |
| 6 | Policy engine that vetoes, with sources rendered in the UI — **depends on #5** | 2 | ⬜ |
| 7 | Naive baseline chaser on the same seed | 2 | ⬜ |
| 8 | Full metric table, both arms, losses included | 2 | ⬜ |
| 9 | **Gate: `v0.1-submittable` tagged — complete system, no LLM** | 2 | ⬜ |
| 10 | Structured-output reasoner + input-hash cache + deterministic fallback | 3 | ⬜ |
| 11 | Batch-level insight (§7b) — the cluster event. **Built in Phase 3; wired to the dashboard in Phase 6.** | 3 → 6 | ⬜ |
| 12 | Dashboard: batch summary, invoice timeline, raw audit | 5 | ⬜ |
| 13 | README with the Razorpay boundary and metric table above the fold | 6 | ⬜ |
| 14 | Seven submission-form answers drafted | 6 | ⬜ |
| 15 | Five-minute video | 7 | ⬜ |

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
