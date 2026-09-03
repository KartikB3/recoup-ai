"""Recoup's three-view Streamlit application.

Run through ``recoup dashboard``. The process reads only local run artifacts;
there is no reasoner, Razorpay client, webhook, or wall-clock dependency here.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import streamlit as st

from dashboard.data import (
    ARM_LABELS,
    available_arms,
    comparison_scorecards,
    default_run_id,
    discover_run_ids,
    load_arm,
    load_metrics,
)
from dashboard.theme import CSS, topbar
from dashboard.views import audit, summary, timeline
from recoup.policy.sources import ALL_SOURCES


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--run-id")
    parser.add_argument("--runs-root", type=Path, default=Path("runs"))
    arguments, _unknown = parser.parse_known_args()
    return arguments


def main() -> None:
    """Render navigation once and keep every page on the same artifact boundary."""
    st.set_page_config(
        page_title="Recoup · Revenue recovery with restraint",
        page_icon="↗",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(CSS, unsafe_allow_html=True)
    arguments = _arguments()
    runs_root = arguments.runs_root.resolve()
    run_ids = discover_run_ids(runs_root)
    if not run_ids:
        st.error(f"No dashboard-ready runs under {runs_root}. Run `recoup metrics <id>` first.")
        st.stop()

    preferred = arguments.run_id or default_run_id(run_ids)
    if preferred not in run_ids:
        st.error(f"Run {preferred!r} has no metrics.json under {runs_root}.")
        st.stop()

    st.sidebar.markdown("# Recoup")
    st.sidebar.caption("Receivables recovery · policy-gated")
    selected_run = st.sidebar.selectbox(
        "Evidence run",
        run_ids,
        index=run_ids.index(preferred),
        help="Changing this reads another local runs/<id>/ directory.",
    )
    view = st.sidebar.radio(
        "View",
        ("Portfolio summary", "Payer timeline", "Raw audit"),
    )
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Artifact status**")
    st.sidebar.caption("LOCAL · OFFLINE · APPEND-ONLY")
    st.sidebar.caption(f"{runs_root / selected_run}")

    try:
        if view == "Portfolio summary":
            st.markdown(topbar(selected_run), unsafe_allow_html=True)
            metrics = load_metrics(runs_root, selected_run)
            cards = comparison_scorecards(runs_root, selected_run)
            summary.render(cards, metrics, ALL_SOURCES)
            return

        arms = available_arms(runs_root, selected_run)
        if not arms:
            st.error(f"Run {selected_run!r} has metrics but no complete arm artifacts.")
            st.stop()
        default_arm = "agent" if "agent" in arms else arms[0]
        arm = st.sidebar.selectbox(
            "Arm",
            arms,
            index=arms.index(default_arm),
            format_func=lambda item: ARM_LABELS[item],
        )
        st.markdown(topbar(selected_run, ARM_LABELS[arm]), unsafe_allow_html=True)
        artifact = load_arm(runs_root, selected_run, arm)
        if view == "Payer timeline":
            timeline.render(artifact)
        else:
            audit.render(artifact)
    except (FileNotFoundError, ValueError) as exc:
        st.error(f"Artifact validation failed: {exc}")
        st.stop()


main()
