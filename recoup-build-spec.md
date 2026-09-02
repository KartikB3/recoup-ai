# Recoup — Build Spec

**Razorpay Buildathon, Track 03: AI Revenue Recovery**
Solo build, ~7 days.

*(Name is a placeholder. Alternatives: Arrears, Winback, Ledgerkeep. Pick something
that sounds like infrastructure, not like a marketing tool.)*

---

## 1. Thesis

> An autonomous receivables recovery agent where the LLM reasons and drafts, but
> every money action and every customer contact passes a deterministic policy
> engine that can veto it — and the whole thing is measured against a naive
> baseline on the same seeded batch.

The product is the policy engine and the measurement harness. The LLM is a
component that must justify its presence.

**The one-sentence answer to "why not just a rules engine?"**
The LLM reads unstructured signal (payer notes, email replies, dispute reasons,
free-text promise-to-pay) and drafts communication. Every number, every rupee
amount, and every go/no-go decision is deterministic.

If a feature can't survive that sentence, cut it.

---

## 2. Domain

**Primary lane:** B2B overdue receivables — invoices past due, chased through a
bounded escalation ladder until paid, promised, disputed, or written off.

**Secondary intake (P1, not P0):** failed payments and failed mandate debits feed
the *same* at-risk ledger, through the same policy engine, into the same audit
trail. One pipeline, multiple sources of revenue-at-risk.

Rationale is in the chat thread; the short version is that the track's bar
("compliant escalation, stopping rules, audit trail") is written for
contact-based recovery, and receivables is the only lane with a genuine
server-side execution path in Razorpay test mode.

---

## 3. Architecture

Six components. Build them in this order.

```
[1] Generator  →  [2] Ledger + Virtual Clock  →  [3] LLM Reasoner
                                                       ↓ proposes
                                              [4] Policy Engine
                                                       ↓ approves / modifies / vetoes
                                              [5] Executor  →  Razorpay test API
                                                       ↓
                                              [6] Audit Log  →  Dashboard + Metrics
```

### [1] Generator
Seeded, reproducible, 120+ invoice records. A first-class repo artifact with its
own README documenting the distribution. Must include:

- Invoice amount, due date, days overdue, payer profile, payment history
- Payer archetypes: reliable-but-slow, chronic-late, disputing, genuinely
  distressed, silent, already-paid-but-unreconciled
- Free-text fields the LLM actually needs: payer notes, prior email replies,
  dispute descriptions. **Without these the LLM has nothing to read and the
  project collapses into a rules engine.**
- A deliberate **cluster event**: e.g. 9 invoices from the same parent group all
  go silent in the same week (procurement freeze). See §7.

### [2] Ledger + Virtual Clock
Simulated time is a first-class concept from hour one. Do not retrofit this.
Recovery plays out over weeks; the demo is five minutes. Every record has a
state machine:

```
AT_RISK → CONTACTED → PROMISED → PAID
                    ↘ DISPUTED → HUMAN_QUEUE
                    ↘ EXHAUSTED → WRITTEN_OFF
```

The clock advances in discrete ticks. The ledger adjudicates outcomes
(did the payer pay? did they reply?) using seeded probabilities conditioned on
archetype and on which intervention was chosen. **The ledger is the system of
record, not Razorpay.**

### [3] LLM Reasoner
Input: one at-risk record plus relevant batch context.
Output: structured JSON only — diagnosis, proposed intervention, confidence,
reasoning string, and (if contacting) a drafted message.

Hard rules:
- Never outputs a rupee amount, a date calculation, or a final decision.
- Every call cached by input hash.
- A deterministic fallback path exists for when the API is slow or down. Assume
  it will be down during the demo recording.

### [4] Policy Engine — the core of the product
Runs *after* the reasoner. Can approve, modify, or veto. Every veto is logged
**as a veto** and is visible in the UI. See §5 for the rule set.

### [5] Executor
Two modes, selectable per run:
- `simulated` — everything happens in the ledger. Default. Used for the full batch.
- `live` — issues real Razorpay test-mode Payment Links for a small subset.

See §6 for the boundary.

### [6] Audit Log
Append-only. One row per decision, never updated. Fields:

| Field | Content |
|---|---|
| `tick` | virtual timestamp |
| `record_id` | which invoice |
| `input_snapshot` | what the agent saw |
| `llm_proposal` | intervention + confidence + reasoning |
| `policy_verdict` | approved / modified / vetoed |
| `policy_rule` | which rule fired, with its source citation |
| `action` | what was actually done |
| `outcome` | result, filled in on a later tick |

**Acceptance test: you can reconstruct any single invoice's complete history from
the log alone, with no other state.** If you can't, the log is wrong.

---

## 4. Intervention space

Small, explicit, closed. Nothing outside this list exists.

