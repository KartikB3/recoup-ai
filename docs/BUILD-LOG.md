# Recoup — Build Log

What has actually been built, and why it was built that way.
Append-only. One entry per phase close. Newest at the bottom.

**Maintenance:** at the close of every phase, append an entry using the template at the end of this file. Do not edit past entries except to correct a factual error — and note the correction inline if you do.

---

## Status at a glance

| Phase | Name | State | Gate met | Commit / tag |
|---|---|---|---|---|
| 0 | Scaffold & long-lead items | ✅ done | ✅ met | `8233ff6`..`702f213` |
| 1 | Generator, clock, ledger (zero AI) | ✅ done | ✅ met | `00b3409`..`7fb21ce` |
| 2 | Policy engine + baseline + metrics | ⬜ not started | — | — |
| 3 | LLM reasoner layer | ⬜ not started | — | — |
| 4 | Razorpay live slice | ⬜ not started | — | — |
| 5 | Dashboard | ⬜ not started | — | — |
| 6 | Evaluation, hardening, submission prose | ⬜ not started | — | — |
| 7 | Video & submission | ⬜ not started | — | — |

Legend: ⬜ not started · 🟡 in progress · ✅ gate met · ⚠️ done but gate not met

---

## Pre-Phase 0 — Planning

**Date:** 2026-09-02
**Model/effort used:** Opus 5, xhigh

**What happened**
Read `recoup-build-spec.md` and the research chat history. Produced `docs/IMPLEMENTATION-PLAN.md`, plus this log, `docs/ISSUES.md` and `docs/ROADMAP.md`.

**Decisions made**

| Decision | Choice | Reasoning |
|---|---|---|
| Language | Python 3.11+ | Simulation, seeded RNG and structured-output parsing all cleanest here; one language end to end. |
| Data layer | SQLite + Pydantic v2 | Zero setup, queryable audit log, JSON Schema for free. |
| Dashboard | Streamlit | Keeps Phase 5 at 0.5 day. The saved day goes into P1 features that actually score. Spec already licenses "ugly-but-real". |
| Product reasoner model | `claude-opus-5`, adaptive thinking, effort `medium` | Per-record triage is not a hard reasoning task; `medium` keeps ~240 calls cheap. Batch-insight call gets `high`. |
| Infra vs product framing | Deferred to Phase 6 | Both affordances get built cheaply in Phase 5 (metric table + one named-payer timeline); the choice is made once the dashboard is real. |

**Open at close of planning**
Everything. No code written.

---

## Phase 0 — Scaffold & long-lead items

**Date:** 2026-09-02
**Model/effort used:** Opus 5
**Gate:** ✅ **met** — repo initialised and committed; `uv run recoup check-razorpay` created a real test-mode Payment Link (`plink_TXAFGZfOooV75R`), confirming credentials end to end. The Support email was dropped by decision, not left undone (ISS-001).
**Commit:** `8233ff6`

**What was built**

- `git init` on `main`, repo skeleton frozen per IMPLEMENTATION-PLAN §1. Python 3.13.5 local, `requires-python = ">=3.11"`.
- `pyproject.toml` — uv/hatchling, deps pinned via `uv.lock`, ruff + mypy strict + pytest configured.
- **26 module stubs**, each carrying a docstring that states its own contract, its phase, and the invariant it enforces. Navigable skeleton, no fake implementations.
- **CLI command surface frozen** (`src/recoup/cli.py`): `generate`, `run`, `metrics`, `replay`, `dashboard`, `check-razorpay`. The signatures are the deliverable — five later phases reference these commands by name in their gates.
- `check-razorpay` **is implemented**, not stubbed: creates one Standard Payment Link and refuses to run against any key not prefixed `rzp_test_`.
- `.env.example` documenting every variable including `RECOUP_LIVE_LINK_BUDGET=30`.
- `.gitignore` excluding `chat_history.txt` and `docs/research/`.
- `README.md` structured judge-first: boundary and metric table above the fold, metrics marked *(pending)*.
- `docs/POLICY-SOURCES.md` and `docs/SEED-DISTRIBUTION.md` seeded for Phases 2 and 1.
- CI (`.github/workflows/ci.yml`): ruff, ruff format, mypy strict, pytest — with `ANTHROPIC_API_KEY: ""` set deliberately, so the Phase 3 no-key gate is enforced by CI from now on rather than remembered on Day 6.
- `tests/test_scaffold.py` — 36 tests.

