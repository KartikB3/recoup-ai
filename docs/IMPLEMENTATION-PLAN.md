# Recoup — End-to-End Technical Implementation Plan

**Track 03: AI Revenue Recovery · Razorpay Buildathon · Solo · ~7 days**
Companion to `recoup-build-spec.md` (the *what*). This is the *how*.

Status: **Phase 0 in progress** — scaffold committed (`8233ff6`); gate open on the Razorpay support email, the credentials smoke test, and the public push.
Last updated: 2026-09-02

---

## 0. Locked decisions

These were open in the spec. They are now closed. Do not relitigate mid-build.

| Decision | Choice | Why |
|---|---|---|
| Language | **Python 3.11+** | Simulation, seeded RNG, state machines and structured-output parsing are all cleanest here. One language across generator → ledger → policy → reasoner → dashboard. |
| Data layer | **SQLite + Pydantic v2** | Single file, zero setup, queryable audit log, trivially committable fixtures. Pydantic gives you the JSON Schema for structured outputs for free. |
| Dashboard | **Streamlit** | Three views in ~half a day. The spec explicitly licenses "ugly-but-real" for the audit view. Phase 5 stays at 0.5 day, and the saved day goes into P1 features that actually score. |
| Webhook receiver | **FastAPI** (single file, ngrok/cloudflared tunnel) | Only needed for the Razorpay live slice. Kept out of the dashboard process deliberately. |
| Product reasoner model | **`claude-opus-5`**, adaptive thinking, `effort: "medium"` | See §5. |
| Framing (infra vs product) | **Deferred to Phase 6**, per your call | Phase 5 must therefore build *both* affordances cheaply: the metric table (infra) and a single named-payer timeline (product). Costs ~1 extra hour, buys the option. |
| Repo | Public GitHub, `git init` in Phase 0 | This directory is **not currently a git repo**. |

**The one constraint that outranks everything else:** the Phase 2 gate. At the end of Phase 2 you have a complete, submittable system with **no LLM in it**. Every phase after that is upside, not risk. If a phase threatens the Phase 2 gate, the phase loses.

---

## 1. Repository layout

Freeze this in Phase 0. Later phases fill in files; they do not move them.

```
recoup/
├── README.md                    # judge-facing. Boundary + metric table above the fold.
├── CLAUDE.md                    # working agreement + doc-maintenance protocol
├── pyproject.toml
├── .env.example                 # RAZORPAY_KEY_ID / _KEY_SECRET / _WEBHOOK_SECRET, ANTHROPIC_API_KEY
├── docs/
│   ├── IMPLEMENTATION-PLAN.md   # this file
│   ├── BUILD-LOG.md             # what has been built (living)
│   ├── ISSUES.md                # obstacles + dead ends (living, GRADED — see §7)
│   ├── ROADMAP.md               # what is left + what could come next (living)
│   ├── SEED-DISTRIBUTION.md     # generator README (Phase 1 deliverable)
│   └── POLICY-SOURCES.md        # every rule → its citation, with verification status
├── src/recoup/
│   ├── domain/                  # models.py  enums.py  interventions.py   ← frozen contracts
│   ├── generator/               # generate.py  archetypes.py  corpus/*.yaml
│   ├── ledger/                  # ledger.py  clock.py  adjudicator.py
│   ├── policy/                  # engine.py  rules/  sources.py
│   ├── reasoner/                # client.py  prompts.py  schemas.py  cache.py  fallback.py  batch_insight.py
│   ├── executor/                # base.py  simulated.py  live_razorpay.py  budget.py
│   ├── audit/                   # log.py  replay.py
│   ├── baseline/                # naive_chaser.py
│   ├── metrics/                 # compute.py  report.py
│   └── runner/                  # batch.py        ← the tick loop, the only orchestrator
├── webhook/app.py               # FastAPI, signature verification, reconcile → ledger
├── dashboard/                   # app.py + views/{summary,timeline,audit}.py
├── data/batches/                # committed seeded batches (JSON)
├── data/llm_cache/              # committed reasoner cache, keyed by input hash.
│                                #   COMMITTED ON PURPOSE: this is what makes the
│                                #   demo work with the API down.
├── runs/                        # per-run audit logs (JSONL) + metrics (JSON)
└── tests/
```

