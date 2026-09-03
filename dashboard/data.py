"""Typed, offline-only readers for Recoup dashboard artifacts.

The dashboard never calls the runner, the reasoner, Razorpay, or the network.
It reads the committed ``runs/<id>/`` evidence and validates the domain-shaped
files at the boundary before any view renders them.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast

from pydantic import TypeAdapter

from recoup.domain.enums import ExecutorKind, RowKind, RuleKind, VerdictKind
from recoup.domain.models import AuditRow, Invoice, RuleSource
from recoup.generator.generate import Batch, load_batch
from recoup.ledger.clock import format_tick

SAFE_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
ARM_ORDER = ("control", "baseline", "policy_baseline", "agent")
ARM_LABELS = {
    "control": "Do nothing",
    "baseline": "Naive chase",
    "policy_baseline": "Naive + policy",
    "agent": "Deterministic agent",
}

_INVOICE_LIST = TypeAdapter(list[Invoice])


@dataclass(frozen=True)
class Scorecard:
    """The dashboard subset of one arm's metric artifact."""

    key: str
    label: str
    run_id: str
    arm: str
    total_records: int
    paid_records: int
    billed_paise: int
    recovered_paise: int
    recovery_rate_percent: Decimal
    contacts_made: int
    payment_links_sent: int
    false_interventions: int
    false_interventions_disputed: int
    false_interventions_already_paid: int
    policy_enabled: bool
    policy_vetoes: int
    regulatory_vetoes: int
    merchant_vetoes: int
    policy_modifications: int
    automated_escalations: int
    unresolved_records: int
    written_off_records: int
    rule_firings: Mapping[str, int]
    is_model_output: bool = False


@dataclass(frozen=True)
class MetricsArtifact:
    """Validated metrics and rule annotations for one run directory."""

    run_id: str
    schema_version: int
    definitions: Mapping[str, str]
    rule_run_notes: Mapping[str, str]
    scorecards: tuple[Scorecard, ...]

    def for_arm(self, arm: str) -> Scorecard:
        """Return one arm scorecard or raise a useful artifact error."""
        return next(item for item in self.scorecards if item.arm == arm)


@dataclass(frozen=True)
class ArmArtifact:
    """Opening book, closing book and append-only log for one arm."""

    run_id: str
    arm: str
    path: Path
    batch: Batch
    final_records: tuple[Invoice, ...]
    rows: tuple[AuditRow, ...]

    @property
    def opening_by_id(self) -> Mapping[str, Invoice]:
        return {record.invoice_id: record for record in self.batch.records}

    @property
    def final_by_id(self) -> Mapping[str, Invoice]:
        return {record.invoice_id: record for record in self.final_records}


def _mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be a JSON object")
    return cast(Mapping[str, object], value)


