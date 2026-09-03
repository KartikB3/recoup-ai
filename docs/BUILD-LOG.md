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
| 2 | Policy engine + baseline + metrics | ✅ done | ✅ met | `v0.1-submittable` |
| 3 | LLM reasoner layer | 🟡 in progress | ⚠️ live model/cache pending | — |
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

## Phase 2 — Policy engine + baseline + metric table

**Date:** 2026-09-02
**Model/effort used:** GPT-5, high
**Gate:** ✅ **met** — `recoup run --seed 42 --arm both` completed all three arms and wrote `runs/seed42/metrics.{json,md}`; `recoup replay seed42/{control,baseline,agent}` returned zero divergences for every arm. The full static and test gate is clean: ruff, `ruff format --check`, mypy strict over 51 source files, **180 tests**.
**Commit / tag:** `v0.1-submittable`

**What was built**

- `policy/rules/` — ten pure rules in the documented fixed order: first veto wins and reductions compose.
- `policy/engine.py` — stateful per-run `PolicyEngine`, with source-stamped verdicts and a configurable `MerchantPolicy`.
- `policy/sources.py` + `docs/POLICY-SOURCES.md` — RBI and TRAI primary-source verification, scope caveats carried in data, and no unverified regulation in the engine.
- `reasoner/fallback.py` — the deterministic Phase 2 agent proposer. It returns the same complete proposal shape the model layer will use, reads structured snapshots only, and deliberately leaves policy decisions to the engine.
- `runner/batch.py`, `ledger/ledger.py`, `audit/replay.py` — ledger-aware adjudication and logged deferrals that replay exactly.
- `metrics/compute.py` + `metrics/report.py` — the full three-arm scorecard in JSON and Markdown, including losses, held-out false interventions, separate human-queue causes, and a count for every rule (including zeroes).
- `cli.py` — `recoup run` and `recoup metrics`; `--arm both` remains compatible and now means control + baseline + agent, with `--arm all` as the explicit spelling.
- `runs/seed42/` — committed opening batch, append-only audit, closing position and summary for all three arms, plus parent-level metrics.
- `tests/test_policy.py`, `tests/test_metrics.py` — direct checks for all ten rules and end-to-end checks for the metric, replay, ground-truth and no-LLM boundaries.

**Key decisions**

| Decision | Choice | Reasoning |
|---|---|---|
| Regulatory scope | The RBI 08:00–19:00 clause is an **adopted standard**, not a claimed legal obligation on trade receivables | The verified circular binds regulated lenders and their recovery agents. The caveat travels with every verdict so the honest version is the rendered version. |
| TRAI time rule | Encode Schedule III's promotional default-OFF preference bands, not a fictional blanket ban | Primary-source verification disproved the project's original claim (ISS-024). Recoup sends service traffic, so this verified rule is correctly dormant on seed 42. |
| Ground-truth boundary | Policy may read observable invoice state and prose fields, never simulation flags or archetypes | A perfect dispute detector would be leakage. The 23 remaining agent false interventions are a required honesty check, not a defect to tune away. |
| Dispute handling | Visible disputes reduce to `ESCALATE_HUMAN`, rather than accumulating vetoes forever | It stops payer contact and places a live commercial objection in front of a person. |
| Deferring vetoes | Store `defer_to_tick` on `PolicyVerdict`, pass it through the ledger, replay it from the row | “Not now” must say when. Recomputing the date in replay would repeat the ISS-017 mistake. |
| Demonstrable contact window | `PHONE_FOLLOWUP.review_ticks` is 18, then the proposer spends one reminder at contact count 4 | The half-day shift creates a real 20:00 proposal. Without the following contact, the RBI rule still fires zero times (ISS-025). |
| Simulated link budget | Off; Phase 4 live runs turn it on | Capping only the policy-governed agent at 30 while the bypass baseline sends 225 links would measure an artificial handicap. |
| Metric denominator | Opening `amount_paise` from INTAKE rows | It pins recovery to the book as received and makes the persisted log, not a live object, the definition. |
| CLI gate | `recoup run`, the installed console script | `python -m recoup.runner` had no module entry point and contradicted the already-frozen CLI surface. The plan now names the real command. |

