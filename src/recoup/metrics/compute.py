"""Metric computation from final records and their append-only audit rows."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from recoup.domain.enums import (
    Arm,
    Flag,
    Intervention,
    RecordState,
    RowKind,
    RuleKind,
    VerdictKind,
)
from recoup.domain.models import AuditRow, Invoice, Paise
from recoup.policy.rules import RULE_ORDER

HARM_FLAGS: frozenset[Flag] = frozenset({Flag.DISPUTED, Flag.ALREADY_PAID_UNRECONCILED})
REPORT_ARM_ORDER: tuple[Arm, ...] = (
    Arm.CONTROL,
    Arm.BASELINE,
    Arm.POLICY_BASELINE,
    Arm.AGENT,
)


@dataclass(frozen=True)
class ArmMetrics:
    """The full section 7a scorecard for one strategy."""

    arm: Arm
    total_records: int
    paid_records: int
    billed_paise: Paise
    recovered_paise: Paise
    recovery_rate_percent: Decimal
    record_recovery_rate_percent: Decimal
    contacts_made: int
    payment_links_sent: int
    contacts_per_rupee_recovered: Decimal | None
    false_interventions: int
    false_interventions_disputed: int
    false_interventions_already_paid: int
    policy_enabled: bool
    policy_vetoes: int
    regulatory_vetoes: int
    merchant_vetoes: int
    policy_modifications: int
    deferred_vetoes: int
    stop_decisions: int
    automated_escalations: int
    payer_human_queue: int
    unresolved_records: int
    written_off_records: int
    rule_firings: dict[str, int]


@dataclass(frozen=True)
class MetricReport:
    """A comparison whose order is stable in JSON, Markdown, and the CLI."""

    arms: tuple[ArmMetrics, ...]

    def for_arm(self, arm: Arm) -> ArmMetrics:
        """Return one arm or raise when the requested run was not supplied."""
        return next(item for item in self.arms if item.arm is arm)


def _billed_at_intake(rows: list[AuditRow]) -> Paise:
    """Sum the immutable opening amounts carried by INTAKE rows."""
    amounts: dict[str, int] = {}
    for row in rows:
        if row.kind is not RowKind.INTAKE or row.input_snapshot is None:
            continue
        amount = row.input_snapshot.get("amount_paise")
        if type(amount) is not int:
            raise ValueError(f"intake row {row.row_id} has no integer amount_paise")
        if row.record_id in amounts:
            raise ValueError(f"duplicate intake row for {row.record_id}")
        amounts[row.record_id] = amount
    if not amounts:
        raise ValueError("metrics require INTAKE rows to define the opening book")
    return sum(amounts.values())


def compute_arm_metrics(records: list[Invoice], rows: list[AuditRow]) -> ArmMetrics:
    """Score one arm without re-running anything that decided the audit rows."""
    if not rows:
        raise ValueError("metrics require at least one audit row")
    arm = rows[0].arm
    if any(row.arm is not arm for row in rows):
        raise ValueError("one arm metric input cannot mix audit arms")

    records_by_id = {record.invoice_id: record for record in records}
    if len(records_by_id) != len(records):
        raise ValueError("duplicate invoice ids in final records")

    billed_paise = _billed_at_intake(rows)
    recovered_paise = sum(record.recovered_paise for record in records)
    recovery_rate = (
        Decimal(recovered_paise) * Decimal(100) / Decimal(billed_paise)
        if billed_paise
        else Decimal(0)
    )

    contact_rows = [
        row
        for row in rows
        if row.action is not None and row.action.executed and row.action.contact_units > 0
    ]
    contacts_made = sum(row.action.contact_units for row in contact_rows if row.action is not None)
    contacts_per_rupee = (
        Decimal(contacts_made) * Decimal(100) / Decimal(recovered_paise)
        if recovered_paise
        else None
    )

    false_interventions = 0
    false_interventions_disputed = 0
    false_interventions_already_paid = 0
    for row in contact_rows:
        record = records_by_id.get(row.record_id)
        if record is None:
            raise ValueError(f"audit row names unknown record {row.record_id}")
        if record.flags & HARM_FLAGS and row.action is not None:
            false_interventions += row.action.contact_units
        if Flag.DISPUTED in record.flags and row.action is not None:
            false_interventions_disputed += row.action.contact_units
        if Flag.ALREADY_PAID_UNRECONCILED in record.flags and row.action is not None:
            false_interventions_already_paid += row.action.contact_units

    veto_rows = [
        row
        for row in rows
        if row.policy_verdict is not None and row.policy_verdict.verdict is VerdictKind.VETOED
    ]

    def vetoes_from(kind: RuleKind) -> int:
        return sum(
            row.policy_verdict is not None
            and row.policy_verdict.rule_source is not None
            and row.policy_verdict.rule_source.kind is kind
            for row in veto_rows
        )

    automated_rows = [
        row
        for row in rows
        if row.action is not None
        and row.action.executed
        and row.action.intervention is Intervention.ESCALATE_HUMAN
    ]
    automated_ids = {row.record_id for row in automated_rows}
    payer_human_queue = sum(
        1
        for record in records
        if record.state is RecordState.HUMAN_QUEUE and record.invoice_id not in automated_ids
    )

    rule_firings = {rule.rule_id: 0 for rule in RULE_ORDER}
    for row in rows:
        if row.policy_rule is not None:
            rule_firings[row.policy_rule] = rule_firings.get(row.policy_rule, 0) + 1

    return ArmMetrics(
        arm=arm,
        total_records=len(records),
        paid_records=sum(record.state is RecordState.PAID for record in records),
        billed_paise=billed_paise,
        recovered_paise=recovered_paise,
        recovery_rate_percent=recovery_rate,
        record_recovery_rate_percent=(
            Decimal(sum(record.state is RecordState.PAID for record in records))
            * Decimal(100)
            / Decimal(len(records))
            if records
            else Decimal(0)
        ),
        contacts_made=contacts_made,
        payment_links_sent=sum(
            row.action.api_units for row in rows if row.action is not None and row.action.executed
        ),
        contacts_per_rupee_recovered=contacts_per_rupee,
        false_interventions=false_interventions,
        false_interventions_disputed=false_interventions_disputed,
        false_interventions_already_paid=false_interventions_already_paid,
        policy_enabled=any(row.policy_verdict is not None for row in rows),
        policy_vetoes=len(veto_rows),
        regulatory_vetoes=vetoes_from(RuleKind.REGULATORY),
        merchant_vetoes=vetoes_from(RuleKind.MERCHANT),
        policy_modifications=sum(
            row.policy_verdict is not None and row.policy_verdict.verdict is VerdictKind.MODIFIED
            for row in rows
        ),
        deferred_vetoes=sum(
            row.policy_verdict is not None
            and row.policy_verdict.verdict is VerdictKind.VETOED
            and row.policy_verdict.defer_to_tick is not None
            for row in rows
        ),
        stop_decisions=sum(
            row.action is not None
            and row.action.executed
            and row.action.intervention is Intervention.STOP
            for row in rows
        ),
        automated_escalations=len(automated_rows),
        payer_human_queue=payer_human_queue,
        unresolved_records=sum(
            record.state not in {RecordState.PAID, RecordState.WRITTEN_OFF} for record in records
        ),
        written_off_records=sum(record.state is RecordState.WRITTEN_OFF for record in records),
        rule_firings=dict(sorted(rule_firings.items())),
    )


def compute_metrics(
    arm_inputs: Mapping[Arm, tuple[list[Invoice], list[AuditRow]]],
) -> MetricReport:
    """Score all supplied arms in the fixed comparison order."""
    computed = {
        arm: compute_arm_metrics(records, rows) for arm, (records, rows) in arm_inputs.items()
    }
    return MetricReport(arms=tuple(computed[arm] for arm in REPORT_ARM_ORDER if arm in computed))
