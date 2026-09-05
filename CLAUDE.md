# Recoup — working agreement

Razorpay Buildathon, Track 03. Solo, ~7 days. Read `docs/IMPLEMENTATION-PLAN.md` before doing anything.

## Start here (cold session)

**Phases 0–3, Phase 5 and the Phase 6 decision work are complete and their gates are met.** The complete no-LLM floor
is tagged **`v0.1-submittable`**. **Phase 4 is built and its offline half is
verified; one live round trip remains, and it is the user's to run. Phase 6 is
next.** The Phase 5 dashboard is fully offline: five-column summary, named-payer
timeline and filterable raw audit.

Read in this order:

1. `docs/IMPLEMENTATION-PLAN.md` — §0 locked decisions, then Phase 6.
2. `docs/BUILD-LOG.md` — the Phase 5 entry, then the Phase 4 entry.
3. `docs/ISSUES.md` — **ISS-046–048** are the Phase 6 record (**ISS-048 carries
   the hardship decision — read it before claiming anything about harm**),
   **ISS-044–045** the Phase 5 one,
   **ISS-039–042** are the Phase 4 record and **ISS-034–038**
   the Phase 3 one; together they are the best raw material in the file for the
   graded "Build Challenges" answer. ISS-017, ISS-024, ISS-025, ISS-027 and
   ISS-028–031 constrain later phases; ISS-021 remains a live obligation
   (ISS-012 was discharged in Phase 4).
4. `docs/OBSERVATIONS.md` — **OBS-001 and OBS-008 govern what may be claimed
   about the model**, **OBS-009 and OBS-010 what may be claimed about the live
   slice**; OBS-012 governs what a rehearsal log may be said to prove; OBS-005 is the
   measured cost model.
5. This file, below, for the invariants.

**Two run directories, and they mean different things.**

- `runs/seed42/` — the four canonical arms. **Deterministic-fallback output.**
  Control 49.25%, naive baseline 62.34% at 459 contacts, the identical proposer
  behind policy 56.54% at 161, the deterministic agent behind the same policy
  56.72% at 137 with 23 false interventions. Six `rbi-contact-hours` vetoes
  prove the adopted contact rule is live. **No model output appears here and
  these numbers must never be relabelled as an LLM result.**
- `runs/seed42-tiered/` — the same four arms with the agent using **real model
  proposals at first review** and the ladder after. A cost-tiered architecture,
  not a compromise. **54.09% at 89 contacts with 0 scored false
  interventions.** Report it as a harm result with its −3.32-point recovery cost
  stated; never as a recovery beat (ISS-038, OBS-008).

The cache under `data/llm_cache/` is **77 real record proposals and one real
batch insight**, bought for $2.09. Every entry is genuine model output.
**277 tests, all offline. No Anthropic import on the empty-key execution path,
and no network on any test path.**

Setup: `uv sync --extra dev`. Check: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`. Note `ruff format --check` — CI enforces it and the old check line here omitted it.

Dashboard: `recoup dashboard` defaults to the canonical `seed42` evidence and
joins only the sibling tiered agent as a labelled fifth column. Its default
timeline is Netra Optics & Lenses / `ASH-2026-0045`: six `WAIT`s and one
verified RBI-hours veto in the same invoice. It reads local run artifacts only.

## Spending money

The balance is small and a partial cache plus a live key is unbounded spend
(ISS-035). Rules:

- **Every run that is not deliberately buying something takes `--cache-only`
  or `--no-model`.** Without one of them, `recoup run --arm agent` bills for
  every uncached record. `--no-model` reproduces `runs/seed42/`; `--cache-only`
  reproduces `runs/seed42-tiered/`. The committed cache is read regardless of
  whether a key is set, so an empty key is not a guard (ISS-043).
- Buy with `recoup seed-cache`, never with `recoup run`. It is a dry run by
  default and needs `--confirm`.
- Use `--run-id` for any new arm. `runs/seed42/` must not be overwritten.
- **Never change `MODEL`, `RECORD_EFFORT`, the prompts or the schemas** without
  intending to. All four are in the cache contract hash, so a change silently
  invalidates every paid entry.
- Never commit fake transport output as the demo cache.

**Razorpay links are the other scarce resource.** Test mode caps them at 30 per
business and **1 is consumed** (ISS-001 carries the running total — keep it
current). `recoup run --executor live` is a rehearsal against
`FakePaymentLinkClient` unless `--confirm` is passed, so develop and demo
against the fake and spend only on the recorded round trip. A live run also
requires an explicit `--run-id`, and the reconciler refuses to write to
`runs/seed42/` or `runs/seed42-tiered/` whatever it is handed.

Two seams are load-bearing:

- **`PolicyGate`** is implemented by `PolicyEngine`. It receives the full record and ledger, logs every firing source, and can approve, reduce or veto. Do not move policy logic into the reasoner.
- **`Proposer`** receives a **snapshot**, never an `Invoice`, so neither the model nor fallback can read `payer_archetype`, `flags`, `provenance` or `spotlight`. Both the Phase 2 fallback and the Phase 3 `ClaudeReasoner` satisfy it.
- **`Executor`** returns an `ExecutionResult`, so **`LIVE` means a Razorpay object exists for that row** — a property of the action, not of the run. Never restore a per-executor kind: reminders and calls have no live counterpart and would be mislabelled (ISS-041). The scarce link budget is allocated in `executor/budget.py` from a dry run's **revealed** demand, and the `link-budget` policy rule is deliberately untouched from Phase 2 — the cap governs real objects, not dunning strategy (ISS-040, ISS-042).

**Report four arms, not two.** `AlwaysWait` preserves the 49.3% do-nothing
floor. Naive baseline versus the policy baseline isolates policy value; the
policy baseline versus agent isolates proposer value. Never collapse `bypassed` policy
into a numeric zero, and keep the rule run-status annotations beside zero
firings. The cost-tiered arm is a **fifth** column beside these, never a
replacement for the deterministic agent column.

**Invariant 7 remains load-bearing.** The shipped RBI and TRAI sources are verified and must not be weakened; RBI e-mandate claims remain unverified P1 work and must not enter the product unless the mandate lane ships and the issuing-body source is read.

**Done:** the public GitHub push. `main` and the `v0.1-submittable` tag are on `origin` (github.com/KartikB3/recoup-ai). Keep it current — the submission points at it. `.env`, `chat_history.txt` and `docs/research/` stay gitignored and must never be pushed.

**Not done, and it is the gate:** the one live Razorpay round trip. Everything
it needs is built and rehearsed against a fake client; it needs a tunnel, a
dashboard webhook and a browser click, so it is the user's to run. Until it has
been run, **nothing may claim a real payment has been reconciled** — say "built
and verified offline". The procedure is in the README under *Closing the live
loop*.

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
