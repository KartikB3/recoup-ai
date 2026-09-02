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

**Action — revised, and the reasoning is the interesting part:** the original plan was to email Razorpay Support in Phase 0 asking for a raise. **Decided against.** Three reasons: the cap is load-bearing for the pitch, since scarcity is precisely what the agent allocates and a raised cap would weaken that; the demo needs the loop to close *once*, not at volume, because the allocation decision across the other 119 invoices is visible in the audit log without creating a single extra link; and the actual risk was never insufficient quota but burning it on debugging, which mock-first development in Phase 4 solves better than a bigger number would. Projected burn is ~10–12 links across the week against a budget of 30.

**Unknown:** whether the cap is lifetime or resets periodically. Not established either way, and it does not change the plan under either reading. If a reset is observed, log it here.

**Consumed so far:** 1 of 30 — the Phase 0 smoke test (`plink_TXAFGZfOooV75R`, 2026-09-02). Keep this line current; it is the only running total.

**Status:** ACCEPTED — the constraint stands, deliberately, and is designed around.

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

### ISS-014 · 🟢 Heredoc authoring failed again in Phase 1, exactly as ISS-013 predicted

**Phase:** 1
**What happened:** Writing `payer_notes.yaml` through a shell heredoc failed with `unexpected EOF while looking for matching quote` and left no file behind. The corpus YAML contains apostrophes inside quoted English prose, which is the same class of failure logged in ISS-013. It then happened a **third** time while appending this very entry to `ISSUES.md`, because the entry text itself contains quoted shell fragments.
**Why it matters:** Only twenty minutes each time, but it was time spent on a problem already solved and written down. The Phase 0 note existed and was not followed.
**What we tried:** One heredoc attempt, then a switch to direct file writes for all long-form content — which is what ISS-013 already prescribed.
**Design consequence:** None to the system. The working rule is now firm: **long-form prose goes through a file write, never a heredoc**; heredocs are reserved for short, quote-free shell content, and multi-line source edits go through a small Python script that reads its input from a file rather than from stdin.
**Status:** RESOLVED.

---

### ISS-015 · 🟡 Two of the nine cluster records rendered near-identical text on the demo seed

**Phase:** 1
**What happened:** On seed 42, `ASH-2026-0002` and `ASH-2026-0006` — the two records carrying the STRONG cluster hint, and the clearest voices in the batch-level insight — drew the same template pair (`CN-01` + `CE-01`) and the same opening slot value. Side by side they read as copy-paste.
**Why it matters:** Those nine records are the single passage a judge reads most closely, because the batch-level insight is the only claim in the project that an LLM does something a lookup table cannot. Text that looks machine-generated there undermines the claim it is meant to support.
**What we tried:** First checked whether the RNG was correlated across cluster slots — it was not; seeds 43–46 produced varied draws, so seed 42 was a genuine coincidence. Rejected special-casing seed 42 in the generator as dishonest and fragile. Then found the real cause: `CN-02` and `CE-02`, the *second* STRONG templates, excluded `RELIABLE_BUT_SLOW`, and both STRONG cluster slots are that archetype — so the pair was forced, not unlucky. The restriction turned out to be arbitrary; nothing in an authority-change note is specific to a chronically late payer.
**Design consequence:** Three changes, in increasing order of value. (1) The archetype restriction on `CN-02`/`CE-02` was dropped. (2) `_without` in `generate.py` now filters templates already spent by a record's cluster siblings, falling back to the unfiltered pool rather than emitting a record with no free text; a payer also no longer draws the same template for two emails. (3) The underlying problem was corpus breadth — the WEAK band had one template pair for two records and MEDIUM had two for three, so the fallback was firing by construction. Six templates were added (`CN-06`–`CN-08`, `CE-06`–`CE-08`), taking the corpus from 48 to 54 and the cluster bands to exact coverage. All nine records now draw distinct templates. `tests/test_corpus.py::test_cluster_hints_are_graded` asserts each band is at least as deep as its demand, so the fallback cannot start firing again silently.
**Status:** RESOLVED.

---

### ISS-016 · 🟡 A "signal leakage" test was written, failed, and was deleted as unsound

