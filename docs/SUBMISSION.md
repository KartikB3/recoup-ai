# Submission form — drafted answers

ROADMAP P0 #14. The form has five fields, two of which are URLs. Everything
below is copy-paste ready; every number is quoted from a committed artifact and
re-checkable with the command named in the README.

---

## 1. Project Name / Title

```
Recoup — autonomous B2B receivables recovery, measured against doing nothing
```

*Shorter alternative if the field is tight:* `Recoup`

---

## 2. Project Objectives · What does it solve?

```
Indian B2B sellers carry crores in overdue invoices and chase them on fixed
schedules — every N days until someone pays. Recoup replaces that with an agent
that decides, per invoice per review, whether to wait, remind, send a payment
link, call, escalate to a human, or stop.

The problem it actually attacks is measurement. Collection tools report a
recovery percentage with nothing to compare it to. On our seeded book of 126
overdue invoices worth Rs 2.53 crore, chasing everything on a fixed schedule
recovers 62.3%. Doing absolutely nothing recovers 49.2%, because B2B customers
pay late rather than never. So the ladder is worth 13 points, not 62 — and it
buys them with 459 customer contacts, 104 of which land on someone who had
already paid or had an open dispute.

Recoup prices that trade honestly. It recovers 56.7% using 137 contacts and 23
wrong ones: 5.6 recovery points given up for 70% fewer customer contacts and 78%
fewer wrong ones. With Claude reading the free text at first review, wrong
contacts reach zero for a further 2.6 points. A finance team that has to answer
for its dunning behaviour is buying that column, not the biggest number.

Three things make it more than a scheduler:

- Every action passes a deterministic policy engine that can veto it. The model
  proposes; the engine disposes. The model never supplies a money amount, a date
  calculation, or a final decision, and the action space is a closed enum of six.
- Every rule carries its citation, whether it was verified at the issuing body,
  and the caveat on its scope — and is labelled regulatory or merchant policy,
  never confused.
- The audit log is append-only, and `recoup replay` rebuilds every invoice's
  final state from the log alone and diffs it against the ledger. 806 rows, hash
  chain verified. It is an enforced test, not a claim.

Harm is scored against held-out ground truth the agent cannot see: 40 of the 126
records carry a hidden dispute, hardship or already-paid flag. That is why the
batch is simulated — on real data, nobody labels which invoices were already
paid, so the harm metric could not exist.
```

---

## 3. GitHub Repository URL

```
https://github.com/KartikB3/recoup-ai
```

---

## 4. 5-min Pitch Video Link

> **To fill in after recording.** Narration script, shot order and the
> re-verify commands are in [`VIDEO-SCRIPT.md`](VIDEO-SCRIPT.md).

---

## 5. Build Challenges & Technical Obstacles

```
Five that changed the architecture rather than just costing time.

1. Our own baseline was accidentally a straw man.

With the first fatigue parameters the naive chaser drove 44 of 126 records into
the human queue over a five-contact campaign. Thirty-five percent of a book
needing human attention because a system sent five reminders is not credible,
and the risk ran opposite to the usual one: not that our agent looked bad, but
that it looked far too good. We swept both parameters and found recovery moves
0.6 points across the entire range while the harm figure nearly halves — so the
calibration governs the plausibility of the harm, not who wins. Settled on three
penalty-free contacts and 28 queued records from 459 contacts. Fixing it made
our own agent look worse, which is the point. Written up in full rather than
buried.

2. We falsified a floor we had published ourselves.

We had documented that false interventions could not reach zero: invoices
already paid but unreconciled show money outstanding in the ledger, so the
snapshot carries no signal. We then seeded the 28 records where prose is the
only signal and scored the model against the held-out flags. It suppressed 10 of
10 already-paid contacts and 6 of 6 prose-only disputes; across the arm, scored
false interventions went 23 to 0. The floor was real for a snapshot-reading
proposer and false for a prose-reading one. No new data source was needed — the
signal was in the payer notes all along. We deleted the observation and logged
the falsification.

3. The obvious scarce-budget allocator spends nothing at all.

Razorpay test mode caps Payment Links at 30 per business, so we modelled link
scarcity as a constraint the agent must allocate. The obvious implementation —
shortlist the largest receivables when the book opens — creates zero real links
on our book. The three largest invoices never request one: two are escalated to
a human at tick 0, one pays after a single reminder. It fails silently and in
the flattering direction: the run completes, the metrics are unchanged, the
allocation report looks principled, and the number of real Razorpay objects is
nought. Had we not made the fake client count LIVE rows, we would have found it
on camera. Demand is now revealed rather than predicted — a free dry run
discovers which records actually ask for a link, and the budget is allocated
across those.

4. A partially seeded model cache plus a live key is unbounded spend.

The reasoner's contract is lookup, miss, live call, fallback on failure. Correct
in isolation, dangerous in aggregate: once a credential exists, an ordinary run
bills for every uncached record. We learned this the expensive way — a
verification run against a freshly configured key made roughly 50 unbudgeted
calls before it was stopped. The demo depends on a partial cache, because a full
one costs an order of magnitude more than the budget, so the hazardous state is
the normal steady state. The existing circuit breaker trips on errors, not on
successful spend, so it gave no protection against the failure mode that costs
money. We added a hard call ceiling, a cache-only mode that makes a miss take
the deterministic fallback instead of calling, and moved all buying to a
separate command that is a dry run unless confirmed. The two documented
reproduction commands now cannot spend anything at all.

5. Our harm metric would have punished the correct behaviour.

Twelve records carry a hidden hardship flag, and the simulation models pressing
those payers as actively counterproductive. The obvious move was to score
hardship contact as a third false-intervention subtype. Reading what the agent
actually did with those twelve killed it. It escalates nine to a human and
contacts three — and all three are payers who asked to be able to pay: one
cannot add a beneficiary, one has a transfer limit below the invoice value, one
confirmed the transfer is already queued. Two others explicitly requested a
payment link and were still escalated, because those payers had also made a
part-payment offer or asked for someone authorised to settle — a commercial
question the agent has no authority to answer. A subtype scored against the flag
would have counted sending a payment link to someone who requested one as harm.
Hardship is now reported rather than scored, and the distinction is written down
as a rule the reasoner is held to: contact is service when the obstacle is
operational, pressure when a commercial question is open.

All five are logged with their evidence and design consequence in
docs/ISSUES.md, which carries 49 entries.
```

---

## Notes for whoever fills the form

- Field 5 is the graded one. The five above were chosen for **design
  consequence**, not drama — each one changed the architecture or the metric.
  The raw material for alternatives is `ISSUES.md`; the sharpest unused ones are
  ISS-041 (`executor: LIVE` would have been a lie on most rows), ISS-043
  (committing a real cache silently broke the documented reproduction command)
  and ISS-039 (the demo horizon settles every funded link before a human could
  pay it).
- Do not claim a real payment has been reconciled until the live round trip has
  actually been run. Until then the honest phrasing is "built and verified
  offline". See the README under *Running the live loop*.
- Every figure quoted above is re-derivable: `recoup metrics seed42`,
  `recoup metrics seed42-tiered`, `recoup replay seed42/agent`.
