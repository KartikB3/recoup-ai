"""Render the Phase 2 metric comparison as readable Markdown and JSON."""

from __future__ import annotations

import json
from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from recoup.domain.enums import Arm
from recoup.domain.models import format_inr
from recoup.metrics.compute import ArmMetrics, MetricReport
from recoup.policy.rules import RULE_ORDER

DEFINITIONS: dict[str, str] = {
    "recovery_denominator": "billed_paise on the INTAKE rows",
    "record_recovery_rate": "final PAID records divided by opening record count",
    "false_intervention": (
        "an executed contact on a record carrying DISPUTED or "
        "ALREADY_PAID_UNRECONCILED ground truth"
    ),
    "automated_escalation": "an executed ESCALATE_HUMAN decision",
    "payer_human_queue": (
        "a final HUMAN_QUEUE record not placed there by an ESCALATE_HUMAN decision"
    ),
    "rule_firing": "the rule_id recorded on a decision row (first veto or first modification)",
}

RULE_RUN_NOTES: dict[str, str] = {
    "nothing-outstanding": ("Defensive guard; zero-balance records are terminal before review."),
    "visible-dispute": "Active merchant guard for structured dispute state.",
    "rbi-contact-hours": (
        "Active adopted standard; the cited circular governs regulated-loan recovery."
    ),
    "trai-promotional-window": (
        "Active for promotional drafts; Phase 2 drafts only service messages."
    ),
    "trai-message-category": (
        "Active for drafted messages; Phase 2 drafts use the correct service category."
    ),
    "payer-contact-frequency": "Active merchant frequency cap.",
    "payer-contact-spacing": "Active merchant minimum-spacing guard.",
    "invoice-link-cap": (
        "Active at an attempted fourth link; neither Phase 2 ladder attempts one."
    ),
    "link-budget": ("Disabled for simulation with link_budget=None; reserved for live execution."),
    "high-value-escalation": (
        "Active when STOP is proposed above Rs 5,00,000; no STOP means no opportunity."
    ),
}


def _decimal(value: Decimal | None, places: str) -> str:
    if value is None:
        return "n/a"
    return format(value.quantize(Decimal(places), rounding=ROUND_HALF_UP), "f")


def _arm_payload(metrics: ArmMetrics) -> dict[str, Any]:
    return {
        "total_records": metrics.total_records,
        "paid_records": metrics.paid_records,
        "billed_paise": metrics.billed_paise,
        "recovered_paise": metrics.recovered_paise,
        "recovered_display": format_inr(metrics.recovered_paise),
        "recovery_rate_percent": _decimal(metrics.recovery_rate_percent, "0.01"),
        "record_recovery_rate_percent": _decimal(metrics.record_recovery_rate_percent, "0.01"),
        "contacts_made": metrics.contacts_made,
        "payment_links_sent": metrics.payment_links_sent,
        "contacts_per_rupee_recovered": _decimal(
            metrics.contacts_per_rupee_recovered, "0.00000001"
        ),
        "false_interventions": metrics.false_interventions,
        "false_interventions_disputed": metrics.false_interventions_disputed,
        "false_interventions_already_paid": metrics.false_interventions_already_paid,
        "policy_enabled": metrics.policy_enabled,
        "policy_vetoes": metrics.policy_vetoes,
        "regulatory_vetoes": metrics.regulatory_vetoes,
        "merchant_vetoes": metrics.merchant_vetoes,
        "policy_modifications": metrics.policy_modifications,
        "deferred_vetoes": metrics.deferred_vetoes,
        "stop_decisions": metrics.stop_decisions,
        "automated_escalations": metrics.automated_escalations,
        "payer_human_queue": metrics.payer_human_queue,
        "unresolved_records": metrics.unresolved_records,
        "written_off_records": metrics.written_off_records,
        "rule_firings": metrics.rule_firings,
    }


def render_json(report: MetricReport) -> str:
    """Return a stable, presentation-ready JSON report."""
    payload = {
        "schema_version": 2,
        "definitions": DEFINITIONS,
        "rule_run_notes": RULE_RUN_NOTES,
        "arms": {metrics.arm.value.lower(): _arm_payload(metrics) for metrics in report.arms},
    }
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def _title(arm: Arm) -> str:
    return {
        Arm.CONTROL: "Control",
        Arm.BASELINE: "Baseline",
        Arm.POLICY_BASELINE: "Baseline + policy",
        Arm.AGENT: "Agent",
    }[arm]