**Deviations from the plan**

1. **`PolicyGate.adjudicate` gained the live `Ledger`.** Payer-level frequency spans invoices; rebuilding counts inside policy would duplicate the system of record and violate the replay lesson from ISS-017. The runner remains the only loop.
2. **`PolicyVerdict.defer_to_tick` and `Ledger.record_action(next_review_override=...)` were added.** A veto at 20:00 otherwise returns on the same whole-day phase forever. The field is logged and replay consumes it rather than deciding again.
3. **The comparison is three arms, not two.** `both` is retained as the gate-compatible alias for all three because the 49.3% do-nothing floor must appear in every scorecard.
4. **The agent's terminal ladder has six decision rungs (five contacts, then STOP).** The post-phone reminder is load-bearing for the RBI behavioural check; the baseline's five-attempt definition is unchanged.

**Numbers**

| Metric | Control | Baseline | Agent |
|---|---:|---:|---:|
| Recovery rate | 49.3% | **62.3%** | 57.8% |
| Recovered paise | 1,246,014,875 | **1,577,122,615** | 1,461,018,533 |
| Records paid | 54 | **70** | 66 |
| Contacts | **0** | 459 | 157 |
| Payment links | 0 | 225 | 71 |
| False interventions | **0** | 104 | 23 |
| Policy vetoes | 0 | 0 | 231 |
| Agent-selected escalations | 0 | 0 | 16 |
| Human queue from payer response | **0** | 28 | 5 |
| Unresolved / written off | 72 / 0 | 37 / 19 | 60 / 0 |

The agent gives up 4.6 recovery points versus the baseline and reports that loss. In return it uses **65.8% fewer contacts**, makes **77.9% fewer false interventions**, and leaves only 5 payer-caused human-queue cases instead of 28. It still beats doing nothing by 8.5 recovery points.

Recorded agent rule firings: `payer-contact-spacing` 172, `payer-contact-frequency` 51, `visible-dispute` 16, **`rbi-contact-hours` 8**. The other six are explicit zeroes; three are structurally dormant and directly unit-tested. Policy vetoes are 231 because the 16 dispute firings are modifications, not vetoes.

**Gate evidence**

| Check | Result |
|---|---|
| `recoup run --seed 42 --arm both` | exit 0; three arm directories + `metrics.json` + `metrics.md` |
| `recoup replay seed42/agent` | 813 rows, chain verified, 126 records, 0 divergences |
| `recoup replay seed42/baseline` | 1,153 rows, chain verified, 126 records, 0 divergences |
| `recoup replay seed42/control` | 1,506 rows, chain verified, 126 records, 0 divergences |
| Phase 1 regression | control and baseline figures match the committed Phase 1 artifacts exactly |
| No-LLM execution | fresh-process import guard fails on any `anthropic` import; full agent run passes with the key empty |
| `ruff check` / `ruff format --check` | clean |
| `mypy --strict` | clean, 51 source files |
| `pytest` | 180 passed |

**Carried forward**

1. Phase 3 replaces the fixed per-record diagnosis with structured model output and a disk cache; the deterministic proposer remains the no-key fallback and its execution path must stay green.
2. Phase 5 renders `rule_source`, including the verified flag and the RBI scope caveat, on the invoice timeline. The data is already present on every firing row.
3. The public GitHub push is still deliberately deferred to the user. The local tag is the recoverable floor.
4. RBI e-mandate verification remains P1 and is required only if the mandate lane ships.

---

## Phase 2 audit hardening — Phase 3 readiness

**Date:** 2026-09-03
**Model/effort used:** Codex
**Gate:** ✅ met — four canonical runs completed and replayed with zero
divergences; ruff, format check, mypy strict and 183 tests are green.
**Commit / tag:** post-tag hardening commit; `v0.1-submittable` deliberately
left at the original recoverable floor.

**What was built**

- `POLICY_BASELINE`: the exact `NaiveChaser` behind `PolicyEngine`, holding the
  proposer constant so policy value and proposer value can be measured
  separately.
- Metrics schema v2: record recovery, payment links, false-intervention
  decomposition, regulatory/merchant veto provenance, modifications,
  deferrals, STOP decisions, policy-bypass state and a reason beside every zero
  rule count.
