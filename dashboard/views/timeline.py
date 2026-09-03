"""Named-payer virtual timeline for the Recoup dashboard."""

from __future__ import annotations

from collections.abc import Sequence

import streamlit as st

from dashboard.data import (
    ArmArtifact,
    featured_story,
    invoice_ids_for_payer,
    payer_names,
    rows_for_invoice,
    source_status,
)
from dashboard.theme import escape
from recoup.domain.enums import RowKind, RuleKind, VerdictKind
from recoup.domain.models import AuditRow, Invoice, RuleSource, format_inr
from recoup.ledger.clock import format_tick


def _event(row: AuditRow) -> tuple[str, str, str, str, str]:
    """Return CSS tone, eyebrow, title, body and metadata for one audit row."""
    if row.kind is RowKind.INTAKE:
        snapshot = row.input_snapshot or {}
        return (
            "",
            "Intake",
            "Invoice entered the recovery book",
            f"Outstanding {format_inr(int(snapshot.get('outstanding_paise', 0)))} · "
            f"{snapshot.get('days_overdue', '?')} days overdue.",
            "Opening facts are preserved on the append-only row.",
        )
    if row.kind is RowKind.OUTCOME and row.outcome is not None:
        amount = f" · {format_inr(row.outcome.amount_paise)}" if row.outcome.amount_paise else ""
        return (
            "outcome",
            "Payer outcome",
            row.outcome.kind.value.replace("_", " ").title(),
            row.outcome.detail or "The simulated world responded to the last action.",
            f"Outcome{amount} · new row, never an update",
        )
    if row.policy_verdict is not None and row.policy_verdict.verdict is VerdictKind.VETOED:
        verdict = row.policy_verdict
        source = verdict.rule_source
        source_name = source.title if source else "Source unavailable"
        original = verdict.original.value.replace("_", " ").title()
        return (
            "veto",
            "Veto · policy disposes",
            f"{original} held by {verdict.rule_id}",
            verdict.explanation,
            f"{source_name} · executed false",
        )
    if row.action is not None and row.action.intervention.value == "WAIT":
        proposal = row.llm_proposal
        body = proposal.reasoning if proposal else "The strategy chose time over another contact."
        return (
            "wait",
            "Wait · deliberate restraint",
            "No contact was made",
            body,
            f"{row.policy_verdict.verdict.value if row.policy_verdict else 'NO POLICY'} · "
            "0 contact units",
        )
    if row.kind is RowKind.DECISION and row.action is not None:
        verdict = row.policy_verdict
        proposal = row.llm_proposal
        tone = "" if verdict is None or verdict.verdict is not VerdictKind.MODIFIED else "wait"
        eyebrow = "Decision" if verdict is None else verdict.verdict.value.replace("_", " ")
        body = proposal.reasoning if proposal else "Deterministic strategy decision."
        execution = "executed" if row.action.executed else "not executed"
        return (
            tone,
            eyebrow,
            row.action.intervention.value.replace("_", " ").title(),
            body,
            f"{row.action.executor.value} · {execution} · {row.action.contact_units} contact units",
        )
    return "", row.kind.value, "Audit event", "Recorded on the append-only ledger.", ""


def _timeline_html(rows: Sequence[AuditRow]) -> str:
    blocks: list[str] = ['<div class="timeline">']
    for row in rows:
        tone, eyebrow, title, body, metadata = _event(row)
        week = row.tick // 28 + 1
        blocks.append(
            f"""
            <div class="timeline-row">
              <div class="timeline-time"><strong>Week {week} · tick {row.tick}</strong>
              {escape(format_tick(row.tick))}</div>
              <div class="timeline-rail"><span class="timeline-dot {tone}"></span></div>
              <div class="timeline-body">
                <div class="timeline-eyebrow {tone}">{escape(eyebrow)}</div>
                <div class="timeline-title">{escape(title)}</div>
                <div class="timeline-copy">{escape(body)}</div>
                <div class="timeline-meta">row {row.row_id} · {escape(metadata)}</div>
              </div>
            </div>
            """
        )
    blocks.append("</div>")
    return "".join(blocks)


def _source_card(source: RuleSource) -> str:
    status, tone = source_status(source)
    caveat = source.scope_caveat or "Business configuration; no regulatory claim is made."
    link = (
        f'<a href="{escape(source.url)}" target="_blank" rel="noreferrer">Read issuing source ↗</a>'
        if source.url
        else "No external citation — merchant configuration."
    )
    return f"""
    <div class="source-card {tone}">
      <span class="source-pill {tone}">{escape(status)}</span>
      <h4>{escape(source.title)}</h4>
      <p>{escape(caveat)}</p><p>{link}</p>
    </div>
    """


def _invoice_label(invoice_id: str, opening: dict[str, Invoice]) -> str:
    record = opening[invoice_id]
    return f"{invoice_id} · {format_inr(record.amount_paise)} · due {record.due_on.isoformat()}"


def render(artifact: ArmArtifact) -> None:
    """Render a timeline selected by payer name, with invoice as a second key."""
    st.markdown('<div class="recoup-kicker">Payer story</div>', unsafe_allow_html=True)
    st.title("One receivable, every decision")
    st.markdown(
        '<p class="section-intro">Virtual weeks make restraint visible. Every outcome is a '
        "new row; a veto retains the proposed action, the rule that stopped it, and the "
        "source behind that rule.</p>",
        unsafe_allow_html=True,
    )

    featured_payer, featured_invoice = featured_story(artifact)
    names = payer_names(artifact)
    selected_payer = st.selectbox(
        "Payer name",
        names,
        index=names.index(featured_payer),
        help="The product-facing key is a payer name, not an internal invoice id.",
    )
    invoices = invoice_ids_for_payer(artifact, selected_payer)
    default_invoice = featured_invoice if featured_invoice in invoices else invoices[0]
    opening = dict(artifact.opening_by_id)
    selected_invoice = st.selectbox(
        "Invoice",
        invoices,
        index=invoices.index(default_invoice),
        format_func=lambda invoice_id: _invoice_label(invoice_id, opening),
    )

    opened = opening[selected_invoice]
    closed = artifact.final_by_id[selected_invoice]
    columns = st.columns(4)
    columns[0].metric("Payer", opened.payer_name)
    columns[1].metric("Invoice value", format_inr(opened.amount_paise))
    columns[2].metric("Closing state", closed.state.value.replace("_", " ").title())
    columns[3].metric("Recovered", format_inr(closed.recovered_paise))
    st.caption(
        f"{opened.payer_city} · {opened.payer_contact_name}, {opened.payer_contact_role} · "
        f"artifact {artifact.run_id}/{artifact.arm}"
    )

    rows = rows_for_invoice(artifact, selected_invoice)
    st.markdown(_timeline_html(rows), unsafe_allow_html=True)

    sources: dict[str, RuleSource] = {}
    for row in rows:
        if row.policy_verdict and row.policy_verdict.rule_source:
            source = row.policy_verdict.rule_source
            sources[source.title] = source
    if sources:
        st.markdown("## Why a veto was allowed to overrule the proposal")
        for source in sorted(sources.values(), key=lambda item: item.kind is RuleKind.MERCHANT):
            st.markdown(_source_card(source), unsafe_allow_html=True)
    else:
        st.info(
            "This invoice has no policy source attached because no rule fired on its decisions."
        )