def render_markdown(report: MetricReport) -> str:
    """Return the full comparison table, including losses and dormant rules."""

    def policy_value(item: ArmMetrics, value: int) -> str:
        return str(value) if item.policy_enabled else "n/a (bypassed)"

    headers = ["Metric", *(_title(item.arm) for item in report.arms)]
    rows: list[tuple[str, Callable[[ArmMetrics], str]]] = [
        (
            "Recovery rate (value)",
            lambda item: f"{_decimal(item.recovery_rate_percent, '0.1')}%",
        ),
        (
            "Recovery rate (record count)",
            lambda item: f"{_decimal(item.record_recovery_rate_percent, '0.1')}%",
        ),
        ("Records paid", lambda item: f"{item.paid_records} / {item.total_records}"),
        ("Rs recovered", lambda item: format_inr(item.recovered_paise)),
        ("Contacts made", lambda item: str(item.contacts_made)),
        ("Payment links sent", lambda item: str(item.payment_links_sent)),
        (
            "Contacts per Rs recovered",
            lambda item: _decimal(item.contacts_per_rupee_recovered, "0.00000001"),
        ),
        ("False interventions", lambda item: str(item.false_interventions)),
        ("- on disputed invoices", lambda item: str(item.false_interventions_disputed)),
        (
            "- on already-paid / unreconciled invoices",
            lambda item: str(item.false_interventions_already_paid),
        ),
        ("Policy vetoes", lambda item: policy_value(item, item.policy_vetoes)),
        (
            "- regulatory-source vetoes",
            lambda item: policy_value(item, item.regulatory_vetoes),
        ),
        (
            "- merchant-policy vetoes",
            lambda item: policy_value(item, item.merchant_vetoes),
        ),
        (
            "Policy modifications",
            lambda item: policy_value(item, item.policy_modifications),
        ),
        ("Deferred vetoes", lambda item: policy_value(item, item.deferred_vetoes)),
        ("STOP decisions", lambda item: str(item.stop_decisions)),
        ("Escalated to human (agent-selected)", lambda item: str(item.automated_escalations)),
        ("Human queue from payer response", lambda item: str(item.payer_human_queue)),
        (
            "Unresolved / written off",
            lambda item: f"{item.unresolved_records} / {item.written_off_records}",
        ),
    ]

    lines = [
        "# Recoup metric report",
        "",
        "Definitions:",
        "",
        "- Value recovery denominator: `billed_paise` on the INTAKE rows.",
        "- Record recovery rate: final `PAID` records divided by opening record count.",
        "- False intervention: an executed contact on an invoice carrying the held-out "
        "`DISPUTED` or `ALREADY_PAID_UNRECONCILED` flag.",
        "- Escalations selected by the strategy are separated from final human-queue "
        "cases caused by payer responses.",
        "- A rule firing is the `rule_id` recorded on the decision row: the first veto "
        "or first modification.",
        "",
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    for label, render in rows:
        lines.append("| " + " | ".join([label, *(render(item) for item in report.arms)]) + " |")

    lines.extend(
        [
            "",
            "## Recorded policy-rule firings",
            "",
            "A number means the policy engine ran. `bypassed` means that arm did not run "
            "policy at all; the run-status note explains every meaningful zero.",
            "",
            "| Rule | Run status | " + " | ".join(_title(item.arm) for item in report.arms) + " |",
            "|" + "|".join("---" for _ in range(len(report.arms) + 2)) + "|",
        ]
    )
    for rule in RULE_ORDER:
        counts = [
            str(item.rule_firings.get(rule.rule_id, 0)) if item.policy_enabled else "bypassed"
            for item in report.arms
        ]
        lines.append(
            "| `"
            + rule.rule_id
            + "` | "
            + RULE_RUN_NOTES[rule.rule_id]
            + " | "
            + " | ".join(counts)
            + " |"
        )

    lines.extend(["", "## Interpretation notes", ""])
    if Arm.POLICY_BASELINE in {item.arm for item in report.arms}:
        lines.append(
            "- The two baseline columns use the identical naive proposer; their only "
            "difference is whether the policy engine runs. Baseline + policy versus "
            "agent then isolates proposer value with policy held constant."
        )
    for item in report.arms:
        if item.arm is Arm.AGENT and item.written_off_records == 0 and item.stop_decisions == 0:
            lines.append(
                f"- Agent write-offs are zero because the 28-day horizon ends mid-ladder: "
                f"it made 0 STOP decisions after {item.deferred_vetoes} deferred vetoes. "
                "This is horizon truncation, not evidence of restraint."
            )
    lines.append(
        "- Veto provenance counts only VETOED decisions. Merchant-source modifications "
        "are reported separately and are not regulatory vetoes."
    )
    return "\n".join(lines) + "\n"


def write_reports(report: MetricReport, out_dir: Path) -> tuple[Path, Path]:
    """Write both required formats and return ``(json_path, markdown_path)``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "metrics.json"
    markdown_path = out_dir / "metrics.md"
    json_path.write_text(render_json(report), encoding="utf-8", newline="")
    markdown_path.write_text(render_markdown(report), encoding="utf-8", newline="")
    return json_path, markdown_path