**Phase:** 1
**What happened:** `tests/test_corpus.py` originally asserted that no template body contains the words of its own signal tag — the mechanical reading of the corpus rule in `SignalKind`. It failed immediately on `CE-02-new-finance-head`, tagged `AUTHORITY_CHANGE`, for containing the word "change".
**Why it matters:** The instinct on a failing test is to weaken it until it passes. Doing that here would have left a test that looked like it enforced the corpus rule and did not.
**What we tried:** Loosened the heuristic to require *every* word of a multi-word signal to appear. That flagged ten templates, of which most were plainly legitimate: `PN-09-tds` for saying "TDS deduction", `ER-03-already-remitted` for saying the payer had already paid. Those are exactly what such payers would write, and they only ever appear in PROSE — which is the entire point. A note is not disqualified by being clear; it is disqualified by putting the answer in a structured field, and none of them do.
**Design consequence:** The generic test was removed rather than tuned, and the reasoning written into the file that replaced it. What actually needs enforcing is narrower and is now covered by two precise tests: the curated `BANNED_IN_CLUSTER` word list, checked against every template body, subject line and slot value in the CLUSTER pool; and `test_the_batch_insight_cannot_be_read_off_a_single_record`, which caps STRONG cluster hints at two of nine. A vague test that fires on good text trains you to ignore it.
**Status:** RESOLVED.

---

### ISS-017 · 🔴 The ledger wrote records off outside the audit log, and the replay test did not notice

**Phase:** 1
**What happened:** `Ledger.finalise()` moved every still-EXHAUSTED record to WRITTEN_OFF at the end of a run, with no audit row emitted. `audit.replay` reproduced those write-offs by calling a `finalise_replay()` helper that re-ran the same logic afterwards. Every test passed. The gap surfaced only when `recoup replay` was run against a committed artifact: the CLI has no run object and inferred the horizon from the last row in the log — 101, where the run had used 112 — and all 19 written-off records came back with the wrong `resolved_tick`.
**Why it matters:** This is the most serious defect found in the phase, and it is serious because of what it says rather than what it broke. **A state change existed that the audit log could not account for**, in a project whose central claim is that every action is auditable and every run reconstructible. The replay test passed because it was re-deriving the answer from a copy of the logic instead of reading it out of the log — the exact failure mode the design was written to prevent, reproduced inside the test meant to prevent it.
**What we tried:** The first instinct was to store the horizon in `summary.json` so the CLI could stop guessing. That would have worked and would have been wrong: it patches the symptom and leaves an unlogged state change in place.
**Design consequence:** `Ledger.finalise` is gone. `Ledger.awaiting_write_off()` returns the eligible records without moving them, and `runner/batch.py` applies each through the same outcome path as every other state change, so the write-off lands in the log as an `OutcomeKind.WRITTEN_OFF` row with its tick attached. Replay now needs no finalisation step and no knowledge of the horizon; `finalise_replay` was deleted. `tests/test_replay.py::test_write_offs_are_rows_in_the_log_not_an_implied_side_effect` reconstructs the closing position with no finalisation call anywhere in it.
**The general lesson, recorded because it will recur:** a replay that shares a helper with the thing it is checking is not a check. The standard adopted for the rest of the build is that replay may call the ledger's own writers — that is the point, one implementation — but it may never call anything that *decides* what to write.
**Status:** RESOLVED.

---

### ISS-018 · 🟡 `run_batch` mutated the caller's records, so the stored batch file was the closing position

**Phase:** 1
**What happened:** `run_batch` was documented as mutating its `records` argument in place, with callers expected to reload the batch when they needed a clean copy. `write_run(result, batch, ...)` then wrote the batch as `batch.json` — but `batch.records` was the very list the run had just walked over, so the "opening position" file contained the final states. Replaying from it double-applied every row.
**Why it matters:** It was caught by a test within minutes, but the same footgun had a worse version waiting: running two arms off one batch object and comparing them to each other would have produced a comparison of a book against itself, and nothing would have crashed.
**What we tried:** Nothing else. The in-place design was a deliberate choice made earlier in the phase to avoid 126 model copies, and it was simply not worth it.
**Design consequence:** `run_batch` now deep-copies each record into its ledger and leaves the caller's list untouched; the final position lives on `result.ledger.records`. One `model_copy` per record is free next to a 112-tick run.
**Status:** RESOLVED.