Rule: **`runner/batch.py` is the only module that orchestrates.** Everything else is a pure-ish component it calls. This is what makes the baseline arm a 40-line file instead of a fork of the whole system.

---

## 2. Contracts to freeze in Phase 1

These five shapes are the interfaces every later phase depends on. Getting them wrong on Day 1 costs a day on Day 4. Review them before writing Phase 2.

### 2.1 `Invoice` — the record

```
invoice_id, parent_group_id, payer_id, payer_name, payer_archetype,
amount_paise: int,              # integers only, never float, never rupees
issued_on: VirtualDate, due_on: VirtualDate,
state: RecordState, source: Literal["INVOICE", "FAILED_PAYMENT", "FAILED_MANDATE"],
history: list[PaymentEvent],
free_text: FreeText,            # ← the LLM's entire reason for existing
flags: set[Flag],               # DISPUTED, ALREADY_PAID_UNRECONCILED, HARDSHIP_CLAIMED
contact_ledger: ContactLedger   # counts + timestamps, owned by the policy engine
```

`FreeText` = `{payer_notes: str, email_replies: list[EmailReply], dispute_description: str | None}`.

**All money is `int` paise. All dates are virtual.** No exceptions anywhere in the codebase.

### 2.2 `LLMProposal` — reasoner output

Pydantic model → JSON Schema → `output_config: {format: ...}`, read back with `client.messages.parse()`.

```
diagnosis: str
intervention: Intervention             # closed enum, spec §4
confidence: float                      # 0..1
reasoning: str
drafted_message: DraftedMessage | None # {channel, category: P|S|T|G, body}
extracted_promise: PromiseToPay | None # {relative_phrase, quote}
```

**Hard schema constraint:** no numeric field the LLM fills is ever used as money or as a date. The ledger resolves `relative_phrase` → a tick **deterministically**; the LLM only quotes the span it found. Enforce with a unit test that asserts no arithmetic happens on reasoner output.

### 2.3 `PolicyVerdict`

```
verdict: APPROVED | MODIFIED | VETOED
original: Intervention
final: Intervention | None
rule_id: str | None                 # the FIRST rule that fired
rule_source: RuleSource             # {kind: REGULATORY|MERCHANT, title, date, url, verified: bool}
explanation: str                    # rendered verbatim in the UI
```

`verified: bool` is load-bearing — it is what stops an unverified citation reaching the video. A rule with `verified=False` must render in the dashboard with a visible "unverified" chip.

### 2.4 `AuditRow` — append-only JSONL

Exactly the eight fields in spec §6, plus `run_id`, `arm: AGENT|BASELINE`, `row_id`, `prev_row_hash`.

**Acceptance test — write it in Phase 1, before there is anything to replay:** `replay.reconstruct(invoice_id, log)` returns the invoice's final state, and it must equal the ledger's state. If those two ever diverge, the log is wrong. Run it over all 120 records in CI.

### 2.5 `Intervention` — closed enum

`WAIT | SOFT_REMINDER | PAYMENT_LINK | PHONE_FOLLOWUP | ESCALATE_HUMAN | STOP`. Nothing outside this list exists anywhere in the codebase. The reasoner's structured-output schema uses this enum, so the model physically cannot propose anything else.

---

## 3. Phases

Estimates assume solo, focused days. "Gate" = do not proceed until true.

---

### Phase 0 — Scaffold & long-lead items

**~2 hours. Do this before anything else, including reading further.**