| Intervention | Cost | Notes |
|---|---|---|
| `WAIT` | none | Explicitly logged. Deciding not to act is a decision. |
| `SOFT_REMINDER` | 1 contact | Service-category message |
| `PAYMENT_LINK` | 1 contact + 1 API budget unit | The real executable action |
| `PHONE_FOLLOWUP` | 1 contact, high cost | Subject to contact-hour rules |
| `ESCALATE_HUMAN` | 0 automated cost | Routes to a queue |
| `STOP` | — | Terminal. Dispute, hardship, or exhaustion. |

`WAIT` and `STOP` being first-class options is what makes this an agent with
judgement rather than a dunning cron job. Make them visible in the demo.

---

## 5. Policy rules

Each rule carries its source. Render the source **in the UI** when the rule
fires. This is the cheapest credibility win in the entire project.

### Regulation-derived
| Rule | Source |
|---|---|
| No contact before 08:00 or after 19:00 IST | RBI Fair Practices Code; circular of 12 Aug 2022 on outsourcing of financial services barring recovery contact outside 8am–7pm |
| Promotional-category messages only 10:00–21:00 IST | TRAI TCCCPR — **verify the window against TRAI directly before quoting it** |
| Transaction-completion consent expires after 7 days | TRAI TCCCPR, Feb 2025 amendment |
| No re-consent request within 90 days of opt-out | TRAI TCCCPR, Feb 2025 amendment |
| Message category must be correctly classified (-P/-S/-T/-G) | TRAI TCCCPR, Feb 2025 amendment |
| Pre-debit notification ≥24h before any mandate debit, with opt-out | RBI *Digital Payments – E-mandate Framework, 2026*, dated 21 Apr 2026 — **applies only if you build the mandate lane** |
| AFA required above ₹15,000 per recurring transaction (₹1,00,000 for insurance premiums, mutual fund subscriptions, credit card bills) | Same framework |

### Business-policy (label these as merchant-configured, NOT regulatory)
- Max 4 contacts per payer per 30 days
- Minimum 72h spacing between contacts to the same payer
- Max 3 payment links per invoice
- Hard stop on any invoice flagged `DISPUTED`
- Escalate to human above a configurable invoice value
- Global API budget: 30 payment links per run (see §6)

**Do not claim a regulatory cap on retry attempts.** I could not find one. Card
network rules may impose limits but I have no verified source. Inventing a
regulation is worse than not citing one.

### Verify before you ship
The RBI 2026 framework post-dates reliable knowledge and was sourced through
secondary reporting. Two different circular reference numbers appear across
sources. **Cite the title and date, never a circular number, and check
rbi.org.in yourself before the video.**

---

## 6. Razorpay integration boundary

State this boundary explicitly in the README and in the video. It is a design
decision, not an apology.

### What is real
- **Standard Payment Links API**, server-side, test mode. Confirmed working.
- Callback URL + `razorpay_signature` verification.
- Webhooks for payment events, reconciled back into the ledger.

### Hard constraints discovered
| Constraint | Impact |
|---|---|
| Test mode caps Payment Links at 30 per business | Live execution covers a subset, not the batch |
| UPI Payment Links unsupported in test mode | Standard links only |
| Error-simulation test cards require clicking "failure" on a mock bank page | Card failure generation is not headless |
| Recurring Payments S2S is an on-demand feature needing account activation | Mandate retry lane is closed |
| Test-mode card tokens valid 3 days; halted subscriptions replace "Charge This Now" with "Issue Invoice" | Subscription retry is not testable |

### The design consequence — say this out loud
> The batch runs against a deterministic simulation harness which is the system
> of record. A bounded subset of interventions executes as real Razorpay
> test-mode Payment Links, closing the loop through live webhooks. The scarcity
> of that budget is modelled as a real constraint the agent must allocate.

That last sentence turns a limitation into a feature. Use it.

---

## 7. The two things that win this

Neither is expensive. Both are the difference between "solid" and "selected."

### (a) The baseline arm
Run the same seeded batch twice: once through a naive fixed-schedule chaser
(contact every 3 days until paid or 5 attempts), once through the agent. Report
both.

| Metric | Baseline | Agent |
|---|---|---|
| Recovery rate | | |
| ₹ recovered | | |
| Contacts made | | |
| Contacts per ₹ recovered | | |
| **False interventions** (chased an already-paid or disputed invoice) | | |
| Policy vetoes | — | |
| Escalated to human | | |
| Unresolved / written off | | |

**Report the numbers where you lose.** Judges notice who hides. An honest
exception list is explicitly in the track's bar.

### (b) The batch-level insight
One decision the per-record path structurally cannot produce. Example: nine
invoices across the same parent group all go silent in one week → the agent
classifies it as an account-level event rather than nine independent
delinquencies → suppresses individual chasing, opens one consolidated
relationship escalation.

