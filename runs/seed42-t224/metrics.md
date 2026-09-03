# Recoup metric report

Definitions:

- Value recovery denominator: `billed_paise` on the INTAKE rows.
- Record recovery rate: final `PAID` records divided by opening record count.
- False intervention: an executed contact on an invoice carrying the held-out `DISPUTED` or `ALREADY_PAID_UNRECONCILED` flag.
- Escalations selected by the strategy are separated from final human-queue cases caused by payer responses.
- A rule firing is the `rule_id` recorded on the decision row: the first veto or first modification.

| Metric | Control | Baseline | Baseline + policy | Agent |
|---|---|---|---|---|
| Recovery rate (value) | 58.5% | 67.0% | 65.8% | 66.7% |
| Recovery rate (record count) | 54.0% | 61.9% | 60.3% | 61.9% |
| Records paid | 68 / 126 | 78 / 126 | 76 / 126 | 78 / 126 |
| Rs recovered | Rs 1,47,90,471.28 | Rs 1,69,47,696.54 | Rs 1,66,51,869.85 | Rs 1,68,76,771.69 |
| Contacts made | 0 | 459 | 233 | 223 |
| Payment links sent | 0 | 225 | 94 | 101 |
| Contacts per Rs recovered | 0.00000000 | 0.00002708 | 0.00001399 | 0.00001321 |
| False interventions | 0 | 104 | 31 | 31 |
| - on disputed invoices | 0 | 76 | 16 | 16 |
| - on already-paid / unreconciled invoices | 0 | 28 | 15 | 15 |
| Policy vetoes | n/a (bypassed) | n/a (bypassed) | 313 | 298 |
| - regulatory-source vetoes | n/a (bypassed) | n/a (bypassed) | 0 | 14 |
| - merchant-policy vetoes | n/a (bypassed) | n/a (bypassed) | 313 | 284 |
| Policy modifications | n/a (bypassed) | n/a (bypassed) | 18 | 19 |
| Deferred vetoes | n/a (bypassed) | n/a (bypassed) | 313 | 298 |
| STOP decisions | 0 | 36 | 14 | 4 |
| Escalated to human (agent-selected) | 0 | 0 | 18 | 19 |
| Human queue from payer response | 0 | 25 | 5 | 7 |
| Unresolved / written off | 58 / 0 | 33 / 15 | 37 / 13 | 44 / 4 |

## Recorded policy-rule firings

A number means the policy engine ran. `bypassed` means that arm did not run policy at all; the run-status note explains every meaningful zero.

| Rule | Run status | Control | Baseline | Baseline + policy | Agent |
|---|---|---|---|---|---|
| `nothing-outstanding` | Defensive guard; zero-balance records are terminal before review. | bypassed | bypassed | 0 | 0 |
| `visible-dispute` | Active merchant guard for structured dispute state. | bypassed | bypassed | 18 | 19 |
| `rbi-contact-hours` | Active adopted standard; the cited circular governs regulated-loan recovery. | bypassed | bypassed | 0 | 14 |
| `trai-promotional-window` | Active for promotional drafts; the canonical fallback drafts only service messages. | bypassed | bypassed | 0 | 0 |
| `trai-message-category` | Active for every model draft; the canonical fallback uses the correct service category. | bypassed | bypassed | 0 | 0 |
| `payer-contact-frequency` | Active merchant frequency cap. | bypassed | bypassed | 131 | 112 |
| `payer-contact-spacing` | Active merchant minimum-spacing guard. | bypassed | bypassed | 182 | 172 |
| `invoice-link-cap` | Active at an attempted fourth link; neither deterministic ladder attempts one. | bypassed | bypassed | 0 | 0 |
| `link-budget` | Disabled for simulation with link_budget=None; reserved for live execution. | bypassed | bypassed | 0 | 0 |
| `high-value-escalation` | Active when STOP is proposed above Rs 5,00,000; no STOP means no opportunity. | bypassed | bypassed | 0 | 0 |

## Interpretation notes

- The two baseline columns use the identical naive proposer; their only difference is whether the policy engine runs. Baseline + policy versus agent then isolates proposer value with policy held constant.
- Veto provenance counts only VETOED decisions. Merchant-source modifications are reported separately and are not regulatory vetoes.
