"""Portfolio-level evidence view for the Recoup dashboard."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal

import pandas as pd
import streamlit as st

from dashboard.data import MetricsArtifact, Scorecard, source_status
from dashboard.theme import escape, percent
from recoup.domain.models import RuleSource, format_inr


def _card(score: Scorecard) -> str:
    kind = "model" if score.is_model_output else ""
    provenance = "real model proposals" if score.is_model_output else "deterministic / no-model"
    return f"""
    <div class="metric-card {kind}">
      <div class="label">{escape(score.label)}</div>
      <div class="value">{escape(percent(score.recovery_rate_percent))}</div>
      <div class="sub">{score.contacts_made:,} contacts · {score.false_interventions} false<br>
      {escape(provenance)} · {escape(score.run_id)}</div>
    </div>
    """


def _delta(before: int, after: int) -> str:
    return f"{before - after:,} fewer" if before >= after else f"{after - before:,} more"


def _source_card(source: RuleSource) -> str:
    status, tone = source_status(source)
    caveat = source.scope_caveat or "Business configuration; no regulatory claim is made."
    cited = f" · {escape(source.cited_date)}" if source.cited_date else ""
    link = (
        f'<a href="{escape(source.url)}" target="_blank" rel="noreferrer">Open source ↗</a>'
        if source.url
        else ""
    )
    return f"""
    <div class="source-card {tone}">
      <span class="source-pill {tone}">{escape(status)}</span>
      <h4>{escape(source.title)}{cited}</h4>
      <p>{escape(caveat)}</p>
      <p>{link}</p>
    </div>
    """


def _scorecard_table(cards: Sequence[Scorecard]) -> pd.DataFrame:
    rows: dict[str, list[object]] = {
        "Value recovery": [percent(item.recovery_rate_percent) for item in cards],
        "Recovered": [format_inr(item.recovered_paise) for item in cards],
        "Paid records": [f"{item.paid_records} / {item.total_records}" for item in cards],
        "Contacts": [f"{item.contacts_made:,}" for item in cards],
        "Payment links": [f"{item.payment_links_sent:,}" for item in cards],
        "False interventions": [f"{item.false_interventions:,}" for item in cards],
        "— disputed": [f"{item.false_interventions_disputed:,}" for item in cards],
        "— already paid": [f"{item.false_interventions_already_paid:,}" for item in cards],
        "Policy vetoes": [
            f"{item.policy_vetoes:,}" if item.policy_enabled else "bypassed" for item in cards
        ],
        "Unresolved": [f"{item.unresolved_records:,}" for item in cards],
        "Written off": [f"{item.written_off_records:,}" for item in cards],
    }
    return pd.DataFrame(rows, index=[item.label for item in cards]).T


def _rule_table(cards: Sequence[Scorecard], metrics: MetricsArtifact) -> pd.DataFrame:
    rules = tuple(metrics.rule_run_notes)
    columns: dict[str, list[object]] = {"Run status": [metrics.rule_run_notes[r] for r in rules]}
    for card in cards:
        columns[card.label] = [
            card.rule_firings.get(rule, 0) if card.policy_enabled else "bypassed" for rule in rules
        ]
    return pd.DataFrame(columns, index=rules)


def render(
    cards: Sequence[Scorecard],
    metrics: MetricsArtifact,
    sources: Mapping[str, RuleSource],
) -> None:
    """Render the video-opening comparison, losses and provenance."""
    st.markdown('<div class="recoup-kicker">Portfolio evidence</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="recoup-hero">
          <span class="offline-pill">Offline artifact · zero API calls</span>
          <h1>Recover revenue.<br>Refuse blind pressure.</h1>
          <p>Five strategies on the same seeded receivables book. The model proposes;
          deterministic policy decides what is safe to execute.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    columns = st.columns(len(cards))
    for column, card in zip(columns, cards, strict=True):
        with column:
            st.markdown(_card(card), unsafe_allow_html=True)

    by_key = {card.key: card for card in cards}
    if {"baseline", "policy_baseline", "agent"} <= by_key.keys():
        naive = by_key["baseline"]
        policy = by_key["policy_baseline"]
        deterministic = by_key["agent"]
        model = by_key.get("agent_model_triage")
        st.markdown("## What changed — and what it cost")
        story_columns = st.columns(3)
        with story_columns[0]:
            st.markdown(
                f"""
                <div class="story-card"><div class="recoup-kicker">Policy value</div>
                <strong>{_delta(naive.contacts_made, policy.contacts_made)} contacts</strong>
                <p>Same naive proposer. False interventions fall
                {naive.false_interventions} → {policy.false_interventions}; recovery moves
                {percent(naive.recovery_rate_percent)} →
                {percent(policy.recovery_rate_percent)}.</p></div>
                """,
                unsafe_allow_html=True,
            )
        with story_columns[1]:
            st.markdown(
                f"""
                <div class="story-card"><div class="recoup-kicker">Proposer value</div>
                <strong>{deterministic.paid_records - policy.paid_records:+d} paid records</strong>
                <p>Policy held constant. The deterministic ladder uses
                {deterministic.contacts_made} contacts and recovers
                {percent(deterministic.recovery_rate_percent)}; residual false contact stays at
                {deterministic.false_interventions}.</p></div>
                """,
                unsafe_allow_html=True,
            )
        with story_columns[2]:
            if model is None:
                st.markdown(
                    """
                    <div class="story-card"><div class="recoup-kicker">Model evidence</div>
                    <strong>Not attached</strong><p>This run has no sibling tiered artifact.
                    The dashboard will not invent or relabel model output.</p></div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                recovery_delta = model.recovery_rate_percent - deterministic.recovery_rate_percent
                st.markdown(
                    f"""
                    <div class="story-card"><div class="recoup-kicker">Harm trade-off</div>
                    <strong>{deterministic.false_interventions} →
                    {model.false_interventions} false</strong>
                    <p>Real model proposals at first review cut
                    {_delta(deterministic.contacts_made, model.contacts_made)} contacts at
                    {recovery_delta.quantize(Decimal("0.01")):+f} recovery points. Escalation is
                    unrewarded by this simulation, so this is not a recovery-beat claim.</p></div>
                    """,
                    unsafe_allow_html=True,
                )

    st.markdown("## Full scorecard — losses included")
    st.markdown(
        '<p class="section-intro">The do-nothing floor stays visible. “Bypassed” is not '
        "rendered as zero, and unresolved / written-off records remain in the comparison.</p>",
        unsafe_allow_html=True,
    )
    st.dataframe(_scorecard_table(cards), width="stretch", height=430)

    with st.expander("Policy-rule firings and meaningful zeroes"):
        st.caption(
            "A number means policy ran. Bypassed means it did not; each dormant or disabled rule "
            "keeps its run-status note."
        )
        st.dataframe(_rule_table(cards, metrics), width="stretch", height=430)

    st.markdown("## Sources travel with the decision")
    st.markdown(
        '<p class="section-intro">Regulatory verification and scope caveats are data, not '
        "footnotes. Merchant configuration is labelled as merchant policy and never receives "
        "a false verified badge.</p>",
        unsafe_allow_html=True,
    )
    for source in sources.values():
        st.markdown(_source_card(source), unsafe_allow_html=True)

    model_runs = sorted({card.run_id for card in cards if card.is_model_output})
    deterministic_runs = sorted({card.run_id for card in cards if not card.is_model_output})
    st.markdown(
        f"""
        <div class="artifact-note"><strong>Artifact boundary.</strong> Deterministic columns read
        <code>{escape(", ".join(deterministic_runs))}</code>. Model output reads
        <code>{escape(", ".join(model_runs) if model_runs else "none")}</code>. The
        model-triage arm is a fifth result, never a relabelled deterministic agent. All money
        shown above is read as integer paise.</div>
        """,
        unsafe_allow_html=True,
    )