---

### ISS-019 · 🟢 Three state-machine holes found by exhaustive tests rather than by running the code

**Phase:** 1
**What happened:** `tests/test_ledger.py` asserts that `state_after_action` and `state_after_outcome` never name a move `ALLOWED_TRANSITIONS` forbids, over every (state, intervention) and (state, outcome) pair. Two of the three holes it found had already crashed a real run; the third had not, and would not have for some time.

- `set_promise` promoted a HUMAN_QUEUE record back to PROMISED — automation reclaiming a case a human already owned, because a contact was still in flight when the escalation happened.
- `STOP` demoted DISPUTED and HUMAN_QUEUE records to EXHAUSTED, which fed them to write-off and booked open commercial matters as settled losses.
- `state_after_outcome` returned WRITTEN_OFF from *any* state, contradicting the ledger's own documented rule that WRITTEN_OFF is reachable only from EXHAUSTED at finalisation. An outcome row carrying it would have written off a live receivable.

**Why it matters:** The third one is the argument for exhaustive tests over example-based ones. It was unreachable in Phase 1 because nothing emits that outcome yet — and it would have become reachable the moment Phase 2 or 4 did, with no test failing.
**Design consequence:** A single `_legal(current, target)` helper now filters every derived transition through `ALLOWED_TRANSITIONS`, so the table is the one place any of this is decided and a derivation function cannot contradict it. `set_promise` records the phrase and the due tick regardless but only moves state when the machine permits it, so a payer whose case a human owns can still promise, and still pay, without automation taking the case back. `UNATTENDED_STATES` keeps HUMAN_QUEUE records out of the review rotation entirely — they reach that state via a COMPLAINT outcome, which never pushed out `next_review_tick`, so the agent had been proposing actions on cases a person had already taken over.
**Status:** RESOLVED.

---

### ISS-020 · 🟢 `PyYAML` ships no inline types either, but publishes stubs

**Phase:** 1
**What happened:** `mypy --strict` failed with *"Library stubs not installed for 'yaml'"* once the corpus loader landed.
**What we did:** Added `types-PyYAML` to the `dev` extra. Deliberately **not** the narrow-override treatment ISS-012 gave `razorpay`: PyYAML publishes real stubs, so installing them keeps full type checking over the corpus loader, whereas an override would switch it off.
**Design consequence:** None. Recorded so the difference between the two decisions is on the record — `razorpay` gets an override because no stubs exist, not because overrides are the house style.
**Status:** RESOLVED.

---

### ISS-021 · 🟡 The naive baseline was accidentally a straw man, and the fix was a judgement call

**Phase:** 1
**What happened:** With the first fatigue parameters (`FATIGUE_ONSET=2`, `FATIGUE_COMPLAINT_STEP=0.035`), the naive chaser drove **44 of 126 records** into the human queue over its five-contact campaign. That is 35% of the book needing human attention because a system sent five reminders, which is not a credible outcome.
**Why it matters:** A baseline that loses badly is worth nothing. The entire comparison in build spec section 7a rests on the baseline being what a competent engineer actually ships — if a judge reads the numbers as rigged, every downstream claim goes with it. The risk here ran opposite to the usual one: not that the agent looks bad, but that it looks too good.
**What we tried:** Swept the two parameters and read off the effect on human-queue volume and recovery: `(2, 0.035)` gave 44 queued at 61.7% recovered; `(3, 0.025)` gave 35 at 62.3%; `(3, 0.015)` gave 28 at 62.3%; `(3, 0.010)` gave 23. Recovery barely moves across the whole range, so the choice is entirely about the plausibility of the HARM, not about who wins.
**Design consequence:** Settled on `FATIGUE_ONSET=3` and `FATIGUE_COMPLAINT_STEP=0.015`: three penalty-free approaches matches ordinary commercial practice, and 28 human-queue items from 459 contacts reads as a costly-but-real system. **This was a calibration, and calling it anything else would be dishonest** — the reasoning, the numbers considered and the target are written out in full at the constant itself in `ledger/adjudicator.py`, and `docs/SEED-DISTRIBUTION.md` states plainly that every number in the behaviour table is a modelling choice rather than a measured quantity.
**Status:** RESOLVED — and flagged for the Phase 6 write-up, because a judge is entitled to ask how these numbers were chosen.

