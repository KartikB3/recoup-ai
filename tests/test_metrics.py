"""The three-arm Phase 2 scorecard and its persisted representations."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from typer.testing import CliRunner

from recoup.baseline.naive_chaser import NaiveChaser
from recoup.cli import app
from recoup.domain.enums import Arm
from recoup.generator.generate import generate_batch
from recoup.metrics.compute import MetricReport, compute_metrics
from recoup.metrics.report import render_json, render_markdown, write_reports
from recoup.policy.engine import PolicyEngine
from recoup.reasoner.fallback import DeterministicFallback
from recoup.runner.batch import AlwaysWait, run_batch


@pytest.fixture(scope="module")
def report() -> MetricReport:
    batch = generate_batch(42)
    control = run_batch(batch.records, AlwaysWait(), seed=42, run_id="metrics")
    baseline = run_batch(batch.records, NaiveChaser(), seed=42, run_id="metrics")
    agent = run_batch(
        batch.records,
        DeterministicFallback(),
        seed=42,
        run_id="metrics",
        policy=PolicyEngine(),
    )
    return compute_metrics(
        {
            Arm.CONTROL: (control.records, control.log.rows),
            Arm.BASELINE: (baseline.records, baseline.log.rows),
            Arm.AGENT: (agent.records, agent.log.rows),
        }
    )


def test_phase1_regression_numbers_are_unchanged(report: MetricReport) -> None:
    baseline = report.for_arm(Arm.BASELINE)
    control = report.for_arm(Arm.CONTROL)
    assert baseline.contacts_made == 459
    assert baseline.recovered_paise == 1_577_122_615
    assert baseline.paid_records == 70
    assert baseline.payer_human_queue == 28
    assert baseline.written_off_records == 19
    assert control.contacts_made == 0
    assert control.recovered_paise == 1_246_014_875
    assert control.paid_records == 54


def test_metric_definitions_include_losses_and_zero_contact_control(
    report: MetricReport,
) -> None:
    control = report.for_arm(Arm.CONTROL)
    baseline = report.for_arm(Arm.BASELINE)
    agent = report.for_arm(Arm.AGENT)
    assert control.contacts_per_rupee_recovered == Decimal(0)
    assert baseline.false_interventions == 104
    assert 0 < agent.false_interventions < baseline.false_interventions
    assert agent.policy_vetoes > 0
    assert agent.rule_firings["rbi-contact-hours"] > 0


def test_markdown_and_json_carry_all_three_arms_and_every_rule(
    report: MetricReport,
) -> None:
    markdown = render_markdown(report)
    assert "| Metric | Control | Baseline | Agent |" in markdown
    assert "False interventions" in markdown
    assert "Unresolved / written off" in markdown
    for rule_id in report.for_arm(Arm.AGENT).rule_firings:
        assert f"`{rule_id}`" in markdown

    payload = json.loads(render_json(report))
    assert list(payload["arms"]) == ["control", "baseline", "agent"]
    assert payload["arms"]["control"]["contacts_per_rupee_recovered"] == "0.00000000"


def test_both_formats_are_written_together(report: MetricReport, tmp_path: Path) -> None:
    json_path, markdown_path = write_reports(report, tmp_path)
    assert json_path.name == "metrics.json"
    assert markdown_path.name == "metrics.md"
    assert json.loads(json_path.read_text(encoding="utf-8"))["schema_version"] == 1
    assert markdown_path.read_text(encoding="utf-8").startswith("# Recoup metric report")


def test_cli_both_means_control_baseline_and_agent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        app,
        ["run", "--seed", "42", "--arm", "both", "--ticks", "1"],
    )
    assert result.exit_code == 0, result.output
    root = tmp_path / "runs" / "seed42-t1"
    for arm in ("control", "baseline", "agent"):
        assert (root / arm / "audit.jsonl").exists()
        assert (root / arm / "final.json").exists()
    assert (root / "metrics.json").exists()
    assert (root / "metrics.md").exists()
