"""Shared visual language for the three Recoup dashboard views."""

# CSS declarations are kept one selector per line so the visual tokens stay
# scannable. Their natural width is occasionally longer than Python's limit.
# ruff: noqa: E501

from __future__ import annotations

import html
from decimal import ROUND_HALF_UP, Decimal

from dashboard.data import Scorecard
from recoup.domain.models import format_inr


def escape(value: object) -> str:
    """Escape artifact text before placing it in a small HTML component."""
    return html.escape(str(value), quote=True)


def percent(value: Decimal, places: str = "0.01") -> str:
    """Render a stored decimal percentage without converting through float."""
    return f"{value.quantize(Decimal(places), rounding=ROUND_HALF_UP):f}%"


def recovered(scorecard: Scorecard) -> str:
    """Render the exact integer-paise recovery value."""
    return format_inr(scorecard.recovered_paise)


CSS = """
<style>
:root {
  --ink: #142522;
  --muted: #66736f;
  --paper: #f6f2e9;
  --card: #fffdf8;
  --line: #dcd6c8;
  --teal: #0d6257;
  --mint: #cfeee2;
  --coral: #e9654b;
  --amber: #e2a83b;
  --navy: #183f4a;
}
.stApp { background: var(--paper); color: var(--ink); }
[data-testid="stSidebar"] { background: #102c31; }
[data-testid="stSidebar"] * { color: #f7f1e6; }
[data-testid="stSidebar"] [data-baseweb="select"] * { color: var(--ink); }
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color: #b7c9c5; }
.block-container { max-width: 1380px; padding-top: 2.1rem; padding-bottom: 4rem; }
h1, h2, h3 { color: var(--ink); letter-spacing: -0.035em; }
.recoup-kicker {
  color: var(--teal); font-size: .72rem; font-weight: 800; letter-spacing: .16em;
  text-transform: uppercase; margin-bottom: .55rem;
}
.recoup-hero {
  background: var(--navy); color: white; padding: 2.1rem 2.2rem 2rem;
  border-radius: 4px 28px 4px 4px; margin-bottom: 1.2rem; position: relative;
  overflow: hidden; box-shadow: 0 16px 38px rgba(24,63,74,.13);
}
.recoup-hero:after {
  content: ""; position: absolute; width: 190px; height: 190px; border-radius: 50%;
  right: -52px; top: -92px; border: 34px solid rgba(207,238,226,.16);
}
.recoup-hero h1 { color: white; font-size: clamp(2rem, 4vw, 3.8rem); margin: 0; line-height: .98; }
.recoup-hero p { color: #cfe0dc; max-width: 760px; font-size: 1.05rem; margin: .9rem 0 0; }
.offline-pill, .source-pill {
  display: inline-flex; align-items: center; gap: .38rem; border-radius: 999px;
  padding: .32rem .68rem; font-size: .72rem; font-weight: 750; letter-spacing: .03em;
}
.offline-pill { background: var(--mint); color: #174b42; margin-bottom: 1rem; }
.offline-pill:before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: #1c8b72; }
.metric-card {
  background: var(--card); border: 1px solid var(--line); border-top: 4px solid var(--teal);
  padding: 1.05rem 1.1rem; min-height: 150px; box-shadow: 0 8px 22px rgba(20,37,34,.055);
}
.metric-card.model { border-top-color: var(--coral); background: #fff9f4; }
.metric-card .label { color: var(--muted); font-size: .72rem; text-transform: uppercase; letter-spacing: .08em; font-weight: 800; }
.metric-card .value { color: var(--ink); font-size: 1.85rem; font-weight: 780; letter-spacing: -.05em; margin: .32rem 0 .1rem; }
.metric-card .sub { color: var(--muted); font-size: .78rem; line-height: 1.4; }
.story-card {
  background: var(--card); border: 1px solid var(--line); padding: 1.15rem 1.2rem;
  min-height: 154px; border-radius: 3px 17px 3px 3px;
}
.story-card strong { display: block; font-size: 1.7rem; letter-spacing: -.04em; color: var(--teal); }
.story-card p { color: var(--muted); margin: .45rem 0 0; font-size: .86rem; line-height: 1.5; }
.section-intro { color: var(--muted); max-width: 820px; margin-top: -.35rem; }
.timeline { margin: 1.2rem 0 2rem; }
.timeline-row { display: grid; grid-template-columns: 142px 24px 1fr; gap: .55rem; min-height: 112px; }
.timeline-time { text-align: right; padding: .15rem .55rem 0 0; color: var(--muted); font-size: .74rem; line-height: 1.45; }
.timeline-time strong { color: var(--ink); display: block; }
.timeline-rail { position: relative; }
.timeline-rail:before { content: ""; position: absolute; left: 11px; top: 20px; bottom: -8px; width: 1px; background: #c7c0b1; }
.timeline-row:last-child .timeline-rail:before { display: none; }
.timeline-dot { position: absolute; top: 4px; left: 4px; width: 16px; height: 16px; border-radius: 50%; background: var(--teal); border: 4px solid var(--paper); box-shadow: 0 0 0 1px var(--teal); }
.timeline-dot.wait { background: var(--amber); box-shadow: 0 0 0 1px var(--amber); }
.timeline-dot.veto { background: var(--coral); box-shadow: 0 0 0 1px var(--coral); }
.timeline-dot.outcome { background: var(--navy); box-shadow: 0 0 0 1px var(--navy); }
.timeline-body { background: var(--card); border: 1px solid var(--line); padding: .82rem 1rem; margin-bottom: .8rem; }
.timeline-eyebrow { color: var(--teal); font-weight: 850; letter-spacing: .09em; font-size: .67rem; text-transform: uppercase; }
.timeline-eyebrow.veto { color: var(--coral); }
.timeline-eyebrow.wait { color: #9b6a00; }
.timeline-title { font-weight: 780; color: var(--ink); margin: .18rem 0 .35rem; }
.timeline-copy { color: var(--muted); font-size: .82rem; line-height: 1.5; }
.timeline-meta { color: #75817d; font-size: .7rem; margin-top: .5rem; }
.source-card { background: #edf4f0; border-left: 4px solid var(--teal); padding: 1rem 1.1rem; margin: .65rem 0; }
.source-card.unverified { background: #fff0ec; border-left-color: var(--coral); }
.source-card.merchant { background: #f0eee8; border-left-color: #7f837e; }
.source-card h4 { margin: 0 0 .35rem; color: var(--ink); }
.source-card p { color: #586762; font-size: .8rem; line-height: 1.48; margin: .42rem 0; }
.source-pill.verified { background: #cde9de; color: #12584d; }
.source-pill.unverified { background: #ffd8cf; color: #8b2f1d; }
.source-pill.merchant { background: #dedbd2; color: #545955; }
.artifact-note { border: 1px dashed #b9b2a4; padding: .8rem 1rem; color: var(--muted); font-size: .78rem; }
div[data-testid="stDataFrame"] { border: 1px solid var(--line); }
@media (max-width: 720px) {
  .timeline-row { grid-template-columns: 1fr; gap: .2rem; }
  .timeline-time { text-align: left; }
  .timeline-rail { display: none; }
  .recoup-hero { padding: 1.5rem; }
}
</style>
"""
