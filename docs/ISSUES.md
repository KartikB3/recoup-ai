# Recoup — Issues, Obstacles & Dead Ends

> **This file is a graded submission artifact, not housekeeping.**
> The buildathon form has a *"Build Challenges & Technical Obstacles"* field. This document is the raw material for that answer. Write every entry as though a judge will read it — because the good ones will be lifted verbatim.
>
> A good entry names the constraint, shows the evidence, and states the **design consequence**. "We had trouble with CORS" scores nothing. "Test mode caps Payment Links at 30 per business, so we modelled action scarcity as a constraint the agent must allocate" scores.

**Maintenance:** append at the close of every phase — and immediately when you hit something, because you will not remember it on Day 6. Never delete an entry; mark it `RESOLVED` with what fixed it.

---

## Severity key

| Tag | Meaning |
|---|---|
| 🔴 **BLOCKING** | Closed a path entirely. Design had to change. |
| 🟠 **CONSTRAINING** | Path still open but bounded. Shaped the design. |
| 🟡 **FRICTION** | Cost time, no design impact. |
| 🔵 **UNCERTAINTY** | Not yet resolved. Must be verified before shipping. |

---

## Pre-build: constraints established during research

These five were discovered before a line of code was written, through Razorpay documentation and testing reports. They are the backbone of the Build Challenges answer. Each one is already sourced.

---

### ISS-001 · 🟠 Test mode caps Payment Links at 30 per business

**Phase:** pre-build (research)
**What we found:** Standard Payment Links can be created via API in test mode, but a Razorpay account is capped at 30 links unless the cap is raised by Razorpay Support.

**Why it matters:** With 120+ invoices in the batch, live execution can only ever cover a subset. A naive design would have made "every intervention is a real API call" a core assumption and then collapsed.

**Design consequence — this is the good version of the story:**
> The simulation harness is the system of record for the full batch. A bounded subset of interventions executes as real Razorpay test-mode Payment Links, closing the loop through live webhooks. The scarcity of that budget is modelled as a real constraint the agent must allocate — highest-expected-recovery invoices get the real links.

The cap stopped being a limitation and became a feature of the agent's decision problem.

**Action:** email Razorpay Support in Phase 0 asking for a raise. If granted, the live slice grows; if not, nothing changes. Record the outcome here.
**Status:** OPEN — support email not yet sent.

---

### ISS-002 · 🟠 UPI Payment Links are unsupported in test mode

**Phase:** pre-build (research)
**What we found:** UPI Payment Links cannot be created in Razorpay test mode at all. Standard Payment Links only.

**Design consequence:** The intervention space contains one link type, not several. Removes a whole branch of "which instrument should we offer" logic that could not have been tested. Simplification, not loss.

**Status:** ACCEPTED — permanent constraint, designed around.

---

### ISS-003 · 🔴 Error-simulation test cards are browser-bound

**Phase:** pre-build (research)
**What we found:** Razorpay publishes a genuinely rich failure taxonomy in test mode — `BAD_REQUEST_ERROR` (`payment_timed_out`, `insufficient_fund`, `payment_cancelled`, `card_declined`, `card_disabled_for_online_payments`, `card_number_invalid`) and `GATEWAY_ERROR` (`gateway_technical_error`, `authentication_failed`), each with distinct Visa and Mastercard test numbers.

**But:** you cannot trigger them headlessly. Test mode routes through a mock bank page with **Success** and **Failure** buttons, and the specific error reason depends on a human (or a browser automation) clicking through. UPI is worse — binary only, `success@razorpay` or `failure@razorpay`, no error-reason granularity. Netbanking and wallets are the same shape.

**Design consequence — two of them:**
1. Generating 100+ varied failures headlessly is impossible via the API. The seeded generator must own the failure distribution. This is *why* the simulation harness is the system of record, stated as a design decision rather than an apology.
2. We adopt Razorpay's own error vocabulary rather than inventing one. The generated failure reasons map onto their published taxonomy — soft decline / hard decline / transient infrastructure — so the simulated data speaks the platform's language.

**Status:** ACCEPTED — permanent constraint, and the origin of the whole architecture.

---

### ISS-004 · 🔴 Recurring Payments S2S requires account activation

**Phase:** pre-build (research)
**What we found:** Recurring Payments server-to-server is an on-demand feature that must be activated on the account by a request to Razorpay. Not obtainable within a hackathon window.

**Design consequence:** The mandate-retry lane is closed for live execution. Mandate events can still flow into the same at-risk ledger through the same policy engine (spec §2, secondary intake) — the *intake* is real, the *execution* is simulated. Boundary stated explicitly in the README.

**Status:** ACCEPTED — path closed, scope adjusted.

---

### ISS-005 · 🔴 Subscription retry is not testable in test mode

**Phase:** pre-build (research)
**What we found:** Three compounding limits:
- Test-mode card tokens are valid for **3 days**, so a subsequent debit only works inside that window.
- Once a subscription reaches `halted`, **no automatic charge attempts are triggered**.
- In test mode the "Charge This Now" button is replaced with "Issue Invoice" — a new invoice is issued, but no charge occurs.
- Mandate registration and authentication are mocked; no real 3DS or OTP.

That last pair is precisely the action a recovery agent would want to take, and it is exactly the one that does not execute.

**Design consequence:** Confirms the choice of B2B overdue receivables over payment-retry as the primary lane. Receivables recovery executes through Payment Links, which works server-side today. **The domain with the best narrative turned out to be the only one with a real execution path** — that coincidence is worth stating out loud in the video.

**Status:** ACCEPTED — decisive input to the domain choice.

---

## Open uncertainties — must be resolved before shipping

These are 🔵. None of them may reach the video unverified. The `RuleSource.verified` flag in the policy engine exists to enforce this mechanically.

