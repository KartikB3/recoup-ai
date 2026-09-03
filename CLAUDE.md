# Recoup — working agreement

Razorpay Buildathon, Track 03. Solo, ~7 days. Read `docs/IMPLEMENTATION-PLAN.md` before doing anything.

## Start here (cold session)

**Phases 0–3 are complete and their gates are met.** The complete no-LLM floor
is tagged **`v0.1-submittable`**. **Phase 4 is next.**

Read in this order:

1. `docs/IMPLEMENTATION-PLAN.md` — §0 locked decisions, then Phase 4.
2. `docs/BUILD-LOG.md` — the Phase 3 close entry, then Phase 2.
3. `docs/ISSUES.md` — **ISS-034–038** are the Phase 3 record and the best raw
   material in the file for the graded "Build Challenges" answer;
   ISS-017, ISS-024, ISS-025, ISS-027 and ISS-028–031 constrain later phases;
   ISS-012 and ISS-021 remain live obligations.
4. `docs/OBSERVATIONS.md` — **OBS-001 and OBS-008 govern what may be claimed
   about the model**; OBS-002 is an open decision the project owes; OBS-005 is
   the measured cost model.
5. This file, below, for the invariants.

**Two run directories, and they mean different things.**

- `runs/seed42/` — the four canonical arms. **Deterministic-fallback output.**
  Control 49.25%, naive baseline 62.34% at 459 contacts, the identical proposer
  behind policy 56.54% at 161, the deterministic agent behind the same policy
  57.75% at 157 with 23 false interventions. Eight `rbi-contact-hours` vetoes
  prove the adopted contact rule is live. **No model output appears here and
  these numbers must never be relabelled as an LLM result.**
- `runs/seed42-tiered/` — the same four arms with the agent using **real model
  proposals at first review** and the ladder after. A cost-tiered architecture,
  not a compromise. **54.43% at 104 contacts with 0 scored false
  interventions.** Report it as a harm result with its −3.32-point recovery cost
  stated; never as a recovery beat (ISS-038, OBS-008).

The cache under `data/llm_cache/` is **77 real record proposals and one real
batch insight**, bought for $2.09. Every entry is genuine model output.
**204 tests. No Anthropic import on the empty-key execution path.**

Setup: `uv sync --extra dev`. Check: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`. Note `ruff format --check` — CI enforces it and the old check line here omitted it.

## Spending money

The balance is small and a partial cache plus a live key is unbounded spend
(ISS-035). Rules:

- **Every run that is not deliberately buying something takes `--cache-only`.**
  Without it, `recoup run --arm agent` bills for every uncached record.
- Buy with `recoup seed-cache`, never with `recoup run`. It is a dry run by
  default and needs `--confirm`.
- Use `--run-id` for any new arm. `runs/seed42/` must not be overwritten.
- **Never change `MODEL`, `RECORD_EFFORT`, the prompts or the schemas** without
  intending to. All four are in the cache contract hash, so a change silently
  invalidates every paid entry.
- Never commit fake transport output as the demo cache.

Two seams are load-bearing:

- **`PolicyGate`** is implemented by `PolicyEngine`. It receives the full record and ledger, logs every firing source, and can approve, reduce or veto. Do not move policy logic into the reasoner.
- **`Proposer`** receives a **snapshot**, never an `Invoice`, so neither the model nor fallback can read `payer_archetype`, `flags`, `provenance` or `spotlight`. Both the Phase 2 fallback and the Phase 3 `ClaudeReasoner` satisfy it.

**Report four arms, not two.** `AlwaysWait` preserves the 49.3% do-nothing
floor. Naive baseline versus the policy baseline isolates policy value; the
policy baseline versus agent isolates proposer value. Never collapse `bypassed` policy
into a numeric zero, and keep the rule run-status annotations beside zero
firings. The cost-tiered arm is a **fifth** column beside these, never a
replacement for the deterministic agent column.

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
