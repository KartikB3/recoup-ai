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
        "contacts_made": metrics.contacts_made,
        "contacts_per_rupee_recovered": _decimal(
            metrics.contacts_per_rupee_recovered, "0.00000001"
        ),
        "false_interventions": metrics.false_interventions,
        "policy_vetoes": metrics.policy_vetoes,
        "automated_escalations": metrics.automated_escalations,
        "payer_human_queue": metrics.payer_human_queue,
        "unresolved_records": metrics.unresolved_records,
        "written_off_records": metrics.written_off_records,
        "rule_firings": metrics.rule_firings,
    }


def render_json(report: MetricReport) -> str:
    """Return a stable, presentation-ready JSON report."""
    payload = {
        "schema_version": 1,
        "definitions": DEFINITIONS,
        "arms": {metrics.arm.value.lower(): _arm_payload(metrics) for metrics in report.arms},
    }
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def _title(arm: Arm) -> str:
    return {
        Arm.CONTROL: "Control",
        Arm.BASELINE: "Baseline",
        Arm.AGENT: "Agent",
    }[arm]


def render_markdown(report: MetricReport) -> str:
    """Return the full comparison table, including losses and dormant rules."""
    headers = ["Metric", *(_title(item.arm) for item in report.arms)]
    rows: list[tuple[str, Callable[[ArmMetrics], str]]] = [
        ("Recovery rate", lambda item: f"{_decimal(item.recovery_rate_percent, '0.1')}%"),
        ("₹ recovered", lambda item: format_inr(item.recovered_paise)),
        ("Contacts made", lambda item: str(item.contacts_made)),
        (
            "Contacts per ₹ recovered",
            lambda item: _decimal(item.contacts_per_rupee_recovered, "0.00000001"),
        ),
        ("False interventions", lambda item: str(item.false_interventions)),
        ("Policy vetoes", lambda item: str(item.policy_vetoes)),
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
        "- Recovery denominator: `billed_paise` on the INTAKE rows.",
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
            "Zeroes are included deliberately so a rule that silently stops firing is visible.",
            "",
            "| Rule | " + " | ".join(_title(item.arm) for item in report.arms) + " |",
            "|" + "|".join("---" for _ in range(len(report.arms) + 1)) + "|",
        ]
    )
    for rule in RULE_ORDER:
        counts = [str(item.rule_firings.get(rule.rule_id, 0)) for item in report.arms]
        lines.append("| `" + rule.rule_id + "` | " + " | ".join(counts) + " |")
    return "\n".join(lines) + "\n"


def write_reports(report: MetricReport, out_dir: Path) -> tuple[Path, Path]:
    """Write both required formats and return ``(json_path, markdown_path)``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "metrics.json"
    markdown_path = out_dir / "metrics.md"
    json_path.write_text(render_json(report), encoding="utf-8", newline="")
    markdown_path.write_text(render_markdown(report), encoding="utf-8", newline="")
    return json_path, markdown_path