**Key decisions**

| Decision | Choice | Reasoning |
|---|---|---|
| Package manager | `uv` | Already installed, lockfile is reproducible, and CI setup is two lines. |
| Unimplemented commands | Exit 1 with a message naming the phase and pointing at the plan | Silently succeeding with no output is how a phase gets marked done by accident. |
| Layout enforcement | A test asserts the exact set of subpackages | Later phases fill files in; they do not move them. Drift now fails CI instead of surfacing on Day 4. |
| `chat_history.txt` | Gitignored, kept locally | Carries build strategy and competitive reasoning about other entrants. `recoup-build-spec.md` is committed — it is the design doc and is fine to publish. |
| `check-razorpay` implemented rather than stubbed | It is a Phase 0 gate item, and the test-key guard is worth having before Phase 4 | Cheap, and it makes the gate verifiable rather than a manual note. |
| CI pins `ANTHROPIC_API_KEY=""` | Deliberate | Turns the Phase 3 fallback gate into a standing invariant. |

**Deviations from the plan**

None structural. Two additions the plan did not call for: the CI workflow, and implementing `check-razorpay` rather than stubbing it. Both cost minutes and remove Day-6 risk.

**Numbers**

- 26 stub modules, 10 subpackages, 6 CLI commands
- 36 tests, 0.52s
- ruff clean, `ruff format` clean, mypy strict clean across 39 source files

**Gate evidence**

| Check | Result |
|---|---|
| `git log` | 4 commits on `main`, working tree clean |
| `ruff check` / `ruff format --check` | clean |
| `mypy --strict` | clean, 39 source files |
| `pytest` | 36 passed |
| `recoup check-razorpay` | **live test-mode Payment Link created**, `plink_TXAFGZfOooV75R` |
| `.env` tracked? | no — gitignored and confirmed absent from `git ls-files` |
| `chat_history.txt` tracked? | no — gitignored |

**Link budget consumed:** 1 of 30 (ISS-001). ~11 more projected across the week; see the Phase 4 budget table.

**Carried forward**

1. ~~Email Razorpay Support to raise the 30-link cap.~~ **Dropped 2026-09-02** — the cap is load-bearing for the pitch and 30 is comfortable under the Phase 4 budget. Reasoning in ISS-001.
2. ~~Razorpay credentials smoke test.~~ **Done** — see gate evidence above.
3. **Create the public GitHub repo and push.** Deliberately not done: the repo is committed locally only, and publishing is the user's call. `gh` is authenticated and ready. Nothing in Phases 1–6 depends on this; the submission does.

---

## Phase 1 — Generator, clock, ledger (zero AI)

**Date:** 2026-09-02
**Model/effort used:** Opus 5, xhigh
**Gate:** ✅ **met** — three conditions, each verified:

1. *`--seed 42` produces a byte-identical batch twice.* Verified in **three separate interpreters** under `PYTHONHASHSEED` 0, 1 and 12345, all yielding SHA-256 `c903d917…88dd6f`. The single-process version of this check passes trivially and proves nothing about the hash-order dependence the sorted `flags` serialiser exists to prevent, so the test spawns subprocesses. `tests/test_generator.py::test_byte_identical_across_processes_and_hash_seeds`.
2. *The ledger advances 112 ticks with no LLM and no policy engine.* Two full runs over all 126 records committed under `runs/`. No `anthropic` import exists anywhere on the execution path; `PolicyGate` is a Protocol with no implementation and `run_batch(policy=None)` is the only call made.
3. *The replay test passes.* `uv run recoup replay phase1-baseline` and `… phase1-control` both report **0 divergences**, reconstructing the closing position from `batch.json` plus `audit.jsonl` alone.

**Full check:** `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest` — clean, **164 tests passing**, mypy strict over 40 source files.

**Commit / tag:** `00b3409`..`7fb21ce`

---

**What was built**

