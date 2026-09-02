# Recoup — working agreement

Razorpay Buildathon, Track 03. Solo, ~7 days. Read `docs/IMPLEMENTATION-PLAN.md` before doing anything.

## Start here (cold session)

**Phases 0–2 are complete and their gates are met.** The complete no-LLM floor is tagged **`v0.1-submittable`**. **Phase 3 is next:** structured reasoner output and the batch-level insight, built over the deterministic fallback path that already runs the full book.

Read in this order:

1. `docs/IMPLEMENTATION-PLAN.md` — §0 locked decisions, then Phase 3.
2. `docs/BUILD-LOG.md` — the Phase 2 entry: the three-arm numbers, rule firings, gate evidence and deviations.
3. `docs/ISSUES.md` — **ISS-017, ISS-024, ISS-025 and ISS-027** carry the lessons that constrain later phases; ISS-012 and ISS-021 remain live obligations.
4. This file, below, for the invariants.

**What Phase 2 left you.** Everything from Phase 1, plus a verified ten-rule policy engine, logged forward-only deferrals, a deterministic snapshot-only agent proposer, complete CLI run/metrics flows, and a committed three-arm run under `runs/seed42/`. The agent recovers **57.8%** with 157 contacts and 23 false interventions; the baseline recovers 62.3% with 459 and 104; control recovers 49.3% with none. Eight `rbi-contact-hours` vetoes prove the verified contact rule is live. All three logs replay with zero divergences. **180 tests. No Anthropic import anywhere on the Phase 2 execution path.**

Setup: `uv sync --extra dev`. Check: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`. Note `ruff format --check` — CI enforces it and the old check line here omitted it.

**Phase 3 in one line:** replace the fixed per-record diagnosis with structured model output and a cache, preserve the existing deterministic fallback, and add the one aggregate insight a per-record path cannot produce.

Two seams are load-bearing:

- **`PolicyGate`** is implemented by `PolicyEngine`. It receives the full record and ledger, logs every firing source, and can approve, reduce or veto. Do not move policy logic into the reasoner.
- **`Proposer`** receives a **snapshot**, never an `Invoice`, so neither the model nor fallback can read `payer_archetype`, `flags`, `provenance` or `spotlight`. The Phase 2 fallback already satisfies it; the Phase 3 client must satisfy the same Protocol.

**Report three arms, not two.** `AlwaysWait` recovers **49.3%** of the book with zero contacts. The naive baseline gets 62.3% for 459 contacts, 225 payment links and 28 cases handed to a human. A metric table without the do-nothing floor flatters whichever arm is being sold.

**Invariant 7 remains load-bearing.** The shipped RBI and TRAI sources are verified and must not be weakened; RBI e-mandate claims remain unverified P1 work and must not enter the product unless the mandate lane ships and the issuing-body source is read.

**Not done, deliberately:** the public GitHub push. It is the user's call. Nothing in Phases 2–6 depends on it; the submission does.

## The rule that outranks everything

**Protect the Phase 2 tag.** `v0.1-submittable` is the complete deterministic floor. Everything after it is upside. If a later change threatens the three-arm gate, replay, or the no-key fallback, the change loses.

If behind schedule: cut from P1, never from P0. Drop order is in `docs/ROADMAP.md`.

## Invariants — never violate these

1. **All money is `int` paise.** Never float, never rupees, anywhere.
2. **All dates are virtual.** No `datetime.now()` in domain, ledger, policy or reasoner code.
3. **The LLM never outputs a rupee amount, a date calculation, or a final decision.** It proposes; the policy engine disposes. Any numeric field on `LLMProposal` that gets used as money or a date is a bug.
4. **The intervention space is a closed enum.** `WAIT | SOFT_REMINDER | PAYMENT_LINK | PHONE_FOLLOWUP | ESCALATE_HUMAN | STOP`. Nothing outside it exists.
5. **The audit log is append-only.** Rows are never updated. Outcomes arrive as new rows.
6. **`runner/batch.py` is the only orchestrator.** Everything else is a component it calls.
7. **Never cite a regulation that is not verified at source.** Every `RuleSource` carries `verified: bool`; unverified rules render with a visible chip and never appear in the video. Merchant policy is labelled merchant policy — never dressed up as regulatory.
8. **The ledger is the system of record, not Razorpay.**

## Documentation protocol — run this at the close of every phase

Four living docs. They are only useful if they stay true.

1. `docs/BUILD-LOG.md` — append the phase entry (template at the bottom of that file): what was built, key decisions and why, gate evidence, numbers.
2. `docs/ISSUES.md` — append every dead end, wrong turn and external constraint hit this phase. **This is a graded submission field** ("Build Challenges & Technical Obstacles"), not housekeeping. Write it for a judge. Log issues *as they happen*, not at phase close — you will not remember them on Day 6.
3. `docs/ROADMAP.md` — re-scope. Move completed items out, slipped items down, add newly discovered ones.
4. `docs/IMPLEMENTATION-PLAN.md` — update the status line at the top; amend later phases if a decision changed.

## Before writing Anthropic SDK code

Load the `claude-api` skill. Do not write SDK calls from memory — several API shapes changed in 2025–26.

Product model config: `claude-opus-5`, adaptive thinking, `output_config: {effort: "medium"}` per record and `"high"` for the batch insight, structured outputs via `messages.parse()`, `betas: ["server-side-fallback-2026-07-01"]` with `fallbacks: "default"`, and always check `stop_reason` before reading content.

## Stack

Python 3.11+ · Pydantic v2 · SQLite · FastAPI (webhook receiver only) · Streamlit (dashboard) · `anthropic` SDK.