---

### ISS-022 · 🟠 The committed run artifact did not match the batch hash the docs publish

**Phase:** 1
**What happened:** The batch format had acquired two serialisers without anyone deciding it should. `generator.write_batch` uses `serialise()` — indented, human-readable — and its SHA-256 is published in `docs/SEED-DISTRIBUTION.md` as *the* hash of seed 42. `runner.write_run` independently re-dumped the same object through `canonical_json`, producing compact JSON: valid, round-trippable, replayable, and **98,270 bytes shorter with a completely different hash**.
**Why it matters:** Nothing was broken in any executable sense. `load_batch` reads both, replay reconstructed both runs from either, and all 164 tests passed. The damage was purely to the claim: a reader who hashed `runs/phase1-baseline/batch.json` and compared it against the figure printed in the docs would have got a mismatch on the project's headline reproducibility statement, and would have been entirely right to distrust everything downstream of it. The whole point of publishing a hash is that someone checks it.
**Why the tests missed it:** every determinism test compared the generator against *itself* across processes, and every replay test compared a reconstruction against the run it came from. Neither ever compared the two artifacts to each other, because nothing in the design said they were supposed to be the same file — that assumption lived only in the documentation.
**What we tried:** Nothing else. Once stated, there is one right answer.
**Design consequence:** `write_run` now calls `serialise(batch)`. One serialiser for the batch format, the same discipline `_legal` imposes on state transitions and that `Ledger.transition` imposes on `.state`. `tests/test_replay.py::test_write_run_produces_a_replayable_artifact` asserts the stored file is byte-identical to `serialise(generate_batch(42))`, so the two can never drift apart again silently. All three committed batch files now hash to `c903d917…88dd6f`.
**The general lesson:** a fact that is stated only in prose is not enforced. Every claim the docs make about a byte-level property needs a test that would fail if the claim stopped being true — otherwise the documentation is the only thing holding it up, and documentation does not run in CI.
**Status:** RESOLVED.

---

### ISS-023 · 🟢 Both baseline arms were stamped `BASELINE`, making a three-arm metric table impossible

**Phase:** 1
**What happened:** `Arm` had exactly two members, `AGENT` and `BASELINE`, and `AlwaysWait` — the do-nothing control added during Phase 1 — was stamped `BASELINE` for want of anywhere better. Both committed run artifacts therefore carried `"arm": "BASELINE"` on all 2,659 rows, and nothing inside a log distinguished the control from the naive chaser.
**Why it matters:** Not a correctness bug today; `verify_chain` requires one run and one arm per file, so the two never mixed. It was a Phase 2 trap. The metric table has to report three arms — the control recovers **49.3%** of this book with zero contacts, and omitting that floor lets both other arms take credit for money that was arriving regardless. Phase 2 would have had to key on `run_id` string conventions to tell them apart, which is the kind of thing that works until someone renames a run.
**Design consequence:** `Arm.CONTROL` added, with the reasoning for its existence written into the enum docstring rather than left as folklore. Caught in review before Phase 2 depended on it, which is the cheapest possible moment.
**Status:** RESOLVED.

---

*Append below as they happen. Do not wait for phase close.*

---

### ISS-024 · 🟠 The TRAI rule this project intended to cite does not exist in the form it was claimed

**Phase:** 2
**What happened:** `docs/POLICY-SOURCES.md` carried, from ISS-007, the rule *"promotional-category messages only 10:00–21:00 IST"*, attributed to TRAI's TCCCPR and flagged unverified because the source was a vendor blog. Phase 2 read the regulation itself. **TCCCPR contains no such prohibition.** There is no blanket promotional time window anywhere in it. What it contains is a customer *preference* register: Schedule III of TCCCPR 2018 lists nine opt-out time bands, and Note-1 to that table says bands (i), (ii), (iii) and (ix) — `00:00–06:00`, `06:00–08:00`, `08:00–10:00` and `21:00–24:00` — "shall be default OFF for all customers irrespective of the status of registration of customer". The complement of those four bands is 10:00–21:00.

