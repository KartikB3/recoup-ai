# Recoup metric report

Definitions:

- Value recovery denominator: `billed_paise` on the INTAKE rows.
- Record recovery rate: final `PAID` records divided by opening record count.
- False intervention: an executed contact on an invoice carrying the held-out `DISPUTED` or `ALREADY_PAID_UNRECONCILED` flag.
- Escalations selected by the strategy are separated from final human-queue cases caused by payer responses.
- A rule firing is the `rule_id` recorded on the decision row: the first veto or first modification.

| Metric | Control | Baseline | Baseline + policy | Agent |
|---|---|---|---|---|
| Recovery rate (value) | 49.3% | 62.3% | 56.5% | 54.4% |
| Recovery rate (record count) | 42.9% | 55.6% | 50.0% | 48.4% |
| Records paid | 54 / 126 | 70 / 126 | 63 / 126 | 61 / 126 |
| Rs recovered | Rs 1,24,60,148.75 | Rs 1,57,71,226.15 | Rs 1,43,03,667.23 | Rs 1,37,68,131.66 |
| Contacts made | 0 | 459 | 161 | 104 |
| Payment links sent | 0 | 225 | 56 | 52 |
| Contacts per Rs recovered | 0.00000000 | 0.00002910 | 0.00001126 | 0.00000755 |
| False interventions | 0 | 104 | 23 | 0 |
| - on disputed invoices | 0 | 76 | 8 | 0 |
| - on already-paid / unreconciled invoices | 0 | 28 | 15 | 0 |
| Policy vetoes | n/a (bypassed) | n/a (bypassed) | 247 | 113 |
| - regulatory-source vetoes | n/a (bypassed) | n/a (bypassed) | 0 | 6 |
| - merchant-policy vetoes | n/a (bypassed) | n/a (bypassed) | 247 | 107 |
| Policy modifications | n/a (bypassed) | n/a (bypassed) | 16 | 15 |
| Deferred vetoes | n/a (bypassed) | n/a (bypassed) | 247 | 113 |
| STOP decisions | 0 | 36 | 0 | 0 |
| Escalated to human (agent-selected) | 0 | 0 | 16 | 64 |
| Human queue from payer response | 0 | 28 | 2 | 6 |
| Unresolved / written off | 72 / 0 | 37 / 19 | 63 / 0 | 65 / 0 |

## Recorded policy-rule firings

A number means the policy engine ran. `bypassed` means that arm did not run policy at all; the run-status note explains every meaningful zero.

| Rule | Run status | Control | Baseline | Baseline + policy | Agent |
|---|---|---|---|---|---|
| `nothing-outstanding` | Defensive guard; zero-balance records are terminal before review. | bypassed | bypassed | 0 | 0 |
| `visible-dispute` | Active merchant guard for structured dispute state. | bypassed | bypassed | 16 | 15 |
| `rbi-contact-hours` | Active adopted standard; the cited circular governs regulated-loan recovery. | bypassed | bypassed | 0 | 6 |
| `trai-promotional-window` | Active for promotional drafts; the canonical fallback drafts only service messages. | bypassed | bypassed | 0 | 0 |
| `trai-message-category` | Active for every model draft; the canonical fallback uses the correct service category. | bypassed | bypassed | 0 | 0 |
| `payer-contact-frequency` | Active merchant frequency cap. | bypassed | bypassed | 65 | 26 |
| `payer-contact-spacing` | Active merchant minimum-spacing guard. | bypassed | bypassed | 182 | 81 |
| `invoice-link-cap` | Active at an attempted fourth link; neither deterministic ladder attempts one. | bypassed | bypassed | 0 | 0 |
| `link-budget` | Disabled for simulation with link_budget=None; reserved for live execution. | bypassed | bypassed | 0 | 0 |
| `high-value-escalation` | Active when STOP is proposed above Rs 5,00,000; no STOP means no opportunity. | bypassed | bypassed | 0 | 0 |

## Interpretation notes

- The two baseline columns use the identical naive proposer; their only difference is whether the policy engine runs. Baseline + policy versus agent then isolates proposer value with policy held constant.
- Agent write-offs are zero because the 28-day horizon ends mid-ladder: it made 0 STOP decisions after 113 deferred vetoes. This is horizon truncation, not evidence of restraint.
- Veto provenance counts only VETOED decisions. Merchant-source modifications are reported separately and are not regulatory vetoes.