1. `git init`, public GitHub repo, `pyproject.toml`, package skeleton per §1, `.env.example`.
2. Create the four living docs (`BUILD-LOG`, `ISSUES`, `ROADMAP`, this plan) + `CLAUDE.md` maintenance protocol.
3. **Email Razorpay Support asking to raise the 30-link test-mode cap.** Five minutes of work, days of latency, nothing else blocks on it. Do it in hour one. Log the outcome in `ISSUES.md` either way.
4. Razorpay test-mode account: generate API keys, confirm you can create one Payment Link with `curl`. A 10-minute smoke test that de-risks all of Phase 4.
5. Seed `ISSUES.md` with the five constraints already discovered — they are research, not guesses. See §7. *(Already done.)*
6. **Decide what happens to `chat_history.txt` before the first public push.** It contains build strategy and competitive reasoning about what other entrants are likely to do. Either move it to `docs/research/` deliberately, add it to `.gitignore`, or keep it outside the repo. `recoup-build-spec.md` is fine to publish — it is the design doc. This is a one-line decision that is much cheaper now than after the repo is public.

**Gate:** repo pushed, one Payment Link created by hand in test mode, support email sent.

**Model/effort:** `Sonnet 5`, effort `medium`. Purely mechanical.

---

### Phase 1 — Foundation: generator, clock, ledger. Zero AI.

**~1 day.**

| Task | Notes |
|---|---|
| `domain/` — the five contracts in §2 | Freeze these. Review before Phase 2. |
| `generator/archetypes.py` | Six archetypes per spec §1, each with a distribution over amount, days overdue, prior payment behaviour, reply propensity. |
| `generator/corpus/` — **the free-text corpus** | The single highest-leverage task of the week. See below. |
| `generator/generate.py` | Seeded (`--seed 42`), reproducible, 120+ records, deterministic output committed to `data/batches/`. |
| The cluster event | 9 invoices, one `parent_group_id`, all silent within the same week, with free text that *hints* at a procurement freeze without naming it. The LLM must infer it — if a note literally says "procurement freeze", the insight is worthless. |
| `ledger/clock.py` | Discrete ticks. **One tick = 6 virtual hours**, which gives you intra-day resolution for the RBI 08:00–19:00 contact rule. 28 virtual days = 112 ticks. |
| `ledger/ledger.py` | The state machine in spec §2. State transitions are the *only* way state changes. |
| `ledger/adjudicator.py` | Seeded outcome resolution: P(pay), P(reply), P(dispute) conditioned on archetype × intervention × days-overdue. **Same seed ⇒ same outcomes**, so baseline and agent face an identical world. |
| `docs/SEED-DISTRIBUTION.md` | Write it now, while the numbers are in your head. |
| Audit replay test | §2.4. Written before there is anything to replay. |

**On the free-text corpus — read this twice.** If your records carry only amounts and dates, the LLM has nothing to read that `if days_overdue > 30` couldn't parse, and a judge spots it in the first minute. You need genuinely varied Indian B2B accounts-payable voice: *"payment is in this week's run, please share SOA"*; *"we have not received the GST invoice, cannot process"*; *"kindly note our vendor payment cycle is 45 days from GRN"*; partial-payment confusion; a wrong-PO-number dispute; a polite stall that is actually a hardship signal; and one payer who already paid and is annoyed at being chased. Write **25–30 templates with slot variation**, not 120 one-offs. Budget three focused hours. It is the least glamorous task of the week and the one most likely to decide the outcome.

**Gate:** `python -m recoup.generator --seed 42` produces a byte-identical batch twice. Ledger advances 112 ticks with no LLM and no policy engine. Replay test passes.

**Model/effort:** `Opus 5`, effort `xhigh`, for the domain contracts, adjudicator probabilities and state machine. For the **free-text corpus specifically**, consider `Fable 5` at effort `medium` — it is pure high-variance creative writing, which is exactly where a step up in model shows. Skip it if cost matters; Opus 5 `xhigh` is fine.

---

### Phase 2 — Policy engine + baseline + metric table. **THE MILESTONE.**

**~1 day. Protect this above everything.**