def _integer(value: object, context: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{context} must be an integer")
    return value


def _boolean(value: object, context: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{context} must be a boolean")
    return value


def _decimal(value: object, context: str) -> Decimal:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise ValueError(f"{context} must be a decimal string")
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{context} is not a decimal") from exc


def _string_map(value: object, context: str) -> Mapping[str, str]:
    raw = _mapping(value, context)
    if not all(isinstance(key, str) and isinstance(item, str) for key, item in raw.items()):
        raise ValueError(f"{context} must map strings to strings")
    return cast(Mapping[str, str], raw)


def _integer_map(value: object, context: str) -> Mapping[str, int]:
    raw = _mapping(value, context)
    if not all(isinstance(key, str) and type(item) is int for key, item in raw.items()):
        raise ValueError(f"{context} must map strings to integers")
    return cast(Mapping[str, int], raw)


def run_path(runs_root: Path, run_id: str) -> Path:
    """Resolve a run id without allowing it to escape the configured root."""
    if SAFE_RUN_ID.fullmatch(run_id) is None:
        raise ValueError(f"unsafe run id {run_id!r}")
    root = runs_root.resolve()
    candidate = (root / run_id).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(f"run id {run_id!r} escapes {root}")
    return candidate


def discover_run_ids(runs_root: Path) -> tuple[str, ...]:
    """Find dashboard-ready runs, newest first, without opening their data."""
    if not runs_root.is_dir():
        return ()
    candidates = [
        path for path in runs_root.iterdir() if path.is_dir() and (path / "metrics.json").is_file()
    ]
    candidates.sort(key=lambda path: (path.stat().st_mtime_ns, path.name), reverse=True)
    return tuple(path.name for path in candidates)


def default_run_id(run_ids: Iterable[str]) -> str:
    """Prefer the canonical evidence book, then fall back to the newest run."""
    choices = tuple(run_ids)
    if not choices:
        raise ValueError("no runs with metrics.json were found")
    return "seed42" if "seed42" in choices else choices[0]


def load_metrics(runs_root: Path, run_id: str) -> MetricsArtifact:
    """Read and validate ``metrics.json`` for one run."""
    path = run_path(runs_root, run_id) / "metrics.json"
    if not path.is_file():
        raise FileNotFoundError(f"{path} does not exist; run `recoup metrics {run_id}`")
    payload = _mapping(json.loads(path.read_text(encoding="utf-8")), str(path))
    schema_version = _integer(payload.get("schema_version"), "metrics.schema_version")
    definitions = _string_map(payload.get("definitions"), "metrics.definitions")
    notes = _string_map(payload.get("rule_run_notes"), "metrics.rule_run_notes")
    arms = _mapping(payload.get("arms"), "metrics.arms")

    scorecards: list[Scorecard] = []
    for arm in ARM_ORDER:
        if arm not in arms:
            continue
        item = _mapping(arms[arm], f"metrics.arms.{arm}")
        scorecards.append(
            Scorecard(
                key=arm,
                label=ARM_LABELS[arm],
                run_id=run_id,
                arm=arm,
                total_records=_integer(item.get("total_records"), f"{arm}.total_records"),
                paid_records=_integer(item.get("paid_records"), f"{arm}.paid_records"),
                billed_paise=_integer(item.get("billed_paise"), f"{arm}.billed_paise"),
                recovered_paise=_integer(item.get("recovered_paise"), f"{arm}.recovered_paise"),
                recovery_rate_percent=_decimal(
                    item.get("recovery_rate_percent"), f"{arm}.recovery_rate_percent"
                ),
                contacts_made=_integer(item.get("contacts_made"), f"{arm}.contacts_made"),
                payment_links_sent=_integer(
                    item.get("payment_links_sent"), f"{arm}.payment_links_sent"
                ),
                false_interventions=_integer(
                    item.get("false_interventions"), f"{arm}.false_interventions"
                ),
                false_interventions_disputed=_integer(
                    item.get("false_interventions_disputed"),
                    f"{arm}.false_interventions_disputed",
                ),
                false_interventions_already_paid=_integer(
                    item.get("false_interventions_already_paid"),
                    f"{arm}.false_interventions_already_paid",
                ),
                policy_enabled=_boolean(item.get("policy_enabled"), f"{arm}.policy_enabled"),
                policy_vetoes=_integer(item.get("policy_vetoes"), f"{arm}.policy_vetoes"),
                regulatory_vetoes=_integer(
                    item.get("regulatory_vetoes"), f"{arm}.regulatory_vetoes"
                ),
                merchant_vetoes=_integer(item.get("merchant_vetoes"), f"{arm}.merchant_vetoes"),
                policy_modifications=_integer(
                    item.get("policy_modifications"), f"{arm}.policy_modifications"
                ),
                automated_escalations=_integer(
                    item.get("automated_escalations"), f"{arm}.automated_escalations"
                ),
                unresolved_records=_integer(
                    item.get("unresolved_records"), f"{arm}.unresolved_records"
                ),
                written_off_records=_integer(
                    item.get("written_off_records"), f"{arm}.written_off_records"
                ),
                rule_firings=_integer_map(item.get("rule_firings"), f"{arm}.rule_firings"),
            )
        )
    if not scorecards:
        raise ValueError(f"{path} contains no recognised arms")
    return MetricsArtifact(
        run_id=run_id,
        schema_version=schema_version,
        definitions=definitions,
        rule_run_notes=notes,
        scorecards=tuple(scorecards),
    )


def comparison_scorecards(runs_root: Path, selected_run_id: str) -> tuple[Scorecard, ...]:
    """Build the honest four-arm table plus a distinct cost-tiered fifth arm.

    The canonical and real-model evidence deliberately live in separate run
    directories. Their documented ``-tiered`` naming contract is used only to
    place the two agent results beside one another; no number is recomputed.
    """
    base_run_id = (
        selected_run_id.removesuffix("-tiered")
        if selected_run_id.endswith("-tiered")
        else selected_run_id
    )
    base_path = run_path(runs_root, base_run_id) / "metrics.json"
    primary_run_id = base_run_id if base_path.is_file() else selected_run_id
    primary = load_metrics(runs_root, primary_run_id)
    cards = list(primary.scorecards)

    tiered_run_id = f"{base_run_id}-tiered"
    tiered_path = run_path(runs_root, tiered_run_id) / "metrics.json"
    if tiered_path.is_file() and tiered_run_id != primary_run_id:
        tiered = load_metrics(runs_root, tiered_run_id).for_arm("agent")
        cards.append(
            replace(
                tiered,
                key="agent_model_triage",
                label="Model triage",
                is_model_output=True,
            )
        )
    elif selected_run_id.endswith("-tiered"):
        cards = [
            replace(
                item,
                label="Model triage" if item.arm == "agent" else item.label,
                is_model_output=item.arm == "agent",
            )
            for item in cards
        ]
    return tuple(cards)


def available_arms(runs_root: Path, run_id: str) -> tuple[str, ...]:
    """Return arms that have all three files required by the views."""
    root = run_path(runs_root, run_id)
    return tuple(
        arm
        for arm in ARM_ORDER
        if all(
            (root / arm / name).is_file() for name in ("batch.json", "final.json", "audit.jsonl")
        )
    )


def load_arm(runs_root: Path, run_id: str, arm: str) -> ArmArtifact:
    """Load a complete arm from disk and validate every row."""
    if arm not in ARM_ORDER:
        raise ValueError(f"unknown arm {arm!r}")
    path = run_path(runs_root, run_id) / arm
    batch_path = path / "batch.json"
    final_path = path / "final.json"
    audit_path = path / "audit.jsonl"
    for required in (batch_path, final_path, audit_path):
        if not required.is_file():
            raise FileNotFoundError(f"missing dashboard artifact: {required}")

    batch = load_batch(batch_path)
    final_records = tuple(_INVOICE_LIST.validate_json(final_path.read_text(encoding="utf-8")))
    rows = tuple(
        AuditRow.model_validate_json(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    if not rows:
        raise ValueError(f"{audit_path} contains no rows")
    if any(row.run_id != run_id or row.arm.value.lower() != arm for row in rows):
        raise ValueError(f"{audit_path} mixes run or arm identities")
    return ArmArtifact(
        run_id=run_id,
        arm=arm,
        path=path,
        batch=batch,
        final_records=final_records,
        rows=rows,
    )


def payer_names(artifact: ArmArtifact) -> tuple[str, ...]:
    """All payer names, alphabetically, as the primary product key."""
    return tuple(sorted({record.payer_name for record in artifact.batch.records}))


def invoice_ids_for_payer(artifact: ArmArtifact, payer_name: str) -> tuple[str, ...]:
    """Invoices belonging to a selected named payer."""
    return tuple(
        record.invoice_id for record in artifact.batch.records if record.payer_name == payer_name
    )


def rows_for_invoice(artifact: ArmArtifact, invoice_id: str) -> tuple[AuditRow, ...]:
    """Every append-only event for one invoice, in row order."""
    return tuple(row for row in artifact.rows if row.record_id == invoice_id)


def featured_story(artifact: ArmArtifact) -> tuple[str, str]:
    """Choose a payer story that demonstrates both judgement and guardrails.

    A WAIT plus a verified regulatory veto wins. The fallback order remains
    useful for arbitrary run directories that do not contain that exact story.
    """
    opening = artifact.opening_by_id
    candidates: list[tuple[tuple[int, ...], str, str]] = []
    for invoice_id, record in opening.items():
        rows = rows_for_invoice(artifact, invoice_id)
        waits = sum(
            row.action is not None and row.action.intervention.value == "WAIT" for row in rows
        )
        vetoes = [
            row
            for row in rows
            if row.policy_verdict is not None and row.policy_verdict.verdict is VerdictKind.VETOED
        ]
        regulatory = sum(
            row.policy_verdict is not None
            and row.policy_verdict.rule_source is not None
            and row.policy_verdict.rule_source.kind is RuleKind.REGULATORY
            and row.policy_verdict.rule_source.verified is True
            for row in vetoes
        )
        score = (
            int(waits > 0 and regulatory > 0),
            regulatory,
            int(waits > 0 and bool(vetoes)),
            waits,
            len(vetoes),
            int(record.spotlight),
            len(rows),
        )
        candidates.append((score, record.payer_name, invoice_id))
    if not candidates:
        raise ValueError(f"{artifact.path} contains no invoices")
    _score, payer_name, invoice_id = max(candidates)
    return payer_name, invoice_id


def source_status(source: RuleSource) -> tuple[str, str]:
    """Return a truthful short badge and tone for a rule source."""
    if source.kind is RuleKind.MERCHANT:
        return "Merchant policy · verification N/A", "merchant"
    if source.verified is True:
        return "Verified at issuing body", "verified"
    return "Unverified · exclude from demo", "unverified"


def flatten_audit_rows(artifact: ArmArtifact) -> list[dict[str, object]]:
    """Flatten domain rows for the filterable table without losing raw JSON."""
    names = {record.invoice_id: record.payer_name for record in artifact.batch.records}
    flattened: list[dict[str, object]] = []
    for row in artifact.rows:
        verdict = row.policy_verdict
        action = row.action
        outcome = row.outcome
        flattened.append(
            {
                "row_id": row.row_id,
                "tick": row.tick,
                "virtual_time": format_tick(row.tick),
                "kind": row.kind.value,
                "record_id": row.record_id,
                "payer_name": names.get(row.record_id, "Unknown payer"),
                "proposal": row.llm_proposal.intervention.value if row.llm_proposal else "",
                "verdict": verdict.verdict.value if verdict else "",
                "rule_id": verdict.rule_id or "" if verdict else "",
                "source_kind": verdict.rule_source.kind.value
                if verdict and verdict.rule_source
                else "",
                "source_verified": verdict.rule_source.verified
                if verdict and verdict.rule_source
                else None,
                "action": action.intervention.value if action else "",
                "executed": action.executed if action else None,
                "executor": action.executor.value if action else "",
                "external_ref": action.external_ref or "" if action else "",
                "outcome": outcome.kind.value if outcome else "",
                "amount_paise": outcome.amount_paise if outcome else 0,
                "prev_row_hash": row.prev_row_hash,
            }
        )
    return flattened


def filter_audit_rows(
    rows: Iterable[Mapping[str, object]],
    *,
    kinds: set[str] | None = None,
    verdict: str | None = None,
    rule_id: str | None = None,
    executor: str | None = None,
    query: str = "",
) -> list[Mapping[str, object]]:
    """Apply the raw-view filters as an independently testable pure function."""
    needle = query.strip().casefold()
    filtered: list[Mapping[str, object]] = []
    for row in rows:
        if kinds is not None and str(row["kind"]) not in kinds:
            continue
        if verdict is not None and row["verdict"] != verdict:
            continue
        if rule_id is not None and row["rule_id"] != rule_id:
            continue
        if executor is not None and row["executor"] != executor:
            continue
        haystack = " ".join(
            str(row[key])
            for key in ("row_id", "record_id", "payer_name", "proposal", "rule_id", "outcome")
        ).casefold()
        if needle and needle not in haystack:
            continue
        filtered.append(row)
    return filtered


def audit_filter_options(rows: Iterable[Mapping[str, object]]) -> Mapping[str, tuple[str, ...]]:
    """Stable filter values present in a flattened audit artifact."""
    materialised = tuple(rows)
    return {
        "kinds": tuple(kind.value for kind in RowKind),
        "verdicts": tuple(sorted({str(row["verdict"]) for row in materialised if row["verdict"]})),
        "rules": tuple(sorted({str(row["rule_id"]) for row in materialised if row["rule_id"]})),
        "executors": tuple(
            kind.value
            for kind in ExecutorKind
            if any(row["executor"] == kind.value for row in materialised)
        ),
    }


def serialise_filtered_jsonl(
    artifact: ArmArtifact, filtered: Iterable[Mapping[str, object]]
) -> str:
    """Return original domain rows for the filtered download, in row order."""
    wanted = {cast(int, item["row_id"]) for item in filtered}
    return "".join(
        json.dumps(row.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")) + "\n"
        for row in artifact.rows
        if row.row_id in wanted
    )


def raw_row(artifact: ArmArtifact, row_id: int) -> Mapping[str, object]:
    """Return a JSON-safe raw row for the inspector."""
    row = next(row for row in artifact.rows if row.row_id == row_id)
    return cast(Mapping[str, object], row.model_dump(mode="json"))
