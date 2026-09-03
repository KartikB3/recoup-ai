# Recoup — working agreement

Razorpay Buildathon, Track 03. Solo, ~7 days. Read `docs/IMPLEMENTATION-PLAN.md` before doing anything.

## Start here (cold session)

**Phases 0–2 are complete and their gates are met.** The complete no-LLM floor
is tagged **`v0.1-submittable`**. **Phase 3 is in progress:** the structured
reasoner, validated cache, failure circuit breaker and policy-approved batch
artifact are implemented. The real model/cache/evaluation gate remains open
because no Anthropic key is configured (ISS-033).

Read in this order:

1. `docs/IMPLEMENTATION-PLAN.md` — §0 locked decisions, then Phase 3.
2. `docs/BUILD-LOG.md` — the Phase 3 checkpoint, then the Phase 2 audit entry.
3. `docs/ISSUES.md` — **ISS-032 and ISS-033** are the current Phase 3 state;
   ISS-017, ISS-024, ISS-025, ISS-027 and ISS-028–031 constrain later phases;
   ISS-012 and ISS-021 remain live obligations.
4. `docs/OBSERVATIONS.md` — **OBS-001 and OBS-003 shape what Phase 3 is allowed to claim**; OBS-005 is its cost model.
5. This file, below, for the invariants.

**What the Phase 3 checkpoint preserves.** Everything from Phase 1–2, plus a post-tag
four-arm comparison under `runs/seed42/`: control, naive baseline, the identical
naive proposer with policy, and agent with policy. Policy alone moves 459 → 161
contacts and 104 → 23 false interventions; with policy held constant, the agent
adds 3 paid records and 1.2 value-recovery points. Eight
`rbi-contact-hours` vetoes prove the adopted contact rule is live. The new
wrapper makes 473 cache lookups on the canonical no-key agent run, performs zero
model calls, and falls back 473 times; all four logs still replay with zero
divergences. **199 tests. No Anthropic
import on the empty-key execution path.**

Setup: `uv sync --extra dev`. Check: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`. Note `ruff format --check` — CI enforces it and the old check line here omitted it.

**To close Phase 3:** configure a key, explicitly approve the estimated first
run spend, seed and commit real structured outputs, rerun for the real 100%
cache gate, and compare model agent vs. policy baseline. Never commit fake
transport output as the demo cache.

Two seams are load-bearing:

- **`PolicyGate`** is implemented by `PolicyEngine`. It receives the full record and ledger, logs every firing source, and can approve, reduce or veto. Do not move policy logic into the reasoner.
- **`Proposer`** receives a **snapshot**, never an `Invoice`, so neither the model nor fallback can read `payer_archetype`, `flags`, `provenance` or `spotlight`. The Phase 2 fallback already satisfies it; the Phase 3 client must satisfy the same Protocol.

**Report four arms, not two.** `AlwaysWait` preserves the 49.3% do-nothing
floor. Naive baseline versus the policy baseline isolates policy value; the
policy baseline versus agent isolates proposer value. Never collapse `bypassed` policy
into a numeric zero, and keep the rule run-status annotations beside zero
firings.

**Invariant 7 remains load-bearing.** The shipped RBI and TRAI sources are verified and must not be weakened; RBI e-mandate claims remain unverified P1 work and must not enter the product unless the mandate lane ships and the issuing-body source is read.

**Not done, deliberately:** the public GitHub push. It is the user's call. Nothing in Phases 2–6 depends on it; the submission does.

## The rule that outranks everything

**Protect the Phase 2 tag.** `v0.1-submittable` is the recoverable deterministic
floor and must not move. The current post-tag gate is four arms, replay, and the
no-key fallback. If a later change threatens those, the change loses.

If behind schedule: cut from P1, never from P0. Drop order is in `docs/ROADMAP.md`.

## Invariants — never violate these

1. **All money is `int` paise.** Never float, never rupees, anywhere.
2. **All dates are virtual.** No `datetime.now()` in domain, ledger, policy or reasoner code.
3. **The LLM never outputs a rupee amount, a date calculation, or a final decision.** It proposes; the policy engine disposes. Any numeric field on `LLMProposal` that gets used as money or a date is a bug.
4. **The intervention space is a closed enum.** `WAIT | SOFT_REMINDER | PAYMENT_LINK | PHONE_FOLLOWUP | ESCALATE_HUMAN | STOP`. Nothing outside it exists.
5. **The audit log is append-only.** Rows are never updated. Outcomes arrive as new rows.
6. **`runner/batch.py` is the only orchestrator.** Everything else is a component it calls.
7. **Never cite a regulation that is not verified at source.** Regulatory
`RuleSource.verified` is a required boolean; unverified sources render with a
visible chip and never appear in the video. It is `None`/N/A for merchant
policy, which is labelled merchant policy — never dressed up as regulatory.
8. **The ledger is the system of record, not Razorpay.**

## Documentation protocol — run this at the close of every phase

Five living docs. They are only useful if they stay true.

1. `docs/BUILD-LOG.md` — append the phase entry (template at the bottom of that file): what was built, key decisions and why, gate evidence, numbers.
2. `docs/ISSUES.md` — append every dead end, wrong turn and external constraint hit this phase. **This is a graded submission field** ("Build Challenges & Technical Obstacles"), not housekeeping. Write it for a judge. Log issues *as they happen*, not at phase close — you will not remember them on Day 6.
3. `docs/ROADMAP.md` — re-scope. Move completed items out, slipped items down, add newly discovered ones.
4. `docs/OBSERVATIONS.md` — review, don't just append. Measured facts that are true and unresolved *by design*, each naming what would change it. Delete an observation that stops being true; if it stopped being true because someone fixed it, it becomes an `ISSUES.md` entry.
5. `docs/IMPLEMENTATION-PLAN.md` — update the status line at the top; amend later phases if a decision changed.

## Before writing Anthropic SDK code

Load the `claude-api` skill. Do not write SDK calls from memory — several API shapes changed in 2025–26.

Product model config: `claude-opus-5`, adaptive thinking, `output_config: {effort: "medium"}` per record and `"high"` for the batch insight, structured outputs via `messages.parse()`, `betas: ["server-side-fallback-2026-07-01"]` with `fallbacks: "default"`, and always check `stop_reason` before reading content.

## Stack

Python 3.11+ · Pydantic v2 · SQLite · FastAPI (webhook receiver only) · Streamlit (dashboard) · `anthropic` SDK.
