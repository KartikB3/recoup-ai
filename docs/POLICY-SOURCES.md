# Policy Sources

> Phase 2–3 deliverable. Every rule, its citation, its verification status, and
> the fixed order the engine runs them in.

Two kinds of rule, never confused:

- **REGULATORY** — carries a real citation. Must be verified at the issuing
  body's own site before it appears in the UI or the video.
- **MERCHANT** — business policy. Labelled as merchant-configured everywhere it
  is rendered. Never dressed up as regulatory.

`RuleSource.verified` is the enforcement mechanism for **regulatory** sources:
`False` renders with a warning chip and is kept out of the demo. Verification
is `None`/N/A for merchant policy because it has no issuing-body source; giving
it a verified badge would be a category error. There are no unverified
regulatory rules in the engine — the P0 citations were read at source and the
P1 e-mandate rules were not written at all.

---

## Verification log — Phase 2, 2026-09-02

Every regulatory source below was read **in the gazette notification or
circular itself, on the issuing body's own domain**. Not a vendor blog, not a
summary, not from memory. Where the PDF would not render through a fetcher, the
file was downloaded and the text extracted locally; the quoted clauses below
are verbatim from those documents.

### ✅ RBI contact window — verified, with a scope caveat

| | |
|---|---|
| **Document** | *Outsourcing of Financial Services – Responsibilities of regulated entities employing Recovery Agents* |
| **Reference** | RBI/2022-23/108 |
| **Date** | 12 August 2022 |
| **Read at** | `rbi.org.in/scripts/NotificationUser.aspx?Id=12378&Mode=0` |

> Regulated entities shall ensure that they or their agents do not resort to
> "**persistently calling the borrower and/ or calling the borrower before 8:00
> a.m. and after 7:00 p.m. for recovery of overdue loans**", and "do not resort
> to intimidation or harassment of any kind, either verbal or physical, against
> any person in their debt collection efforts."

**Applies to:** all Commercial Banks (excluding Payments Banks), All-India
Financial Institutions, NBFCs, Primary and State Co-operative Banks, and Asset
Reconstruction Companies. **Excludes** microfinance loans, covered separately.

**The scope caveat, stated plainly and carried in the data.** This circular
governs *lending recovery by regulated entities*. A merchant chasing its own
trade receivables is not a regulated entity under it. Recoup **adopts** the
08:00–19:00 window as a standard and does not claim to be legally bound by it.
That sentence lives in `RuleSource.scope_caveat` so it travels with the
citation into the dashboard rather than sitting in a document nobody opens.
This closes ISS-008.

The circular number is quoted here because it was verified at source. Contrast
ISS-006, where two different circular numbers appear across secondary sources
for the e-mandate framework — that one would have shipped as title-and-date
only, if it had shipped.

### ⚠️ TRAI promotional window — verified, but **the project's own claim was wrong**

| | |
|---|---|
| **Document** | *Telecom Commercial Communications Customer Preference Regulations, 2018* (6 of 2018), Schedule III |
| **Date** | 19 July 2018 |
| **Read at** | `trai.gov.in/sites/default/files/2024-09/RegulationUcc19072018.pdf` |

This file previously carried the rule as *"Promotional-category messages only
10:00–21:00 IST"*, sourced from a vendor blog (ISS-007). **TCCCPR contains no
such prohibition.** What it contains is a customer preference register with
nine opt-out time bands, and this note to the table:

> **Note-1:** Time Bands (i), (ii), (iii) and (ix) shall be **default OFF for
> all customers irrespective of the status of registration of customer** i.e.
> for all customers including those who have not registered any type of
> preference(s), anytime unless customer has registered its preference(s) and
> switched ON

Bands (i), (ii), (iii) and (ix) are `00:00–06:00`, `06:00–08:00`, `08:00–10:00`
and `21:00–24:00`. Their complement is **10:00–21:00** — which is where the
widely repeated figure comes from.

So the number is right and the reason is completely different: it is a
**default preference, not a ban**, and it binds **only promotional
communication**. Note-4 to the BLOCK PROMO option is explicit that service,
transactional and government communications are outside it. Full write-up in
ISS-024.

### ✅ TRAI message categories — verified

| | |
|---|---|
| **Document** | *Telecom Commercial Communications Customer Preference (Second Amendment) Regulations, 2025* (1 of 2025) |
| **Date** | 12 February 2025 |
| **Read at** | `trai.gov.in/sites/default/files/2025-02/Regulation_12022025.pdf` |

> Access Provider should suffix "**-P**", "**-S**", "**-T**", and "**-G**" to
> Header structure for promotional, service, transactional, and government
> communications.

That is the `MessageCategory` enum, confirmed. The same amendment settles a
design question this project had already answered by reasoning:

> "Transactional Message or Transactional Voice Call" means a Message sent or
> Voice Call made by a Sender to its Customer or Subscriber **in response to
> Customer initiated transaction within thirty minutes of the transaction**

