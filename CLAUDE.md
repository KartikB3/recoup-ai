# Recoup — working agreement

Razorpay Buildathon, Track 03. Solo, ~7 days. Read `docs/IMPLEMENTATION-PLAN.md` before doing anything.

## Start here (cold session)

**Phases 0 and 1 are complete and both gates are met.** Repo is committed locally on `main`, clean tree. **Phase 2 is next, and it is the phase that outranks everything** — it ends with a complete, submittable system tagged `v0.1-submittable`.

Read in this order:

1. `docs/IMPLEMENTATION-PLAN.md` — §0 locked decisions, §3 Phase 2.
2. `docs/BUILD-LOG.md` — the Phase 1 entry: what exists, the numbers, the four deviations from the plan.
3. `docs/ISSUES.md` — 21 findings. **ISS-017 is the one to read**; ISS-012 and ISS-021 are live obligations.
4. This file, below, for the invariants.

**What Phase 1 left you.** Domain contracts, a 126-record seeded generator, a 54-template corpus, the virtual clock, the ledger state machine, the seeded adjudicator, the append-only log with its hash chain, replay, the executor seam, the naive baseline, a do-nothing control, and the tick loop. 164 tests. No LLM anywhere on the execution path.

Setup: `uv sync --extra dev`. Check: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`. Note `ruff format --check` — CI enforces it and the old check line here omitted it.

**Phase 2 in one line:** verify the TRAI and RBI citations at source, write the policy engine that vetoes, wire it into `run_batch`, and produce the metric table across three arms.

Two seams already exist and are the whole of the work:

- **`PolicyGate`** is a Protocol in `runner/batch.py` with no implementation. `run_batch` already threads it through, logs the verdict on the decision row, and treats a veto as a spent review slot with no contact and no budget. Phase 2 supplies a class, not a loop.
- **`Proposer`** is what both arms already satisfy. It receives a **snapshot**, never an `Invoice`, so nothing implementing it can read `payer_archetype`, `flags`, `provenance` or `spotlight`. Keep it that way; a test enforces it.

**Report three arms, not two.** `AlwaysWait` recovers **49.3%** of the book with zero contacts. The naive baseline gets 62.3% for 459 contacts, 225 payment links and 28 cases handed to a human. A metric table without the do-nothing floor flatters whichever arm is being sold.

**Invariant 7 gates Phase 2's headline feature.** Do not write a rule citing TRAI or RBI until the citation is verified at the issuing body. `RuleSource.verified` is load-bearing and an unverified rule never appears in the video.

**Not done, deliberately:** the public GitHub push. It is the user's call. Nothing in Phases 2–6 depends on it; the submission does.

## The rule that outranks everything

**Protect the Phase 2 gate.** At the end of Phase 2 there is a complete, submittable system with no LLM in it, tagged `v0.1-submittable`. Everything after that is upside. If a change threatens that gate, the change loses.

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