- `domain/enums.py` — every closed enumeration, including `RowKind` and a 29-value `SignalKind` whose docstring carries the corpus rule.
- `domain/models.py` — the frozen contracts. `Invoice`, `AuditRow`, `LLMProposal`, `PolicyVerdict`, `ActionRecord`, `OutcomeRecord`, plus `canonical_json` and `to_snapshot`.
- `domain/interventions.py` — the cost and shape of all six interventions, one table, no intervention uncosted.
- `generator/corpus/*.yaml` — **54 templates over 8,333 distinct renderings**, plus 46 invented payers and their contacts.
- `generator/freetext.py` — corpus loading, weighted selection, slot rendering that raises on an undeclared placeholder rather than shipping a literal `{slot}` into a demo.
- `generator/archetypes.py` — the six archetype profiles, sized backwards from the Phase 2 metric table.
- `generator/generate.py` — the seeded batch generator and its on-disk format.
- `ledger/clock.py` — the tick grid and `resolve_promise_phrase`.
- `ledger/ledger.py` — the state machine and the only code permitted to assign `Invoice.state`.
- `ledger/adjudicator.py` — seeded outcome resolution over three independent hash channels.
- `audit/log.py` — the append-only JSONL log and its hash chain.
- `audit/replay.py` — reconstruction from the batch and the log, and nothing else.
- `executor/base.py`, `executor/simulated.py` — the seam a live Razorpay call occupies in Phase 4.
- `baseline/naive_chaser.py` — the baseline arm, and `AlwaysWait`, the do-nothing control.
- `runner/batch.py` — the only tick loop in the project.
- `cli.py` — `generate` and `replay` implemented; `run` still gated to Phase 2 on purpose.
- Tests: 164 across six files.

---

**Key decisions**

| Decision | Choice | Reasoning |
|---|---|---|
| Where Phase 1 orchestration lives | `runner/batch.py` now, CLI `run` still Phase-2-gated | Invariant 6 says one orchestrator. Writing a throwaway test driver would have meant writing the loop twice and throwing away the version that got debugged. The CLI stays gated because a `run` that silently means "baseline only" would be a lie in the demo. |
| Epoch anchored at **08:00**, not midnight | Tick hours are 02, 08, 14, 20 | On a midnight grid the RBI (08:00–19:00) and TRAI (10:00–21:00) windows admit exactly the same ticks and are indistinguishable on screen. Offset by eight hours they disagree at 08:00 and 20:00, so each rule gets its own visible moment in the Phase 5 timeline. |
| Spontaneous payment is its **own hash channel** | Drawn every tick for every non-terminal record, in both arms | If it rode the response path, a record nobody contacted could never pay — WAIT and STOP would be pure concessions and the agent could never win by correctly declining to act, which is the behaviour the project exists to demonstrate. |
| What goes in the adjudicator's hash key | `(seed, invoice_id, tick, channel)` and nothing else | Archetype, intervention, days overdue and contact fatigue all move the *threshold* instead. Same dice, different odds. The moment an arm-dependent term enters the key, the two arms face different luck and the comparison measures the RNG. |
| Terminal states | PAID and WRITTEN_OFF only | EXHAUSTED and HUMAN_QUEUE can still receive payment. A payer on a 45-day cycle pays whether or not anyone chased them. |
| Write-offs | Logged rows, applied by the runner | See ISS-017. A state change the log cannot account for is a hole in the project's central claim. |
| Replay strategy | Re-apply rows through the **ledger's own writers** | Re-deriving state through the pure functions would compare `RecordState` and nothing else, while `recovered_paise` — which the metric table actually reads — diverged silently. |
| Response delay | 2 ticks (12 virtual hours) | Nobody replies in the same instant they are written to. |
| `types-PyYAML` vs. a mypy override | Install the stubs | PyYAML publishes real ones, unlike `razorpay`. See ISS-020. |
| One serialiser for the batch format | `write_run` calls `serialise`, not a fresh dump | The run artifact has to be the same bytes the generator published a hash of. Two serialisers is how a reproducibility claim quietly stops being true. ISS-022. |
| A third `Arm` | `Arm.CONTROL` | The do-nothing control was stamped `BASELINE`, so nothing in a log distinguished it. Phase 2 reports three arms. ISS-023. |

---

**Deviations from the plan**

Four, all additive.

1. **`RowKind` added to `AuditRow`.** The planned field list inferred row type from which optional fields happened to be populated. An explicit `INTAKE | DECISION | OUTCOME` makes the raw audit view filterable and gives replay a real dispatch.
2. **`AuditRow` deliberately has no `resulting_state`.** Storing the answer would make the replay test a comparison of the log against itself. Replay must re-derive.
3. **`Ledger.finalise` was removed, not implemented as planned.** Replaced by `awaiting_write_off()`, with the runner applying and logging each write-off. ISS-017.
4. **`AlwaysWait` control arm added.** Not in the plan. On this book the do-nothing floor is 49.3% recovered, which is higher than anyone expects — and reporting the agent's recovery without that floor would flatter every arm equally.