**Why it matters:** the number in the blog is right and its justification is wrong, which is the most dangerous shape a citation can have — it survives a spot check and fails a follow-up question. The true rule is a **default customer preference**, revocable by the customer switching a band on, and it binds **only promotional** communication; Note-4 to the BLOCK PROMO option puts service, transactional and government messages explicitly outside it. Recoup sends no promotional traffic at all, so under the blog's version of the rule the engine would have been enforcing a fictional ban on itself, and under the real version the rule correctly never fires. Invariant 7 exists for exactly this, and this is the first time it has actually caught something.

**What we tried:** four fetches at trai.gov.in returned nothing usable — the TCCCPR landing page, "Advice to Senders" and the UCC FAQ category page all discuss the preference facility without quoting the bands, and both gazette PDFs came back as undecoded binary through the fetcher (5.7 MB and 1.8 MB). The answer only appeared after downloading both PDFs and extracting the text locally with `pypdf`, then grepping for the band table. **Lesson for Phase 4 and 6: an Indian regulator's primary source is a gazette PDF, and a summarising fetch will not read it. Budget for downloading and extracting.**

**Design consequence:** the rule ships as `trai-promotional-window` citing TCCCPR 2018 Schedule III with `verified=True`, and its `scope_caveat` states in the data that it is a default preference rather than a prohibition. `docs/POLICY-SOURCES.md` was rewritten with the verbatim Note-1 text. The rule is structurally dormant on this batch and that is documented rather than engineered around. ISS-007 is closed by this entry.

**Also verified in the same pass, and worth recording so nobody re-researches them:** explicit consent taken to complete a transaction is valid for a maximum of seven days; a sender may re-acquire consent only after ninety days from an opt-out; the `-P`/`-S`/`-T`/`-G` header suffixes are confirmed verbatim; and a Transactional message is one sent "in response to Customer initiated transaction **within thirty minutes** of the transaction" — which independently confirms the Phase 1 reasoning that a payment link chasing a 40-day-old bill is a Service message and never `-T`.
**Status:** RESOLVED — and it closes ISS-007, which was the reason the rule was flagged.

---

### ISS-025 · 🟠 Every decision in every run landed at 08:00, so both contact-window rules were unable to fire

**Phase:** 2
**What happened:** the tick grid is offset to 08:00 precisely so that the RBI window (08:00–19:00) and the TRAI default bands (10:00–21:00) disagree at 08:00 and 20:00 — that offset is a documented Phase 1 decision, taken so each rule would have its own visible moment in the timeline view. It does not work. Intake sets `next_review_tick = 0` for all 126 records, and **every** `review_ticks` value in `domain/interventions.py` (8, 12, 16) is a whole number of virtual days. A record's review phase is therefore fixed at intake and never changes. Measured on the committed Phase 1 artifacts: 495 of 495 baseline decisions and 1,321 of 1,321 control decisions fall at hour 08. Not most. All of them.

**Why it matters:** the headline deliverable of Phase 2 is a policy engine that vetoes with a verified citation on screen. The RBI contact-hour rule is the only regulatory rule on this batch that *can* fire, and it was sitting behind a phase lock that guaranteed it never would. The engine would have been correct, verified, tested, and provably dead. Worse, it would have looked fine: no test failed, and "0 contact-hour vetoes" reads as compliance rather than as a rule that cannot fire.

**What we tried, and rejected:**

1. *Stagger `next_review_tick` in the generator.* Correct, and far too expensive. It changes `batch.json`, so the SHA-256 published in `docs/SEED-DISTRIBUTION.md` changes, the three committed run artifacts stop matching it, and — because the tick is in the adjudicator's hash key — every outcome in the book is redrawn. The 49.3% and 62.3% figures quoted in `CLAUDE.md`, the build log and the README would all have to be re-derived, and the Phase 1 gate re-verified, in the phase that is not allowed to slip.
2. *Stagger at intake inside `run_batch`.* Cheaper, and it breaks replay: `audit.replay` starts from `batch.json`, where `next_review_tick` is 0, so any record the run never acted on would reconstruct with a different review tick. Sharing a staggering helper between the runner and replay is the ISS-017 mistake wearing a different hat.
3. *Give `WAIT` an odd cadence.* Both Phase 1 arms use `WAIT`, so this has the same blast radius as option 1.