| Task | Notes |
|---|---|
| `policy/rules/` — one file per rule | Each rule is a pure function `(record, proposal, world) -> PolicyVerdict \| None`. Returns `None` if it does not fire. |
| `policy/engine.py` | Runs rules in a **fixed, documented order**; first veto wins; modifications compose. The order is part of the spec, not an implementation detail — write it down. |
| `policy/sources.py` + `docs/POLICY-SOURCES.md` | Every rule carries `RuleSource` with `verified: bool`. |
| **Verification tasks — do them now, not on Day 6** | ① TRAI promotional window 10:00–21:00 → confirm at trai.gov.in. ② RBI Fair Practices 08:00–19:00 contact rule, Aug 2022 outsourcing circular → confirm at rbi.org.in. These two are P0 because they gate contact. The RBI E-mandate Framework 2026 rules are **P1** — they only apply if you build the mandate lane, so do not burn Phase 2 time on them. |
| `baseline/naive_chaser.py` | Contact every 3 days until paid or 5 attempts. **Runs through the same runner, the same ledger, the same seed — and bypasses the policy engine.** That bypass is the whole point: the baseline is what generates the false interventions the agent avoids. |
| `metrics/compute.py` + `report.py` | The full table from spec §7a, including the rows where you lose. Emits JSON + Markdown. |
| `runner/batch.py` | Tick loop, arm-agnostic. In Phase 2 the "reasoner" is a stub returning a fixed policy-driven proposal. |

**Merchant-policy rules — label them merchant-configured, never regulatory:** max 4 contacts / payer / 30 days; ≥72h spacing; max 3 payment links / invoice; hard stop on `DISPUTED`; escalate above a configurable value; global 30-link API budget. **Do not invent a regulatory retry cap** — no verified source exists, and getting caught inventing a regulation is worse than citing none.

**Gate — the one that matters:** `python -m recoup.runner --seed 42 --arm both` runs end to end and produces `runs/<id>/metrics.md` with both arms filled in, and **you could submit this today**. Tag the commit `v0.1-submittable`. Write the Phase 2 entry in `BUILD-LOG.md` before moving on.

**Model/effort:** `Opus 5`, effort `xhigh` throughout; step up to `max` for the rule-ordering logic and the metrics computation — an off-by-one in "contacts per ₹ recovered" is exactly the kind of error that survives all the way to the video. Use WebSearch/WebFetch for the two verification tasks; never answer a citation from memory.

---

### Phase 3 — LLM layer

**~1 day. Everything here is upside; the Phase 2 tag is your floor.**

| Task | Notes |
|---|---|
| `reasoner/schemas.py` | Pydantic → JSON Schema → `output_config: {format: ...}`. Read back with `client.messages.parse()`. |
| `reasoner/prompts.py` | System prompt carries the intervention space, the policy rules (so the model proposes *plausible* actions), and the "you never output a rupee amount or a date" constraint. **Put the frozen system prompt first and cache it** — prefix caching is what makes 120 records × 2 arms affordable. |
| `reasoner/cache.py` | Cache by SHA-256 of the canonical input snapshot. Disk-backed at `data/llm_cache/`, **committed to the repo**. This makes runs reproducible *and* makes the demo work with the API down. Do not let this become an untracked directory — the offline gate silently depends on it. |
| `reasoner/fallback.py` | Deterministic path for when the API errors, times out, or refuses. **Assume the API is down while you record the video.** Branch on a falsy-or-missing key, not on key absence. CI runs the suite with `ANTHROPIC_API_KEY: ""` so this stays true. |
| `reasoner/batch_insight.py` | The §7b call: one prompt over the aggregate, run at effort `high`. Detects the parent-group cluster and returns a suppression recommendation which the **policy engine still has to approve**. |
| Re-run and compare | Agent vs baseline on seed 42. If the agent does not beat the baseline, that is a *finding* — investigate before adding features. Log it in `ISSUES.md` either way. |

