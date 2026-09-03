"""Phase 5: the dashboard is an offline view over committed evidence."""

from __future__ import annotations

import json
from pathlib import Path

from dashboard.data import (
    comparison_scorecards,
    default_run_id,
    discover_run_ids,
    featured_story,
    filter_audit_rows,
    flatten_audit_rows,
    load_arm,
    rows_for_invoice,
    run_path,
    source_status,
)
from streamlit.testing.v1 import AppTest

from recoup.domain.enums import RuleKind, VerdictKind
from recoup.domain.models import RuleSource

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"


def test_summary_keeps_four_canonical_arms_and_adds_model_as_a_fifth() -> None:
    """Paid model output must never relabel the deterministic agent column."""
    cards = comparison_scorecards(RUNS, "seed42")

    assert [card.label for card in cards] == [
        "Do nothing",
        "Naive chase",
        "Naive + policy",
        "Deterministic agent",
        "Model triage",
    ]
    assert [card.run_id for card in cards] == [
        "seed42",
        "seed42",
        "seed42",
        "seed42",
        "seed42-tiered",
    ]
    assert cards[3].is_model_output is False
    assert cards[3].false_interventions == 23
    assert cards[4].is_model_output is True
    assert cards[4].false_interventions == 0
    assert cards[4].recovery_rate_percent < cards[3].recovery_rate_percent


def test_default_is_canonical_even_when_tiered_artifact_is_newer() -> None:
    """The opening frame needs the recoverable floor plus its fifth model arm."""
    run_ids = discover_run_ids(RUNS)
    assert "seed42" in run_ids
    assert default_run_id(run_ids) == "seed42"


def test_featured_named_payer_contains_wait_and_verified_regulatory_veto() -> None:
    """The 1:30 and 2:15 video beats exist in one honest invoice story."""
    artifact = load_arm(RUNS, "seed42", "agent")
    payer_name, invoice_id = featured_story(artifact)
    rows = rows_for_invoice(artifact, invoice_id)

    assert payer_name == "Netra Optics & Lenses"
    assert invoice_id == "ASH-2026-0045"
    assert any(row.action is not None and row.action.intervention.value == "WAIT" for row in rows)
    regulatory_vetoes = [
        row.policy_verdict
        for row in rows
        if row.policy_verdict is not None
        and row.policy_verdict.verdict is VerdictKind.VETOED
        and row.policy_verdict.rule_source is not None
        and row.policy_verdict.rule_source.kind is RuleKind.REGULATORY
    ]
    assert len(regulatory_vetoes) == 1
    source = regulatory_vetoes[0].rule_source
    assert source is not None
    assert source.verified is True
    assert source.scope_caveat
    assert source_status(source) == ("Verified at issuing body", "verified")


def test_audit_filters_operate_on_rows_read_from_jsonl() -> None:
    artifact = load_arm(RUNS, "seed42", "agent")
    rows = flatten_audit_rows(artifact)

    vetoes = filter_audit_rows(rows, verdict="VETOED", query="netra optics")
    rbi = filter_audit_rows(rows, rule_id="rbi-contact-hours")

    assert {row["record_id"] for row in vetoes} == {
        "ASH-2026-0045",
        "ASH-2026-0046",
        "ASH-2026-0047",
    }
    # Counted from the artifact rather than hardcoded: these move whenever the
    # rule ladder changes, and a stale literal here is a failing test that says
    # nothing about the filter under test.
    firings = json.loads((RUNS / "seed42" / "metrics.json").read_text(encoding="utf-8"))
    expected_rbi = firings["arms"]["agent"]["rule_firings"]["rbi-contact-hours"]
    assert len(rbi) == expected_rbi > 0
    assert all(row["rule_id"] == "rbi-contact-hours" for row in rbi)
    assert vetoes and all(row["verdict"] == "VETOED" for row in vetoes)
    assert all(row["source_verified"] is True for row in rbi)


def test_run_path_rejects_traversal() -> None:
    try:
        run_path(RUNS, "../outside")
    except ValueError as exc:
        assert "unsafe run id" in str(exc)
    else:
        raise AssertionError("path traversal was accepted")


def test_unverified_regulatory_source_gets_a_visible_exclusion_badge() -> None:
    """OBS-006's dormant honesty path is pinned by a synthetic source fixture."""
    source = RuleSource(
        kind=RuleKind.REGULATORY,
        title="Unverified fixture",
        verified=False,
        scope_caveat="Not for the recorded demo.",
    )

    assert source_status(source) == ("Unverified · exclude from demo", "unverified")


def test_all_three_streamlit_views_render_from_local_artifacts() -> None:
    """Exercise the Phase 5 gate without starting a server or making a network call."""
    app = AppTest.from_file(str(ROOT / "dashboard" / "app.py"), default_timeout=30).run()
    assert not app.exception
    assert app.sidebar.selectbox[0].value == "seed42"
    assert len(app.dataframe) == 2

    app.sidebar.radio[0].set_value("Payer timeline").run()
    assert not app.exception
    assert app.title[0].value == "One receivable, every decision"
    assert next(item for item in app.selectbox if item.label == "Payer name").value == (
        "Netra Optics & Lenses"
    )
    timeline_markup = "\n".join(item.value for item in app.markdown)
    assert "Wait · deliberate restraint" in timeline_markup
    assert "Veto · policy disposes" in timeline_markup
    assert "Verified at issuing body" in timeline_markup

    app.sidebar.radio[0].set_value("Raw audit").run()
    assert not app.exception
    assert app.title[0].value == "The audit log, without the gloss"
    assert len(app.dataframe) == 1
    # Read from the artifact: the row count moves with any policy change.
    expected_rows = sum(
        1 for _ in (RUNS / "seed42" / "agent" / "audit.jsonl").open(encoding="utf-8")
    )
    assert app.metric[0].value == str(expected_rows)
