# Recoup — Build Log

What has actually been built, and why it was built that way.
Append-only. One entry per phase close. Newest at the bottom.

**Maintenance:** at the close of every phase, append an entry using the template at the end of this file. Do not edit past entries except to correct a factual error — and note the correction inline if you do.

---

## Status at a glance

| Phase | Name | State | Gate met | Commit / tag |
|---|---|---|---|---|
| 0 | Scaffold & long-lead items | 🟡 in progress | ⚠️ 2 of 3 items are yours | `8233ff6` |
| 1 | Generator, clock, ledger (zero AI) | ⬜ not started | — | — |
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
**Gate:** ⚠️ **not met** — the code half is done; three items require account access only you have. See "Carried forward".
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

**Carried forward — these three are yours, not mine**

1. **Email Razorpay Support to raise the 30-link test-mode cap.** Highest-latency item in the whole build; nothing else blocks on it. Log the outcome in `ISSUES.md` ISS-001 either way.
2. **Generate Razorpay test-mode API keys**, put them in `.env`, then run `uv run recoup check-razorpay`. That closes the smoke-test half of the gate.
3. **Create the public GitHub repo and push.** Not done — pushing publicly is your call, and `gh` is authenticated and ready when you want it.

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
