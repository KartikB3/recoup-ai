# Policy Sources

> Phase 2 deliverable. Every rule, its citation, and its verification status.

Two kinds of rule, never confused:

- **REGULATORY** — carries a real citation. Title and date only, never a circular
  number. Must be verified at the issuing body's own site before it appears in
  the UI or the video.
- **MERCHANT** — business policy. Labelled as merchant-configured everywhere it
  is rendered. Never dressed up as regulatory.

`RuleSource.verified` is the enforcement mechanism: a rule with `verified=False`
renders with a visible warning chip and is kept out of the demo.

## Regulatory rules — to verify in Phase 2

| Rule | Claimed source | Verified | Notes |
|---|---|---|---|
| No contact before 08:00 or after 19:00 IST | RBI Fair Practices Code; Aug 2022 circular on outsourcing of financial services | ❌ | Verify at rbi.org.in. **Scope caveat:** governs lending recovery, not merchant receivables. Present as an adopted standard, not a binding obligation. See ISS-008. |
| Promotional-category messages only 10:00–21:00 IST | TRAI TCCCPR | ❌ | Verify at trai.gov.in. Currently vendor-blog sourced. See ISS-007. |
| Transaction-completion consent expires after 7 days | TRAI TCCCPR, Feb 2025 amendment | ❌ | Verify at trai.gov.in |
| No re-consent request within 90 days of opt-out | TRAI TCCCPR, Feb 2025 amendment | ❌ | Verify at trai.gov.in |
| Message category must be correctly classified (-P/-S/-T/-G) | TRAI TCCCPR, Feb 2025 amendment | ❌ | Verify at trai.gov.in |
| Pre-debit notification ≥24h, with opt-out | RBI *Digital Payments – E-mandate Framework, 2026*, 21 Apr 2026 | ❌ | **P1 only** — applies solely if the mandate lane ships. Two different circular numbers appear across sources: cite title and date only. See ISS-006. |
| AFA required above ₹15,000 per recurring transaction | Same framework | ❌ | P1 only. ₹1,00,000 for insurance premiums, mutual fund subscriptions, credit card bills. |

## Merchant-configured rules — no citation, and none claimed

| Rule | Default |
|---|---|
| Max contacts per payer per 30 days | 4 |
| Minimum spacing between contacts to the same payer | 72h |
| Max payment links per invoice | 3 |
| Hard stop on any invoice flagged DISPUTED | on |
| Escalate to human above invoice value | configurable |
| Global payment-link budget per run | 30 (test-mode cap, ISS-001) |
| Max attempts before EXHAUSTED | 5 — **explicitly not regulatory**, see ISS-009 |

## Rule evaluation order

> Phase 2: write the fixed order here. First veto wins; modifications compose.
> The order is part of the spec, not an implementation detail.
