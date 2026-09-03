"""Filterable raw audit view for the Recoup dashboard."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.data import (
    ArmArtifact,
    audit_filter_options,
    filter_audit_rows,
    flatten_audit_rows,
    raw_row,
    serialise_filtered_jsonl,
)


def _optional(label: str, options: tuple[str, ...]) -> str | None:
    selected = st.selectbox(label, ("All", *options))
    return None if selected == "All" else selected


def render(artifact: ArmArtifact) -> None:
    """Render filters over the real JSONL and a lossless row inspector."""
    st.markdown('<div class="recoup-kicker">Append-only evidence</div>', unsafe_allow_html=True)
    st.title("The audit log, without the gloss")
    st.markdown(
        '<p class="section-intro">This table is flattened for scanning, not regenerated '
        "from business logic. Select any row below to inspect the exact domain object "
        "read from audit.jsonl.</p>",
        unsafe_allow_html=True,
    )

    flattened = flatten_audit_rows(artifact)
    options = audit_filter_options(flattened)
    filter_columns = st.columns((1.4, 1, 1, 1))
    with filter_columns[0]:
        kinds = st.multiselect("Row kind", options["kinds"], default=options["kinds"])
    with filter_columns[1]:
        verdict = _optional("Verdict", options["verdicts"])
    with filter_columns[2]:
        rule_id = _optional("Policy rule", options["rules"])
    with filter_columns[3]:
        executor = _optional("Executor", options["executors"])
    query = st.text_input("Search payer, invoice, proposal, rule, outcome or row id")

    filtered = filter_audit_rows(
        flattened,
        kinds=set(kinds),
        verdict=verdict,
        rule_id=rule_id,
        executor=executor,
        query=query,
    )
    left, middle, right = st.columns(3)
    left.metric("Visible rows", f"{len(filtered):,}")
    middle.metric("Total rows", f"{len(flattened):,}")
    right.metric("Hash-chain start", artifact.rows[0].prev_row_hash[:12] + "…")

    display_columns = [
        "row_id",
        "virtual_time",
        "kind",
        "record_id",
        "payer_name",
        "proposal",
        "verdict",
        "rule_id",
        "action",
        "executed",
        "executor",
        "outcome",
        "amount_paise",
        "external_ref",
        "prev_row_hash",
    ]
    frame = pd.DataFrame(filtered, columns=display_columns)
    st.dataframe(
        frame,
        width="stretch",
        height=520,
        hide_index=True,
        column_config={
            "amount_paise": st.column_config.NumberColumn("Outcome paise", format="%d"),
            "prev_row_hash": st.column_config.TextColumn("Previous row hash", width="large"),
        },
    )

    st.download_button(
        "Download filtered JSONL",
        data=serialise_filtered_jsonl(artifact, filtered),
        file_name=f"{artifact.run_id}-{artifact.arm}-audit-filtered.jsonl",
        mime="application/x-ndjson",
        disabled=not filtered,
    )
    if not filtered:
        st.warning("No rows match these filters.")
        return

    row_ids = tuple(int(item["row_id"]) for item in filtered)
    inspected = st.selectbox("Inspect exact row", row_ids, format_func=lambda item: f"row {item}")
    with st.expander(f"Raw row {inspected}", expanded=True):
        st.json(raw_row(artifact, inspected), expanded=2)