This is your proof that reasoning over aggregate context earns the LLM's place.
Without it, a judge can correctly say a lookup table would have done the job.

---

## 8. Scope

### P0 — no submission without these
1. Seeded generator, 120+ records, documented distribution
2. Virtual clock + ledger state machine
3. Policy engine that vetoes, with sources rendered in the UI
4. Append-only replayable audit log
5. Baseline vs agent on the same seed, full metric table
6. One batch-level insight (§7b)
7. Dashboard: batch summary, single-invoice timeline, raw audit view
8. README documenting the Razorpay boundary honestly

### P1 — turns solid into winning
- Live Razorpay Payment Link + webhook round-trip, shown in the video
- **Abstention**: below a confidence threshold the agent routes to human queue
  instead of guessing. Showing the agent decline to act is a stronger moment
  than showing it act.
- **Kill switch**: anomaly detected → agent halts itself → dashboard shows why.
  This is your "one failure handled gracefully."
- Promise-to-pay tracking: payer says "Friday" in free text → LLM extracts →
  agent suppresses all contact until Friday → checks → escalates one step if
  broken. This is the most human, most memorable feature on the list and it
  showcases exactly what the LLM is for.
- Failed-payment / mandate intake into the same ledger

### P2 — only if genuinely ahead
Hinglish drafting, voice, multi-turn dialogue, merchant config UI.

### Out of scope, permanently
Real money, real customers, real PII, anything the LLM decides numerically,
anything requiring Razorpay account feature activation.

---

## 9. Seven-day solo plan

**Day 1 — Foundation, zero AI.**
Domain model, generator, virtual clock, ledger state machine. Write the seed
distribution README while it's fresh.

**Day 2 — Policy engine + baseline. MILESTONE.**
Deterministic policy engine. Naive baseline chaser. Run the full batch end to
end and produce the metric table. *At the end of Day 2 you have a complete,
submittable system with no LLM in it.* Everything after this is upside. Protect
this milestone above all else.

**Day 3 — LLM layer.**
Structured-output reasoner, caching by input hash, deterministic fallback,
message drafting. Re-run the batch. You should now be able to see the agent beat
the baseline. If it doesn't, that's a finding — investigate before adding
features.

**Day 4 — Razorpay live slice.**
Payment Links, callback signature verification, webhooks, reconciliation back
into the ledger. Budget-aware execution. Log every real API call.

**Day 5 — Dashboard.**
Three views. The audit view being ugly-but-real beats pretty-but-fake. Spend
your design effort on the batch summary, since that's the frame the video opens
on.

**Day 6 — Evaluation and hardening.**
Batch-level insight, abstention, kill switch, edge cases, README, engineering-log
cleanup. Freeze features at end of day.

**Day 7 — Video and submission.**
No code. Buffer for everything that breaks.

**Rule for the whole week:** if you're behind, cut from P1, never from P0.
A complete small system beats an incomplete impressive one, and the metric table
is the thing being graded.

---

## 10. Submission form mapping

The form asks for exactly seven things. Draft answers on Day 6, not Day 7.

| Field | Approach |
|---|---|
| Track | 03 — AI Revenue Recovery |
| Project name | — |
| Objectives | Lead with the thesis sentence from §1 |
| What does it solve | Frame as: the cost of a *wrong* intervention, not just a missed one |
| GitHub | Public. README must open with the Razorpay boundary (§6) and the metric table (§7a). Judges skim; put the evidence above the fold. |
| 5-min video | See below |
| Build challenges | **You already have this** — §6's constraint table is the answer. Keep an engineering log from hour zero; you will not remember the dead ends at day six. |

### Video structure (5:00)
```
0:00  The problem: a wrong chase costs more than a missed one
0:45  Architecture: LLM proposes, policy engine disposes
1:30  Single invoice timeline over virtual weeks — including one WAIT
2:15  A policy VETO firing, with the regulatory source on screen
2:45  The batch-level insight (§7b)
3:15  Live Razorpay payment link + webhook closing the loop
3:45  Baseline vs agent metric table, losses included
4:30  Honest limits: what's simulated and why
```

There is no live demo in this competition. The video *is* the product. Every
architectural decision should be tested against "does this show up in five
minutes."

---

## 11. Open items to verify before shipping

- [ ] RBI E-mandate Framework 2026 — confirm title, date and provisions at rbi.org.in
- [ ] TRAI promotional-messaging time window — confirm at trai.gov.in
- [ ] Whether the 30-link test-mode cap can be raised via Razorpay Support (worth
      one email on Day 1 — if it's raised, the live slice can be much larger)
- [ ] Refunds API behaviour in test mode, if you use it
- [ ] Whether the buildathon supplies any dataset (assume not; own the generator)
