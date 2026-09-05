# Recoup — Roadmap

What is left in the build window, and what Recoup could become after it.
Two horizons, kept deliberately separate. Do not let the second one leak into the first.

**Maintenance:** re-scope at the close of every phase. Move completed items out of §1, move slipped items down, and add anything newly discovered.

Last updated: 2026-09-03 — **Phase 5 is complete. Phase 6 is next. Phase 4's
offline half is verified and its live half still awaits the user.** The live slice is complete in
code: the agent allocates a capped payment-link budget from revealed demand,
creates real test-mode links, and a signature-verified webhook reconciles a
payment into the ledger as an ordinary append-only outcome row. The whole loop
has been run end to end against a fake client — `CONTACTED → PAID`, replay
clean — **without spending a single test-mode link**. What remains is a browser,
a tunnel and ~3 real links, which is the user's call (ISS-039 constrains the
horizon that verification must use).

The cache still holds 77 real record proposals and one batch insight, for
$2.09. The cost-tiered arm in `runs/seed42-tiered/` cuts scored false
interventions **23 → 0** for 2.63 recovery points, and still reproduces byte for
byte after the Phase 4 executor change. The four canonical `runs/seed42/` arms
are untouched. The full-book model arm was deliberately not bought (ISS-038,
OBS-008). `v0.1-submittable` remains untouched, and is now pushed to `origin`
alongside `main`.

---

## 1. Remaining in the 7-day window

### P0 — no submission without these

| # | Item | Phase | State |
|---|---|---|---|
| 11 | Batch-level insight (§7b) — the cluster event. **Built in Phase 3; applied in Phase 6.** | 3 → 6 | ✅ done — binds through `batch-cluster-suppression`, 54 logged suppressions (ISS-047) |
| 23 | Exercise the terminal path end to end (`STOP` → `EXHAUSTED` → write-off) so the bar's "stopping rules" is demonstrated, not just tested | 6 | ✅ done — `runs/seed42-t224/`, ISS-046, OBS-011 |
| 14 | Submission-form answers drafted | 6 | ✅ done — `docs/SUBMISSION.md`; the form has five fields, two of them URLs |
| 15 | Five-minute video | 7 | 🟡 narration in `docs/VIDEO-SCRIPT.md`, shooting order in `docs/RUNBOOK.md` Part B; recording is the user's |
| 18 | Write up the fatigue calibration (ISS-021) before a judge asks how those numbers were chosen | 6 | ✅ done — `docs/SEED-DISTRIBUTION.md`, *How the fatigue numbers were chosen* |
| 22 | **Rule on `HARDSHIP_CLAIMED`**: either score it as a third false-intervention subtype or write down the decision that hardship contact is legitimate. | 6 | ✅ done — reported, not scored; decision and evidence in ISS-048. OBS-002 closed |
| 19 | Create the public GitHub repository and push | user decision | ✅ done — `main` and `v0.1-submittable` on github.com/KartikB3/recoup-ai |
| 21 | Run the live round trip once and screen-record it: 3 links, tunnel, mock-page payment, webhook, `PAID` | 4 | ⬜ user decision — everything it needs is built and the step-by-step is `docs/RUNBOOK.md` Part A. Nothing spends a link before step 8 |

The four-arm comparison is now a standing contract. `AlwaysWait` preserves the
49.3% floor. The naive baseline gets 62.3% with 459 contacts; the identical
proposer behind policy gets 56.5% with 161; the deterministic agent behind the
same policy gets 56.7% with 137. Every later table must preserve all four
columns: the middle pair isolates policy value, and the final pair isolates
proposer value.

**A fifth column joined it in Phase 3.** `runs/seed42-tiered/` is the same four
arms with the agent using real model proposals at first review and the ladder
after — a cost-tiered architecture, not a compromise. It records 54.09% with 89
contacts and **0** scored false interventions against the ladder arm's 23. Report
it as a harm result with its recovery cost stated, never as a recovery beat
(ISS-038, OBS-008). Keep the two run directories distinct: `runs/seed42/` is
deterministic-fallback output and `runs/seed42-tiered/` is the only place model
output appears.

**Items 18 and 22 are closed, and both were decisions rather than builds.**
Item 22 asked whether `HARDSHIP_CLAIMED` should become a third
false-intervention subtype. It should not: the model contacts three of the
twelve hardship records and all three are payers who asked to be able to pay, so
the subtype would have scored sending a payment link to someone who requested
one as harm. Hardship is **reported, not scored**, and the rule that governs it
is written out in ISS-048. Item 18 writes up how `FATIGUE_ONSET` and
`FATIGUE_COMPLAINT_STEP` were chosen, in `docs/SEED-DISTRIBUTION.md` — the
sweep, the target, and the load-bearing fact that recovery barely moves across
the whole range, so the calibration governs the plausibility of the harm rather
than who wins.

### P1 — turns solid into winning

Cut from here first if behind. Listed in **drop order** — drop the top one first.

| # | Item | Phase | Why it is worth it | State |
|---|---|---|---|---|
| 1 | Failed-payment / mandate intake into the same ledger | 6 | Keeps the project inside payments vocabulary for a payments panel | ⬜ |
| 2 | Promise-to-pay tracking | 6 | Most human, most memorable feature on the list; showcases exactly what the LLM is for | ⬜ |
| 3 | Kill switch — anomaly → self-halt → dashboard shows why | 6 | Your "one failure handled gracefully" | ⬜ |
| 4 | Abstention below a confidence threshold | 6 | The agent declining to act is a stronger moment than the agent acting | ⬜ |
| 5 | Live Razorpay Payment Link + webhook round-trip, on video | 4 | The only genuinely live thing in the build. Drop last. | 🟡 built and verified offline; the real round trip needs a tunnel, a browser and ~3 links — the user's call |

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
| 20 | Scarce-link allocation, live executor, verified webhook, ledger reconciliation | Phase 4; 262 offline tests, 0 test-mode links spent. ISS-039 to ISS-042; ISS-012 resolved |
| 10, 17 | Structured-output proposer, validated cache, spend guards and deterministic fallback | Phase 3; 77 real record proposals, 0 scored false interventions in the tiered arm |
| 12 | Offline dashboard: five-arm summary, named-payer timeline, filterable raw audit and source caveats | Phase 5; all three views exercised from local artifacts, 274 tests |

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