---

### ISS-006 · 🔵 RBI E-mandate Framework 2026 — provenance unconfirmed

**What we have:** Reportedly titled *Digital Payments – E-mandate Framework, 2026*, dated 21 April 2026, consolidating and repealing eight circulars issued 2019–2024. Reported provisions: pre-transaction notification ≥24h before debit plus a post-transaction alert with per-transaction opt-out; recurring transactions up to ₹15,000 without AFA (₹1,00,000 for insurance premiums, mutual fund subscriptions and credit card bills); acquirer responsibility for merchant compliance; FASTag and NCMC auto-replenishment exempt from the pre-alert.

**The problem:** Sourced entirely through secondary reporting, and **two different circular reference numbers appear across sources**.

**Rule:** cite the **title and date only, never a circular number**, and verify at rbi.org.in before anything goes on screen.
**Scope note:** these rules only apply if the mandate lane is built, which is P1. Do not burn Phase 2 time on this.
**Status:** OPEN — verify in Phase 6, only if the mandate lane ships.

---

### ISS-007 · 🔵 TRAI promotional-messaging time window — unverified

**What we have:** A secondary source states promotional SMS may only be delivered 10:00–21:00 IST, with transactional and service messages permitted 24 hours. A separate TRAI gazette document suggests the transactional category is scoped to messages triggered within 30 minutes of a customer-initiated transaction.

**The problem:** Vendor-blog sourcing, not TRAI directly.

**Action:** verify at trai.gov.in in **Phase 2** — this is P0, because it gates contact timing in the policy engine.
**Status:** OPEN.

---

### ISS-008 · 🔵 RBI Fair Practices contact window — scope caveat

**What we have:** The August 2022 outsourcing-of-financial-services circular bars regulated entities and their agents from contacting a borrower before 08:00 or after 19:00 to recover overdue loans, and from intimidation or harassment.

**The caveat, and be honest about it:** strictly this governs *lending recovery*, not merchant receivables dunning. Encoding it as the contact window is defensible and reads as domain literacy — but it should be presented as **an adopted standard, not a binding obligation** on this use case. Say so in the UI copy and the README.

**Action:** verify the circular at rbi.org.in in Phase 2 (P0).
**Status:** OPEN.

---

### ISS-009 · 🔵 No verified regulatory cap on retry attempts

**What we found:** No regulatory limit on the number of recovery retry attempts could be located. Card network rules (Visa, Mastercard) may impose limits, but no verified source was found.

**Decision:** the max-attempts rule ships as **merchant-configured business policy**, explicitly labelled as such in `docs/POLICY-SOURCES.md` and in the UI. **Do not invent a regulation.** Getting caught fabricating a citation is worse than citing none, and a payments panel is exactly the audience that would catch it.

**Status:** RESOLVED by design decision. No further verification needed — the rule simply is not claimed to be regulatory.

---

### ISS-010 · 🔵 Refunds API behaviour in test mode — unverified

**What we have:** Probably usable in test mode; not confirmed.
**Action:** verify in Phase 4, and only if the design actually calls for refunds. Currently it does not.
**Status:** OPEN, low priority.

---

## Build-time issues

### ISS-011 · 🟡 Ruff UP042 / B008 both fire on idiomatic Typer code

**Phase:** 0
**What happened:** With `select = ["E","F","I","UP","B","SIM","RUF"]`, ruff flagged five errors in `cli.py`: `UP042` on `class Arm(str, Enum)` and `B008` on every `typer.Option(...)` default.
**What we did:** `UP042` was a real improvement — switched to `enum.StrEnum`, available since 3.11 and what `requires-python` already asks for. `B008` is a false positive against the Typer framework idiom (options *must* be call-valued defaults), so it is suppressed per-file with a comment saying why, rather than dropping `B` from the whole ruleset.
**Design consequence:** None. Recorded because "we suppressed a lint rule" is the kind of thing that looks unprincipled at review time unless the reason is written down at the moment it happened.
**Status:** RESOLVED.

---

### ISS-012 · 🟡 The `razorpay` Python SDK ships no type stubs

**Phase:** 0
**What happened:** `mypy --strict` fails on `import razorpay` — *"module is installed, but missing library stubs or py.typed marker"*.
**What we did:** Narrow override in `pyproject.toml` for `razorpay.*` only. Strict mode stays on everywhere else.
**Why it matters later:** Phase 4 touches this SDK for payment links and webhook signature verification, and that is the one place in the build where correctness is absolute. Untyped SDK responses mean the type checker will not catch a wrong field name there — so the Phase 4 signature-verification test against a known-good fixture is not optional.
**Design consequence:** None yet. Flagged as a Phase 4 risk.
**Status:** RESOLVED for now, revisit in Phase 4.

---

### ISS-013 · 🟡 Heredoc authoring of docs with mixed quoting is a time sink

**Phase:** 0
**What happened:** Two attempts at writing multi-file content through shell heredocs failed on quote parsing before the approach was changed.
**What we did:** Long-form content goes through direct file writes; batches of generated files go through a short Python script. Shell heredocs are reserved for short, quote-free content.
**Design consequence:** None. Noted so the same twenty minutes is not spent again in Phase 1, which writes a 25–30 template free-text corpus.
**Status:** RESOLVED.

---

*Append below as they happen. Do not wait for phase close.*

---

## Entry template

```markdown
### ISS-0NN · <severity> <one-line title>

**Phase:** <n>
**What happened:** <the observed behaviour, with the exact error text if short>
**Why it matters:** <what it threatened>
**What we tried:** <the dead ends, in order — these are the valuable part>
**Design consequence:** <what changed in the architecture, or "none">
**Status:** OPEN / RESOLVED — <what fixed it> / ACCEPTED — <permanent, designed around>
```
