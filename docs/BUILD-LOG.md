# Recoup — Build Log

What has actually been built, and why it was built that way.
Append-only. One entry per phase close. Newest at the bottom.

**Maintenance:** at the close of every phase, append an entry using the template at the end of this file. Do not edit past entries except to correct a factual error — and note the correction inline if you do.

---

## Status at a glance

| Phase | Name | State | Gate met | Commit / tag |
|---|---|---|---|---|
| 0 | Scaffold & long-lead items | ⬜ not started | — | — |
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
