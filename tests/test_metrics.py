"""The four-arm Phase 2 scorecard and its persisted representations."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from typer.testing import CliRunner

from recoup.baseline.naive_chaser import NaiveChaser, PolicyNaiveChaser
from recoup.cli import app
from recoup.domain.enums import Arm
from recoup.generator.generate import generate_batch
from recoup.metrics.compute import MetricReport, compute_metrics
from recoup.metrics.report import render_json, render_markdown, write_reports
from recoup.policy.context import MerchantPolicy
from recoup.policy.engine import PolicyEngine
from recoup.reasoner.fallback import DeterministicFallback
from recoup.runner.batch import AlwaysWait, run_batch


@pytest.fixture(scope="module")
def report() -> MetricReport:
    batch = generate_batch(42)
    control = run_batch(batch.records, AlwaysWait(), seed=42, run_id="metrics")
    baseline = run_batch(batch.records, NaiveChaser(), seed=42, run_id="metrics")
    policy_baseline = run_batch(
        batch.records,
        PolicyNaiveChaser(),
        seed=42,
        run_id="metrics",
        policy=PolicyEngine(MerchantPolicy(link_budget=None)),
    )
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
            Arm.POLICY_BASELINE: (policy_baseline.records, policy_baseline.log.rows),
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

    policy_baseline = report.for_arm(Arm.POLICY_BASELINE)
    assert policy_baseline.contacts_made == 161
    assert policy_baseline.recovered_paise == 1_430_366_723
    assert policy_baseline.paid_records == 63
    assert policy_baseline.false_interventions == 23
    assert policy_baseline.policy_vetoes == 247
    assert policy_baseline.regulatory_vetoes == 0
    assert policy_baseline.merchant_vetoes == 247
    assert policy_baseline.rule_firings["payer-contact-frequency"] == 65
    assert policy_baseline.rule_firings["payer-contact-spacing"] == 182


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
    assert agent.regulatory_vetoes == 8
    assert agent.merchant_vetoes == 223
    assert agent.policy_modifications == 16
    assert agent.false_interventions_disputed == 8
    assert agent.false_interventions_already_paid == 15
    assert baseline.false_interventions_disputed == 76
    assert baseline.false_interventions_already_paid == 28
    assert agent.payment_links_sent == 71
    assert baseline.payment_links_sent == 225
    assert not baseline.policy_enabled
    assert report.for_arm(Arm.POLICY_BASELINE).policy_enabled
    assert agent.rule_firings["rbi-contact-hours"] > 0


def test_markdown_and_json_carry_all_four_arms_and_every_rule(
    report: MetricReport,
) -> None:
    markdown = render_markdown(report)
    assert "| Metric | Control | Baseline | Baseline + policy | Agent |" in markdown
    assert "False interventions" in markdown
    assert "Unresolved / written off" in markdown
    assert "horizon truncation" in markdown
    assert "bypassed" in markdown
    for rule_id in report.for_arm(Arm.AGENT).rule_firings:
        assert f"`{rule_id}`" in markdown

    payload = json.loads(render_json(report))
    assert list(payload["arms"]) == ["control", "baseline", "policy_baseline", "agent"]
    assert payload["arms"]["control"]["contacts_per_rupee_recovered"] == "0.00000000"
    assert payload["arms"]["baseline"]["policy_enabled"] is False
    assert payload["arms"]["policy_baseline"]["policy_enabled"] is True
    assert set(payload["rule_run_notes"]) == set(payload["arms"]["agent"]["rule_firings"])


def test_both_formats_are_written_together(report: MetricReport, tmp_path: Path) -> None:
    json_path, markdown_path = write_reports(report, tmp_path)
    assert json_path.name == "metrics.json"
    assert markdown_path.name == "metrics.md"
    assert json.loads(json_path.read_text(encoding="utf-8"))["schema_version"] == 2
    assert markdown_path.read_text(encoding="utf-8").startswith("# Recoup metric report")


def test_cli_both_means_all_four_comparison_arms(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        app,
        ["run", "--seed", "42", "--arm", "both", "--ticks", "1"],
    )
    assert result.exit_code == 0, result.output
    root = tmp_path / "runs" / "seed42-t1"
    for arm in ("control", "baseline", "policy_baseline", "agent"):
        assert (root / arm / "audit.jsonl").exists()
        assert (root / arm / "final.json").exists()
    assert (root / "metrics.json").exists()
    assert (root / "metrics.md").exists()