A payment link chasing a bill that is forty days overdue is merchant-initiated
and is not within thirty minutes of anything. It is a **Service** message and
never `-T`. The `correct_category` table in `domain/interventions.py` was
written on that reasoning in Phase 1 and is now backed by the clause.

Two further provisions were verified and are **not** encoded, because Recoup
never acquires consent — recorded here so a later phase does not re-research
them:

- Explicit consent taken to facilitate or complete a transaction is valid for
  **a maximum of seven days** ("Provided that such Explicit Consent shall be
  for seven days or as directed by the Authority from time to time").
- A sender may **re-acquire consent only after ninety (90) days** from the date
  the customer revoked it or opted out.

### ⬜ RBI E-mandate Framework 2026 — not verified, not written

P1, and the mandate lane did not ship. No rule cites it, so there was nothing
to verify. ISS-006 stays open and unresolved on purpose. **Do not** encode
these from the secondary sources in that issue.

---

## Rules the engine runs, in order

The order is part of the spec, not an implementation detail. It is
`policy/rules/__init__.py::RULE_ORDER`, and `tests/test_policy.py` asserts that
this table and that tuple agree.

**First veto wins.** Evaluation stops at the first rule that vetoes; the
`rule_id` logged on the audit row is that rule, and it is what the dashboard
renders as the reason.

**Modifications compose**, and the invariant that makes a single pass safe is:
**a modification may only reduce contact intensity, never raise it.** Ordering
`WAIT = STOP = ESCALATE_HUMAN < SOFT_REMINDER < PAYMENT_LINK < PHONE_FOLLOWUP`,
every modification moves down or sideways. A rule that has already passed
therefore cannot be violated by a later downgrade, so no re-run is needed.
`tests/test_policy.py::test_a_modification_never_raises_contact_intensity`
asserts it over every rule.

| # | Rule id | Kind | Verdict | Fires when |
|---|---|---|---|---|
| 1 | `nothing-outstanding` | MERCHANT | VETO | A contact is proposed on a record with nothing left to collect. |
| 2 | `visible-dispute` | MERCHANT | MODIFY → `ESCALATE_HUMAN` | The record is in `DISPUTED`, or carries a `dispute_description`. |
| 3 | `batch-cluster-suppression` | MERCHANT | MODIFY → `ESCALATE_HUMAN`, then VETO | An approved aggregate pattern holds the parent group: the first contact opens one consolidated escalation, later ones are suppressed. |
| 4 | `rbi-contact-hours` | **REGULATORY** | VETO + defer | A contact would land before 08:00 or after 19:00 virtual time. |
| 5 | `trai-promotional-window` | **REGULATORY** | VETO + defer | A `-P` message would land outside the 10:00–21:00 default bands. |
| 6 | `trai-message-category` | **REGULATORY** | VETO | A drafted message carries a category the intervention may not use. |
| 7 | `payer-contact-frequency` | MERCHANT | VETO + defer | The payer has already had 4 contacts in the rolling 30-day window. |
| 8 | `payer-contact-spacing` | MERCHANT | VETO + defer | The payer was contacted less than 72h ago, on any of their invoices. |
| 9 | `invoice-link-cap` | MERCHANT | MODIFY → `SOFT_REMINDER` | 3 payment links have already gone out on this invoice. |
| 10 | `link-budget` | MERCHANT | MODIFY → `SOFT_REMINDER` | The run's global payment-link budget is spent. |
| 11 | `high-value-escalation` | MERCHANT | MODIFY → `ESCALATE_HUMAN` | Automation proposes to `STOP` on a record above the escalation threshold. |

### The aggregate decision, and how it binds

The portfolio insight is adjudicated outside `RULE_ORDER`. `adjudicate_batch`
evaluates one aggregate recommendation before the per-record loop rather than
competing for first-veto position with invoice rules.

It approves suppression only when every named invoice exists, is still open,
belongs to the one named parent group, covers that group's complete open scope,
and spans at least three invoices and three distinct payers. Approval resolves
to the existing `ESCALATE_HUMAN` intervention; the model cannot invent a
seventh action.

Applying it is a second and deliberately separate step. `adjudicate_batch`
decides whether a recommendation is *allowed*; `arm_batch_suppression` is the
runner asking for it to be *applied*. A caller therefore cannot apply something
the engine refused, and `applied_to_ledger` reports what the engine accepted
rather than what the model asked for. Once armed, the decision reaches
individual records through rule 3 above, `batch-cluster-suppression`, so every
suppressed contact carries a rule id and a reason in the audit log instead of
vanishing (ISS-047).

**Why this order.** Rules 1–2 are about the record itself and produce the most
explanatory reason a reader could be given, so they run first — for a disputed
invoice contacted at 20:00, "this invoice is disputed" is a better answer than
"wrong hour". Rule 3 applies an already-approved account-level decision, and
sits after `visible-dispute` so an invoice with its own dispute is routed on its
own merits rather than absorbed into a group one. Rules 4–6 are the regulatory
contact constraints. Rules 7–8 are merchant frequency. Rules 9–10 are budget
downgrades, which cannot un-fire anything above them because a downgrade is
still a contact. Rule 11 is last because it only ever looks at `STOP`, which no
earlier rule inspects.

**Deferral.** Rules 4, 5, 7 and 8 are "not now", not "no" — so their verdict
carries `defer_to_tick`, and the runner sets the record's next review to that
tick instead of the intervention's usual interval. Without it a record vetoed
at 20:00 would be re-reviewed a whole number of days later, land on 20:00
again, and be blocked forever. See ISS-025.

---

## Merchant-configured rules — no citation, and none claimed

Engine-owned defaults live in `policy/context.py::MerchantPolicy`; attempt
limits belong to each proposer and are called out separately below.

| Rule | Default | Note |
|---|---|---|
| Max contacts per payer per 30 days | 4 | Counted across **all** of a payer's invoices, not per invoice. A payer with nine open bills must not get nine times the messages. |
| Minimum spacing between contacts to the same payer | 72h | Same reason. |
| Max payment links per invoice | 3 | |
| Hard stop on a visibly disputed invoice | on | Implemented as an escalation, not a silence — see below. |
| Escalate rather than abandon above | ₹5,00,000 | Applies to `STOP`, so a large receivable is never written off by automation without a human seeing it. |
| Global payment-link budget per run | `None` (off) | Set to 30 for live runs only (ISS-001). Off for the simulated batch — see the note below. |
| Attempts before automation stops | Baseline: 5 contacts. Agent: 6 decision rungs (5 contacts, then `STOP`). | **Explicitly not regulatory**, see ISS-009. Owned by each proposer, not the engine. The agent's post-phone reminder is required for the RBI behavioural check; see ISS-025. |
| Parent-level escalation breadth | 3 open invoices across 3 distinct payers, covering the complete open group | Applies only to the Phase 3 batch recommendation; it is not a regulatory threshold. |

The ₹5,00,000 default is `50_000_000` paise. A regression test equates it to
the generator's escalation reference; this prevents Indian digit grouping from
silently turning ₹5 lakh into ₹50 lakh again (ISS-030).

**The dispute rule is an escalation, not a veto, and that was a decision.** The
build spec says "hard stop on `DISPUTED`". A veto would have been the literal
reading and the wrong behaviour: the proposer would re-propose contact at every
review, the engine would veto it again, and the record would accumulate a
hundred veto rows while no human ever looked at a live commercial objection.
Modifying to `ESCALATE_HUMAN` stops the chasing *and* puts the case in front of
someone, and it terminates — `ESCALATE_HUMAN` moves the record to `HUMAN_QUEUE`,
which `UNATTENDED_STATES` keeps out of the review rotation. The cost is real
and is reported: it raises the agent's escalation count, and the metric table
separates escalations the agent *chose* from human-queue items caused by a
payer complaint.

**The link budget is configured off for the simulated batch, deliberately.**
The 30-link cap is a Razorpay *test-mode* constraint (ISS-001) and belongs to
live runs. Applying it to a simulated batch would cap the agent at 30 links
while the baseline — which bypasses the engine entirely — sent 225, and the
metric table would then be measuring a handicap rather than a strategy. The
rule is written, unit-tested and wired; it activates in Phase 4 with
`--executor live`.

---

## Why each zero stays zero on the seeded batch

The canonical report distinguishes a policy bypass from a policy-enabled zero.
Six rules record zero in both policy-enabled arms, for four different reasons:

| Rule | Run status and why zero |
|---|---|
| `nothing-outstanding` | Defensive guard. A zero-balance record is terminal and excluded from review before policy runs. |
| `trai-promotional-window` | Recoup sends no promotional traffic. Every message it drafts is Service, which the regulation explicitly exempts. Making it fire would mean inventing promotional content so a time window had something to bite on — a worse use of a real citation than leaving it dormant. |
| `trai-message-category` | The Phase 2 agent always drafts the correct Service category; the naive proposer has no draft. The rule becomes a live guard against model error in Phase 3. |
| `invoice-link-cap` | Active on an attempted fourth payment link. The naive ladder sends at most three and the agent ladder at most two, so neither attempts the action the cap would modify. |
| `link-budget` | Disabled for simulated runs with `link_budget=None`, per the note above. The report labels this disabled state rather than displaying it as an unexplained zero. |
| `high-value-escalation` | Active only when `STOP` is proposed above ₹5,00,000. Policy deferrals leave both policy-enabled arms mid-ladder at the 28-day horizon, so neither proposes STOP. |

Every rule has a discriminating direct unit test. The behavioral artifact also
records 16 visible-dispute modifications in each policy arm, 247 merchant
vetoes in baseline + policy, and 223 merchant plus 8 regulatory vetoes in the
agent arm. Modifications are reported separately; they are not inflated into
the veto total.