- Regulatory verification semantics: `bool` for regulatory sources and
  `None`/N/A for merchant policy, enforced in the domain model.
- Executable documentation contracts: the README’s 126-record command is
  tested against the published seed-42 SHA-256.
- A regression test binding the ₹5,00,000 high-value threshold to the
  generator calibration.

**Key decisions**

| Decision | Choice | Reasoning |
|---|---|---|
| Fourth arm | Identical naive proposer + fresh policy engine | Baseline → policy baseline isolates policy; policy baseline → agent isolates proposer. |
| Dormant rules | Annotate their actual run state | `bypassed`, disabled, defensive and no triggering proposal are not interchangeable zeroes. |
| Invoice cap | Do not manufacture a firing | Three sent links are below the rule’s trigger; it modifies an attempted fourth link, which neither ladder proposes. |
| Veto provenance | Count VETOED rows only; show modifications separately | The agent has 223 merchant + 8 regulatory vetoes, not 239 merchant vetoes. The 16 dispute events are modifications. |
| Zero write-offs | Label horizon truncation | Both policy arms end mid-ladder after deferrals and make zero STOP decisions. |
| Phase 2 tag | Do not move it | The audit asked for post-tag improvements; the tagged floor remains recoverable. |

**Numbers**

| Metric | Control | Baseline | Baseline + policy | Agent |
|---|---:|---:|---:|---:|
| Value recovery | 49.3% | 62.3% | 56.5% | 57.8% |
| Record recovery | 42.9% | 55.6% | 50.0% | 52.4% |
| Records paid | 54 | 70 | 63 | 66 |
| Recovered paise | 1,246,014,875 | 1,577,122,615 | 1,430,366,723 | 1,461,018,533 |
| Contacts | 0 | 459 | 161 | 157 |
| Payment links | 0 | 225 | 56 | 71 |
| False interventions | 0 | 104 | 23 | 23 |
| Disputed / already-paid false contacts | 0 / 0 | 76 / 28 | 8 / 15 | 8 / 15 |
| Regulatory / merchant vetoes | bypassed | bypassed | 0 / 247 | 8 / 223 |
| Policy modifications | bypassed | bypassed | 16 | 16 |
| STOP decisions | 0 | 36 | 0 | 0 |
| Unresolved / written off | 72 / 0 | 37 / 19 | 63 / 0 | 60 / 0 |

**Gate evidence**

| Check | Result |
|---|---|
| `recoup run --seed 42 --arm both` | exit 0; four arm directories + schema-v2 metric reports |
| replay control / baseline / policy baseline / agent | 1,506 / 1,153 / 763 / 813 rows; all chains verified; zero divergences |
| documented generate command | 126 records; SHA-256 `c903d91724d1c4566cb5c0a67ecf308eb6a0636772fe4a744a6b3f423188dd6f` |
| `ruff check` / `ruff format --check` | clean |
| `mypy --strict` | clean, 51 source files |
| `pytest` | 183 passed |

**Carried forward**

1. Phase 3 begins from the four-arm contract and must preserve the no-key
   deterministic path.
2. The canonical agent run has 472 decision rows. Snapshot hash inputs change
   every review, so the disk cache accelerates repeated runs and powers the
   offline demo; it does not reduce first-run calls within a run.
3. The two TRAI rules become meaningful guards once the Phase 3 model drafts
   and classifies messages. Zeroes should remain zero unless the model errs.
4. The public GitHub push remains the user’s decision.

---

## Phase 3 checkpoint — structured reasoner implementation

**Date:** 2026-09-03
**Model/effort used:** Codex; product calls configured for Claude Opus 5 at
`medium` per record and `high` for the aggregate insight
**Gate:** ⚠️ **partially met** — the complete no-key run, replay gate, static
checks and full-book cache behavior are green. A real Anthropic call, committed
model-output cache and model-vs-policy-baseline comparison remain blocked by an
unconfigured `ANTHROPIC_API_KEY` (ISS-033).
**Commit / tag:** working tree checkpoint; `v0.1-submittable` remains untouched.

**What was built**