**Design consequence:** `PHONE_FOLLOWUP.review_ticks` moved from 16 to **18** — four and a half virtual days rather than four. It is the most intrusive intervention in the space and earns the longest rest, and being a half-day rather than a whole one is what takes a record off the 08:00 phase lock: after a phone call the record's reviews land at 20:00, where the RBI rule bites and the TRAI bands do not. **Neither Phase 1 arm ever proposes `PHONE_FOLLOWUP`**, so the committed artifacts, the published batch hash and every number in the docs are untouched. This is a modelling choice made so that a verified rule is demonstrable, and calling it anything else would be dishonest — the same standard ISS-021 set for the fatigue parameters.

Second consequence: a veto had to become able to reschedule. `record_action(executed=False)` pushes the next review by the *proposed* intervention's interval, which is a whole number of days — so a record vetoed at 20:00 would return at 20:00 and be blocked for the rest of the run. `PolicyVerdict` gained `defer_to_tick`, the ledger gained a `next_review_override`, and replay reads the deferral back out of the logged verdict. A contact-window veto now means "not now", and says when.

**The general lesson:** a rule that has never fired has not been tested, however green its unit test is. The phase lock was found by counting decision hours in a committed log, not by any assertion in the suite. Every rule in `RULE_ORDER` now has its firing count reported in the metric table, so a rule that silently stops firing is visible rather than inferred.
**Status:** RESOLVED.

---

### ISS-026 · 🟠 The Phase 2 gate completed the run but failed while printing a valid UTF-8 report on Windows

**Phase:** 2
**What happened:** the first full `recoup run --seed 42 --arm both` execution produced all three arm artifacts and both metric files, then exited non-zero at the final display step. `metrics.md` correctly used the `₹` label required by the scorecard, but this PowerShell host exposed a CP-1252 stdout stream; Typer raised `UnicodeEncodeError` when it tried to echo the already-written UTF-8 file.

**Why it matters:** a command that writes correct output and then crashes is still a failed gate. It is especially easy to miss here because every substantive computation had completed and the artifact on disk looked fine.

**Resolution:** artifacts remain UTF-8 and keep `₹`. The CLI display path translates that glyph to `Rs ` before writing to the host console, including `recoup metrics --fmt markdown`. This changes presentation only; no stored data or money calculation changes.
**Status:** RESOLVED.

---

### ISS-027 · 🟠 A composed dispute escalation was vetoed by a later rule inspecting the stale original draft

**Phase:** 2
**What happened:** the first full agent probe logged **151 `trai-message-category` vetoes**, even though the deterministic proposer always drafts Service-category messages correctly. `visible-dispute` had already reduced some contacts to `ESCALATE_HUMAN`, but the category rule compared the original Service draft against the *modified* non-message intervention, concluded that an escalation permits no DLT category, and vetoed the whole decision. The human escalation never happened.

**Why it matters:** “modifications compose” means every later rule judges the current intervention, including the fact that a reduced non-contact action will never send the original draft. Looking at one current field and one stale field created a hybrid proposal that never existed. A unit test of either rule alone passed; the per-rule firing count exposed the impossible batch-level pattern.

**Resolution:** the category rule returns `None` once an earlier rule has reduced the current action to an intervention with no message category. A composition test now proves that reductions continue in order, preserve the first modification reason, and stop at the first later veto. The corrected run records 16 visible-dispute escalations and zero category-rule firings, as designed.
**Status:** RESOLVED.



---

### ISS-028 · 🟠 A numeric zero conflated bypassed, disabled, defensive and dormant rules

