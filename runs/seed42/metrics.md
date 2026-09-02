# Recoup metric report

Definitions:

- Recovery denominator: `billed_paise` on the INTAKE rows.
- False intervention: an executed contact on an invoice carrying the held-out `DISPUTED` or `ALREADY_PAID_UNRECONCILED` flag.
- Escalations selected by the strategy are separated from final human-queue cases caused by payer responses.
- A rule firing is the `rule_id` recorded on the decision row: the first veto or first modification.

| Metric | Control | Baseline | Agent |
|---|---|---|---|
| Recovery rate | 49.3% | 62.3% | 57.8% |
| ₹ recovered | Rs 1,24,60,148.75 | Rs 1,57,71,226.15 | Rs 1,46,10,185.33 |
| Contacts made | 0 | 459 | 157 |
| Contacts per ₹ recovered | 0.00000000 | 0.00002910 | 0.00001075 |
| False interventions | 0 | 104 | 23 |
| Policy vetoes | 0 | 0 | 231 |
| Escalated to human (agent-selected) | 0 | 0 | 16 |
| Human queue from payer response | 0 | 28 | 5 |
| Unresolved / written off | 72 / 0 | 37 / 19 | 60 / 0 |

## Recorded policy-rule firings

Zeroes are included deliberately so a rule that silently stops firing is visible.

| Rule | Control | Baseline | Agent |
|---|---|---|---|
| `nothing-outstanding` | 0 | 0 | 0 |
| `visible-dispute` | 0 | 0 | 16 |
| `rbi-contact-hours` | 0 | 0 | 8 |
| `trai-promotional-window` | 0 | 0 | 0 |
| `trai-message-category` | 0 | 0 | 0 |
| `payer-contact-frequency` | 0 | 0 | 51 |
| `payer-contact-spacing` | 0 | 0 | 172 |
| `invoice-link-cap` | 0 | 0 | 0 |
| `link-budget` | 0 | 0 | 0 |
| `high-value-escalation` | 0 | 0 | 0 |
