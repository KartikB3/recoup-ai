# Recoup — working agreement

Razorpay Buildathon, Track 03. Solo, ~7 days. Read `docs/IMPLEMENTATION-PLAN.md` before doing anything.

## Start here (cold session)

**Phase 0 is complete and its gate is met.** Repo is committed locally on `main` (4 commits, clean tree); Razorpay test credentials are verified; `.env` exists and is gitignored. **Phase 1 is next.**

Read in this order:

1. `docs/IMPLEMENTATION-PLAN.md` — §0 locked decisions, §2 the contracts to freeze, §3 Phase 1.
2. `docs/BUILD-LOG.md` — the Phase 0 entry: what exists and why.
3. `docs/ISSUES.md` — 13 findings. ISS-012 is a live Phase 4 risk.
4. This file, below, for the invariants.

**Phase 1 in one line:** domain contracts, seeded generator (120+ records), the free-text corpus, virtual clock, ledger state machine, and the audit replay test — **with no LLM anywhere in it**.

The highest-leverage task in Phase 1 is the **free-text corpus**, not the code. Three focused hours, 25–30 templates with slot variation. If the records carry only amounts and dates, the LLM has nothing to read that a regex couldn't parse, and the whole project collapses into a rules engine. Do not let this get squeezed.

Setup: `uv sync --extra dev`. Check: `uv run ruff check . && uv run mypy && uv run pytest`. The scaffold tests fail loudly if a subpackage is renamed — that is deliberate, five gates reference those paths by name.

**Not done, deliberately:** the public GitHub push. It is the user's call. Nothing in Phases 1–6 depends on it; the submission does.

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