**Model config for the product itself:** `claude-opus-5`, `thinking: {type: "adaptive"}`, `output_config: {effort: "medium"}`. Per-record triage is not a hard reasoning problem, and `medium` keeps 240 calls cheap; the batch-insight call gets `high`. Set `betas: ["server-side-fallback-2026-07-01"]` with `fallbacks: "default"`, and always check `stop_reason` before reading content. `claude-haiku-4-5` is a reasonable degraded tier between Opus and the deterministic fallback — build it only if Phase 3 finishes early.

**Load the `claude-api` skill before writing any of this code.** Do not write SDK calls from memory; several API shapes changed in 2025–26.

**Gate:** the full batch runs with `ANTHROPIC_API_KEY` **empty or unset** and completes via the fallback path. Cache hit rate is 100% on a second identical run.

> Empty and unset are different conditions and `fallback.py` must branch on **falsy-or-missing**, not on `"ANTHROPIC_API_KEY" not in os.environ`. An empty value still outranks every other credential source rather than falling through to a profile, which makes it the stricter test — so that is the one CI runs.

**Model/effort for building it:** `Opus 5`, effort `xhigh`.

---

### Phase 4 — Razorpay live slice

**~0.75 day.**

| Task | Notes |
|---|---|
| `executor/live_razorpay.py` | Standard Payment Links API, server-side, test mode. |
| `executor/budget.py` | Global budget (30, or whatever Support granted). **The agent must allocate the scarcity** — highest-expected-recovery invoices get the real links. This is the sentence that turns the cap into a feature; make sure the code actually implements allocation rather than taking the first 30. |
| `webhook/app.py` | FastAPI, `razorpay_signature` HMAC verification, idempotent by `payment_id`, reconciles into the ledger as an ordinary state transition. |
| Callback URL verification | The synchronous half of the loop. |
| Log every real API call | Marked `executor: LIVE` in the audit log. Judges should be able to see exactly which rows were real. |

**Known-closed doors — do not spend time here:** UPI Payment Links (unsupported in test mode), error-simulation cards (browser-bound), Recurring Payments S2S (needs account activation), subscription retry (3-day token expiry; halted subscriptions issue an invoice instead of charging). These are already in `ISSUES.md` and they *are* your Build Challenges answer.

**Gate:** one real test-mode Payment Link created by the agent, paid on the mock page, webhook received, ledger moved to `PAID`, audit row written. **Screen-record this the moment it works** — it is your 3:15 video beat and you do not want to be reproducing it on Day 7.

**Model/effort:** `Opus 5`, effort `high`. Signature verification is the one place where correctness is absolute — do that function at `max` and write a test against a known-good fixture.

---

### Phase 5 — Dashboard

**~0.5 day. Hard stop.**

Three views, in this priority order:

1. **Batch summary** — the frame the video opens on. Baseline vs agent side by side, losses included. Spend your design effort here.
2. **Single-invoice timeline** — virtual weeks, one row per tick, including at least one `WAIT` and one `VETO` with its `rule_source` rendered on screen. This is the 1:30 and 2:15 beats.
3. **Raw audit view** — ugly-but-real beats pretty-but-fake. A filterable table over the JSONL.

**Because framing is deferred to Phase 6:** build the timeline view keyed by payer *name*, not invoice ID, and pick one memorable payer in the seed data. That single choice costs an hour and keeps the product framing available without committing to it.

**Gate:** all three views run off `runs/<id>/` with no live API calls. The dashboard must work offline.

**Model/effort:** `Sonnet 5` at effort `high` for Streamlit plumbing and the audit table — well-trodden framework code. Switch to `Opus 5` plus the `frontend-design` skill for the batch-summary view only. Consider `/fast` here; the iteration loop is tight and visual.

---

### Phase 6 — Evaluation, hardening, submission prose

**~1 day.**