- `reasoner/client.py` — Claude Opus 5 structured proposer with adaptive
  thinking, exact effort settings, prompt caching, server-side refusal fallback,
  stop-reason validation, a three-failure circuit breaker and lazy SDK import.
- `reasoner/cache.py` — disk cache under committed `data/llm_cache/`, with
  canonical-input SHA-256 filenames and a separate contract hash over prompt,
  schema, model and effort. Only successful model output is cached.
- `reasoner/prompts.py` + `schemas.py` — frozen system prefixes, the closed
  intervention space, no-money/no-date constraints, the Phase 1 `LLMProposal`
  contract, and a validated aggregate insight/verdict contract.
- `reasoner/batch_insight.py` — deterministic offline aggregate fallback over
  the same snapshot-only boundary.
- `PolicyEngine.adjudicate_batch` — independently validates that a suppression
  recommendation covers the complete open parent group, contains only live
  ledger IDs and spans the configured invoice/payer breadth.
- `runner/batch.py` + CLI — the runner remains the only orchestrator; agent runs
  use cached/model/fallback reasoning and persist `batch-insight.json` beside
  the replayable log.
- `tests/test_reasoner.py` — 16 focused tests, including exact SDK request shape,
  refusal-before-content handling, cache invalidation, circuit breaking,
  hallucinated aggregate IDs, no-SDK empty-key execution and a full-book fake
  transport whose second identical run is 100% cached.

**Key decisions**

| Decision | Choice | Reasoning |
|---|---|---|
| Python SDK shape | `beta.messages.parse(output_format=PydanticType, output_config={"effort": ...})` | This is the installed Anthropic 1.3 contract. Passing the Pydantic type as `output_config.format` is not the helper API (ISS-032). |
| Cache key vs. contract | Filename hashes canonical input; entry separately hashes prompt/schema/model/effort | Preserves the promised input-key layout while making every contract change a safe miss. |
| What gets cached | Successful validated model output only | Caching fallback output would prevent a later keyed run from ever reaching the model. |
| Empty key | Read disk cache, then fall back without importing `anthropic` | A fresh clone and CI remain independent of both network and hidden SDK credential sources. |
| Repeated API failure | Open a run-local circuit after three consecutive failures | An invalid key or outage must not produce 473 doomed attempts. |
| Aggregate execution | Persist proposal + policy verdict with `applied_to_ledger: false` | Phase 3 builds the decision artifact; Phase 6 applies and renders it. The current metrics must not imply suppression that did not happen. |

**Numbers**

- Canonical no-key agent: 473 cache lookups (472 record decisions + one batch
  call), 0 model calls, 473 deterministic fallbacks.
- Canonical Phase 2 behavior unchanged: 57.8% value recovery, 66 paid records,
  157 contacts, 23 false interventions, 231 vetoes.
- Aggregate fallback: all 9 invoices under `GRP-SURYODAYA`; policy verdict
  `APPROVED`, final action `ESCALATE_HUMAN`, not yet applied to the ledger.
- Test transport: first one-tick full-book run populates every successful call;
  the second identical run has 100% disk hits and zero client calls.

**Gate evidence**

| Check | Result |
|---|---|
| `ANTHROPIC_API_KEY="" recoup run --seed 42 --arm all` | exit 0; original four-arm numbers preserved; model calls 0 |
| replay control / baseline / policy baseline / agent | 1,506 / 1,153 / 763 / 813 rows; all chains verified; zero divergences |
| structured request contract | exact model, adaptive thinking, effort, Pydantic output type, cache marker and fallback beta asserted |
| second identical full-book fake-transport run | 100% disk-cache hits; zero API-client calls |
| real model/cache run | **not run** — no Anthropic key configured; no synthetic entry committed |
| ruff / format / mypy | clean at checkpoint |
| pytest | 199 tests after Phase 3 additions |

**Carried forward**

1. Configure `ANTHROPIC_API_KEY`, approve the estimated first-run API spend,
   run the agent arm once to seed real cache entries, run it again for the real
   100% cache gate, and compare it against the policy baseline. Do not mark the
   phase complete before this evidence exists.
2. Phase 6 applies the approved aggregate suppression to the ledger and renders
   it. Until then `applied_to_ledger` remains false.
3. The public GitHub push remains the user's decision.

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
