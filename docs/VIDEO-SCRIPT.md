# Recoup — five-minute narration script

ROADMAP P0 #15. Every number here is quoted from a committed artifact; the
source is named in each beat so it can be re-checked before recording.

**The bar this is scored against:** *"Don't just identify the problem. Show
measured money recovered across a batch, with compliant escalation, stopping
rules, and an audit trail."* Every beat below serves one of those four. Nothing
else earns screen time.

Total spoken words ≈ 690, which is a comfortable five minutes at 140 wpm. It is
slightly under on purpose — leave air around the terminal beats.

---

## Pre-flight

```bash
uv run recoup run --seed 42 --arm all --no-model
uv run recoup run --seed 42 --arm all --cache-only --run-id seed42-tiered
uv run recoup run --seed 42 --arm all --no-model --ticks 224 --run-id seed42-t224
uv run recoup dashboard
```

- Browser at 100% zoom, window 1440 wide. The dashboard caps at 1340.
- Terminal font large enough to read at 720p. Two tabs: one for the webhook,
  one for the run.
- **Type `--arm all`, never `--arm both`.** `both` selects four arms for
  backward compatibility (OBS-007) and reads as sloppiness on camera.
- **Record the live beat with `--ticks 16`.** At 112 all three funded invoices
  have already settled and the link on screen would belong to a closed record
  (ISS-039).
- Do not pre-run the replay. It is worth more live.

---

## 0:00 – 0:30 · Open on the money

**Screen:** dashboard, Portfolio summary, run `seed42`.

> A hundred and twenty-six overdue B2B invoices. Two crore fifty-three lakh
> rupees outstanding.
>
> Do nothing at all, and forty-nine percent of it still comes back — customers
> pay late, not never. So that is the real baseline. Not zero.
>
> Chase every invoice on a fixed schedule and you recover sixty-two percent.
> That is the number most collection tools would put on a slide.

*Source: `runs/seed42/metrics.json` — control 49.25%, baseline 62.34%.*

---

## 0:30 – 1:15 · The number nobody puts on the slide

**Screen:** stay on the five-column frame; move the cursor along the contact row.

> Here is what it cost. Four hundred and fifty-nine phone calls, emails and
> payment links. And a hundred and four of those landed on somebody who had
> already paid, or who had an open dispute on the invoice.
>
> Recoup puts a deterministic policy engine in front of every action. Recovery
> drops to fifty-seven point eight percent. Contacts drop from four hundred and
> fifty-nine to a hundred and fifty-seven. Wrong contacts drop from a hundred
> and four to twenty-three.
>
> Four and a half points of recovery, for two-thirds fewer customer contacts. I
> think that is the trade a real finance team wants, and I would rather defend
> it than the bigger number.

*Source: same file — agent 57.75% at 157 contacts, 23 false interventions.*

---

## 1:15 – 2:15 · What a rule cannot read

**Screen:** Payer timeline → `ASH-2026-0012`. Then switch the run selector to
`seed42-tiered`.

> This invoice is twenty-five days overdue and the rules engine wants to send a
> reminder. But the payer already told us why they have not paid: the place of
> supply on the invoice puts the GST credit in the wrong state, so their
> accounts team physically cannot process it.
>
> No reminder ever fixes that. It is a document error, and it needs a person.
>
> That sentence is in free text. It is invisible to every structured field in
> the system. So Recoup sends the invoice to Claude, which reads the note and
> routes it to a human instead — and here is its own reasoning on screen.
>
> Across the book, that takes wrong contacts from twenty-three to zero.

*Source: `runs/seed42-tiered/metrics.json` — agent 0 false interventions.
Documented in ISS-036: the project had recorded this as an unreachable floor.*

---

## 2:15 – 3:00 · The model proposes, the engine disposes

**Screen:** scroll the timeline to a red veto dot; the rule provenance card is
beside it.

> The language model never decides anything. It proposes; a deterministic
> engine approves, reduces, or vetoes.
>
> This one is a veto. Contact attempted outside the eight-a-m-to-seven-p-m
> window that the Reserve Bank's recovery guidance sets. Eight of those fired in
> this run.
>
> And every rule on screen carries its source, whether it was verified at the
> issuing body, and the caveat on its scope. Where a rule is merchant policy
> rather than regulation, it says so. Nothing here is dressed up as a law that
> is not one.

*Source: canonical agent run — 8 `rbi-contact-hours` firings. The tiered run
shows 6.*

---

## 3:00 – 3:40 · Knowing when to stop

**Screen:** run selector → `seed42-t224`.

> Recovery is not the only job. Knowing when to give up matters too.
>
> Over fifty-six virtual days the naive chaser abandons thirty-six invoices and
> writes off fifteen. Recoup, running the same policy engine, stops on four.
>
> One note of honesty: twenty-eight days is the horizon everything else in this
> project is measured on, and it was fixed before any of these results existed.
> This longer run is a sensitivity check, not the headline — picking the
> timeframe that flatters your own agent is exactly the mistake I did not want
> to make.

*Source: `runs/seed42-t224/` — baseline 36 STOPs / 15 write-offs, agent 4 / 4.
The horizon is a §0 locked decision; see OBS-011.*

---

## 3:40 – 4:20 · Real money, and a log that proves it

**Screen:** terminal. The live run creating a Payment Link, the mock payment
page, the webhook arriving, the ledger flipping to `PAID`. Then run the replay.

> This is a real Razorpay test-mode Payment Link, created by the agent under a
> budget it has to allocate — thirty links, thirty times more demand.
>
> Payment goes through. Signed webhook arrives. The ledger moves to paid, and
> the outcome is appended to the audit log as a new row. Nothing is ever
> updated in place.
>
> And this is the part I would ask you to watch.

**Run it live:** `uv run recoup replay seed42/agent`

> That rebuilds every invoice's final state from the append-only log alone, with
> no other input, and checks it against what the run actually produced. Eight
> hundred and thirteen rows, hash chain verified, replay matches the ledger.
> That is an enforced test, not a claim.

*Source: `recoup replay seed42/agent` → 813 rows.*

---

## 4:20 – 5:00 · What is still wrong with it

**Screen:** back to Portfolio summary.

> Two things I would fix next, and both are written down in the repo.
>
> When the agent routes an invoice to a human, the recovery metric scores that
> as money not collected — because the simulation has no human collector in it.
> So the recovery column understates the agent, and I would rather say that than
> quietly benefit from it.
>
> And the invoices that were already paid but not reconciled are invisible to
> the ledger by construction. The model catches them by reading the customer's
> own words. A real deployment would want a bank feed instead.
>
> Recoup finds money that is slipping away, decides what to do about it, and can
> prove every decision it made. Thank you.

*Source: OBS-008 and OBS-003/ISS-036.*

---

## If a beat has to go

Drop in this order. Never cut the replay.

1. §4:20 limitations — shrink to one sentence
2. §3:00 stopping rules — the metric table already shows write-offs
3. §2:15 provenance — merge one line into the veto beat

## Numbers to re-verify before recording

| Claim | Command |
|---|---|
| 49.25 / 62.34 / 56.54 / 57.75, contacts, false interventions | `recoup metrics seed42` |
| 0 false interventions, 104 contacts | `recoup metrics seed42-tiered` |
| 36 / 15 vs 4 / 4 write-offs | `recoup metrics seed42-t224` |
| 813 rows, chain verified | `recoup replay seed42/agent` |
| 1 of 30 test links consumed | `docs/ISSUES.md` ISS-001 |