| Task | Priority |
|---|---|
| Batch-level insight (built in Phase 3) wired end to end and visible in the dashboard | **P0** (spec §7b) |
| **Abstention** — below a confidence threshold → `ESCALATE_HUMAN`, logged as an abstention, not a failure | P1, high value. Showing the agent decline to act is a stronger moment than showing it act. |
| **Kill switch** — anomaly (veto rate spikes, or > N disputes in one tick) → agent halts itself → dashboard shows why | P1. This is your "one failure handled gracefully". |
| **Promise-to-pay** — free text → LLM extracts the phrase → ledger resolves the date deterministically → contact suppressed until then → checked → one-step escalation if broken | P1, most memorable feature on the list |
| Failed-payment / mandate intake into the same ledger | P1, keeps you inside payments vocabulary |
| **README** — boundary (§6) and metric table (§7a) above the fold | **P0** |
| Draft all seven submission-form answers | **P0** — today, not Day 7 |
| **Decide the framing** (infra vs product) now that you can see the dashboard | **P0** |
| `ISSUES.md` → Build-Challenges prose | **P0** — this is a graded field |
| Feature freeze at end of day | — |

**Gate:** feature freeze. No code after this except bug fixes.

**Model/effort:** `Opus 5` effort `xhigh` for the batch insight, abstention and kill switch — novel logic with subtle interactions with the policy engine. `Opus 5` effort `high` for the README and submission prose; it is persuasive writing against a known rubric, and `xhigh` buys nothing there.

---

### Phase 7 — Video and submission

**~1 day. No code.**

Beat sheet is in spec §10. Record the Razorpay live slice separately — you already have Phase 4's capture as insurance. Everything else runs off committed run artifacts, offline, from the cache. Which is precisely why Phase 3 built the cache.

**Model/effort:** `Opus 5`, effort `medium`, for script tightening and the submission-form answers. Buffer the rest of the day for what breaks.

---

## 4. Schedule against the seven days

| Day | Phases | Slack |
|---|---|---|
| 1 | Phase 0 + Phase 1 | tight |
| 2 | **Phase 2 → tag `v0.1-submittable`** | protect at all costs |
| 3 | Phase 3 | — |
| 4 | Phase 4 (0.75d) + start Phase 5 | some |
| 5 | Phase 5 finish + start Phase 6 | some |
| 6 | Phase 6, feature freeze | — |
| 7 | Phase 7 | all of it is buffer |

**If you are behind: cut from P1, never from P0.** Drop in this order: mandate intake → promise-to-pay → kill switch → abstention → live Razorpay slice. Never drop the metric table, the veto-with-source, or the batch insight.

---

## 5. Model & effort — consolidated recommendation

### 5.1 For driving Claude Code during the build

| Phase | Model | Effort | Rationale |
|---|---|---|---|
| 0 · Scaffold | `Sonnet 5` | `medium` | Mechanical. Directory trees and config files. |
| 1 · Domain, generator, ledger | `Opus 5` | `xhigh` | The contracts here are load-bearing for five later phases. |
| 1 · Free-text corpus *(sub-task)* | `Fable 5` *(optional)* | `medium` | Pure high-variance creative writing — the one place a model step-up genuinely shows. Skip if cost matters. |
| 2 · Policy engine, baseline | `Opus 5` | `xhigh`, → `max` for rule ordering & metrics | The core of the product and the thing being graded. |
| 2 · Regulatory verification | `Opus 5` + WebSearch/WebFetch | `high` | Never answer a citation from memory. |
| 3 · LLM layer | `Opus 5` | `xhigh` | Load the `claude-api` skill first. |
| 4 · Razorpay integration | `Opus 5` | `high`, `max` for signature verification | Integration-against-docs, with one function where correctness is absolute. |
| 5 · Dashboard plumbing | `Sonnet 5` | `high` | Well-trodden Streamlit. Consider `/fast`. |
| 5 · Batch-summary view | `Opus 5` + `frontend-design` skill | `high` | The frame the video opens on. |
| 6 · Insight, abstention, kill switch | `Opus 5` | `xhigh` | Novel logic, subtle policy-engine interactions. |
| 6 · README & submission prose | `Opus 5` | `high` | Persuasive writing against a known rubric. |
| 7 · Video script | `Opus 5` | `medium` | Editing, not generating. |
| Any phase · bulk renames, mechanical refactors | `Haiku 4.5` | `low` | Cheap and fast for edits with no judgement in them. |