---

**Numbers**

*The batch, seed 42:*

| | |
|---|---|
| Records / payers | 126 / 46 |
| Book value | Rs 2,52,97,406.40 |
| Amounts | median Rs 1,05,220.60, p90 Rs 5,00,131.20, max Rs 13,18,366.80 |
| Days overdue | median 37, p90 87, max 130 |
| Free text | 99 payer notes, 104 email replies over 76 records, 12 visible disputes |
| **Records with no free text at all** | **17** — silence is a signal |
| Corpus | 54 templates, 8,333 distinct renderings, 53 drawn on seed 42 |
| Prose-only disputes | **6 of 18** — the population a structured-field rule cannot see |
| Above the Rs 5,00,000 escalation reference | 14 |

*The two arms over 112 ticks:*

| | control (`AlwaysWait`) | baseline (`NaiveChaser`) |
|---|---|---|
| Decisions | 1,321 | 495 |
| Contacts | **0** | 459 |
| Payment links | 0 | 225 |
| Recovered | **49.3%** | **62.3%** |
| Records paid | 54 | 70 |
| Human queue | 0 | 28 |
| Written off | 0 | 19 |
| Audit rows | 1,506 | 1,153 |

The 49.3% floor is the most important number in this table. It is what makes
the Phase 2 comparison honest: chasing has to earn its 13 points against
doing nothing, and it buys them with 459 contacts, 225 links and 28 cases
handed to a human.

*Behaviour ordering, measured on seed 42 — the thesis, before any LLM exists:*

| Archetype | Pays on contact | Spontaneous | Reading |
|---|---|---|---|
| `CHRONIC_LATE` | 13.8% | 42% | Chasing genuinely works. The baseline is not a straw man. |
| `RELIABLE_BUT_SLOW` | 4.2% | 85% | Chasing buys almost nothing. WAIT is the right move. |
| `DISPUTING` | 2.4% | 10% | 23.4% of contacts convert into a formal dispute. Chasing is *harmful*. |
| `PAID_UNRECONCILED` | 1.1% | 95% | 44.6% just reply to say so. Every contact is a false intervention. |

Contact fatigue on a `RELIABLE_BUT_SLOW` payer, by prior contacts: pay rate
3.6% → 0.9%, complaint rate 1.8% → 26.8%. The naive arm damages its own book,
and the metric table will show it.

---

**Carried forward**

1. **The public GitHub push.** Still deliberately not done; still the user's call. `gh` is authenticated. Nothing in Phases 2–6 depends on it; the submission does.
2. **`PolicyGate` is a Protocol with no implementation.** Phase 2 fills it. The runner already threads it through, logs the verdict, and treats a veto as a spent review slot with no contact and no budget — so Phase 2 adds a component rather than changing the loop.
3. **`Proposer` is the only seam the agent arm needs.** Phase 3's reasoner satisfies the same Protocol the `NaiveChaser` does, and receives a snapshot rather than an `Invoice`, so it structurally cannot read ground truth.
4. **ISS-021 is a live write-up obligation.** The fatigue parameters were calibrated so the baseline stays credible. A judge is entitled to ask how those numbers were chosen, and Phase 6 should answer it before being asked.
5. **ISS-012 remains a Phase 4 risk.** Untyped `razorpay` responses mean the Phase 4 webhook signature-verification test against a known-good fixture is not optional.

---

## Entry template — copy this for each phase

```markdown
## Phase N — <name>

**Date:**
**Model/effort used:**
**Gate:** ✅ met / ⚠️ not met — <evidence: command run, output, test result>
**Commit / tag:**

**What was built**
- <module>: <one line on what it does>

**Key decisions**
| Decision | Choice | Reasoning |
|---|---|---|

**Deviations from the plan**
<what changed vs docs/IMPLEMENTATION-PLAN.md, and why. If nothing, say "none".>

**Numbers**
<any measurement produced this phase: record counts, recovery rate, veto counts,
cache hit rate, token spend. Even rough ones. Future-you needs these for the README.>

**Carried forward**
<anything left undone that a later phase now depends on>
```