**Phase:** Phase 2 audit hardening
**What happened:** The canonical table printed `0` for every rule in control
and baseline even though those arms bypass policy, then printed the same `0`
for six policy-enabled rules. Those six represented four different states:
`link-budget` was configured off; `nothing-outstanding` was a defensive guard
behind terminal-state filtering; the two TRAI rules had no erroneous Phase 2
draft to reject; and neither ladder attempted a fourth link or reached a
policy-gated `STOP` within the horizon. The table made those distinctions
invisible. It also combined 223 merchant vetoes and 8 regulatory vetoes into a
single agent count, while 16 merchant modifications were described nearby and
could be mistaken for vetoes. `MERCHANT_POLICY.verified=True` added a related
category error: business configuration has no issuing-body fact to verify.

**Why it matters:** A zero can mean compliance, no opportunity, disabled code
or code that never ran. Presenting them identically weakened the behavioral
evidence and risked a false “verified merchant policy” badge in Phase 5.

**Resolution:** Metrics schema v2 carries `policy_enabled`, rule run-status
notes, payment-link volume, record-count recovery, false-intervention
subtypes, veto provenance, modifications, deferrals and STOP decisions.
Bypassed cells render `bypassed`; disabled and structurally dormant rules say
why. Merchant verification is now `None`/N/A and is enforced by the model.
The report explicitly calls zero agent write-offs 28-day horizon truncation.

**What we rejected:** Changing a proposer merely to make `invoice-link-cap`
fire. The audit inferred that three baseline links were “exactly the trigger,”
but the rule correctly fires on an **attempted fourth** link after three have
already been sent. Neither Phase 2 ladder attempts one. The report records that
truth rather than manufacturing a firing.
**Status:** RESOLVED.

---

### ISS-029 · 🟠 The three-arm comparison changed policy and proposer together

**Phase:** Phase 2 audit hardening
**What happened:** Baseline used `NaiveChaser` with no policy while agent used
the deterministic fallback with `PolicyEngine`. The headline 459 → 157 contact
change therefore could not be attributed separately to policy enforcement and
proposer behavior.

**Why it matters:** Phase 3 replaces the proposer. Without a policy-controlled
baseline, any claimed model gain would remain confounded.

**Resolution:** Added `POLICY_BASELINE`, which runs the **identical**
`NaiveChaser` through a fresh engine. Measured on seed 42: policy alone moves
459 → 161 contacts, 104 → 23 false interventions and 62.3% → 56.5% value
recovery. With policy held constant, the agent moves 161 → 157 contacts,
63 → 66 paid records and 56.5% → 57.8% value recovery, with the same 23 false
interventions. All four logs replay with zero divergences.
**Status:** RESOLVED.

---

### ISS-030 · 🔴 Indian digit grouping made the high-value threshold ten times too large

**Phase:** Phase 2 audit hardening
**What happened:** `MerchantPolicy` documented ₹5,00,000 but encoded
`5_000_000_00` paise — ₹50,00,000. The largest seeded invoice is below that,
so no record could satisfy the rule even if `STOP` were reached.

**Why it matters:** The rule’s prose, generator calibration and code disagreed
while direct tests passed by overriding the threshold to zero.

**Resolution:** The default is now `5_00_000_00` paise (50,000,000), and a
regression test requires it to equal the generator’s
`ESCALATION_REFERENCE_PAISE`. The canonical run still records zero because
policy deferrals prevent either policy arm from reaching `STOP` in 28 days;
that separate horizon condition is annotated in the report.
**Status:** RESOLVED.

---

### ISS-031 · 🟠 The README quickstart regenerated a different book

**Phase:** Phase 2 audit hardening
**What happened:** `recoup generate --seed 42` used the CLI default of 120
records while every canonical run used `BATCH_SIZE=126`. The published
`c903d917…` digest was stated only in prose, repeating ISS-022’s failure mode.

**Why it matters:** The first command a reviewer runs did not reproduce the
book behind any reported number.

**Resolution:** The CLI default is 126, the README spells out `--count 126`,
and a CLI test executes that exact documented command and pins the complete
SHA-256 `c903d91724d1c4566cb5c0a67ecf308eb6a0636772fe4a744a6b3f423188dd6f`.
**Status:** RESOLVED.

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