Model is switched with `/model`; `/fast` toggles fast mode on Opus 5 (same model, faster output — useful for the tight visual loop in Phase 5). **Check `/help` for the exact effort-setting command in your Claude Code version before relying on the effort column** — the level names (`low` … `max`) are the API's `output_config.effort` values and are correct, but the CLI surface for setting them is not verified here. If there is no per-session effort control, treat the `high`/`medium` rows as guidance on how much scope to hand the model per turn rather than a literal setting: smaller, well-specified turns for the mechanical phases, whole-subsystem specs for the `xhigh` ones.

### 5.2 For the product itself — the model Recoup calls

| Call site | Model | Config |
|---|---|---|
| Per-record reasoner | `claude-opus-5` | adaptive thinking · `output_config: {effort: "medium"}` · structured outputs via `messages.parse()` · prompt caching on the frozen system prefix · own disk cache keyed by input hash |
| Batch-level insight (§7b) | `claude-opus-5` | adaptive thinking · `output_config: {effort: "high"}` |
| Degraded tier *(only if Phase 3 finishes early)* | `claude-haiku-4-5` | sits between Opus and the deterministic fallback |

Always set `betas: ["server-side-fallback-2026-07-01"]` + `fallbacks: "default"`, and check `stop_reason` before reading content.

---

## 6. Risk register

| Risk | Likelihood | Mitigation | Phase |
|---|---|---|---|
| Free text too thin → project reads as a rules engine | **High** | 3 dedicated hours, 25–30 varied templates, each reviewed against "could a regex do this?" | 1 |
| Agent does not beat the baseline | Medium | Treat as a finding, not a failure. Investigate before adding features. Report it honestly either way — the track's bar explicitly rewards the exception list. | 3 |
| Anthropic API down or slow during recording | Medium | Disk cache + deterministic fallback, both tested with the key unset | 3 |
| Razorpay link cap not raised | High | Already the design: scarcity is modelled as a real constraint the agent must allocate | 0, 4 |
| Webhook tunnel flaky on demo day | Medium | Capture the live round-trip on video in Phase 4, the day it works | 4 |
| Citing an unverified regulation on screen | Low but **fatal** | `RuleSource.verified` flag; unverified rules render with a visible chip and never appear in the video | 2 |
| Phase 5 design work eats Phase 6 | Medium | Streamlit was chosen precisely to prevent this. Hard-stop the dashboard at 0.5 day. | 5 |

---

## 7. Living documentation — the maintenance protocol

Four docs, and they are only useful if they stay true. `docs/ISSUES.md` in particular is **not housekeeping — it is a graded submission field** ("Build Challenges & Technical Obstacles"), and the spec is explicit that the constraint table is the answer to it. Write it for that audience from hour zero.

At the close of **every phase**, without exception:

1. **`BUILD-LOG.md`** — append the phase entry: what was built, key decisions and why, files touched, gate evidence.
2. **`ISSUES.md`** — append every dead end, wrong turn and external constraint hit during the phase, with what you did about it. You will not remember these on Day 6.
3. **`ROADMAP.md`** — re-scope. Move completed items out, move slipped items down, note anything newly discovered.
4. **`IMPLEMENTATION-PLAN.md`** (this file) — update the status line at the top; amend later phases if a decision changed.

This protocol also lives in `CLAUDE.md`, so it survives context resets.

---

## 8. Open items carried from spec §11

| Item | Phase | Status |
|---|---|---|
| Razorpay Support — raise the 30-link cap | 0 | **not started — yours, do it first** |
| TRAI promotional-messaging window — verify at trai.gov.in | 2 | not started |
| RBI Fair Practices 08:00–19:00 contact rule — verify at rbi.org.in | 2 | not started |
| RBI E-mandate Framework 2026 — title, date, provisions | 6 (P1, mandate lane only) | not started |
| Refunds API behaviour in test mode | 4, only if used | not started |
| Does the buildathon supply a dataset? | 0 | assumed not; the generator is ours |
